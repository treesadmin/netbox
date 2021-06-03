import json
import traceback
import uuid
import logging

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from extras.api.serializers import ScriptOutputSerializer
from extras.choices import JobResultStatusChoices
from extras.models import JobResult
from extras.scripts import get_script
from utilities.exceptions import AbortTransaction


class Command(BaseCommand):
    help = "Run a script"

    def add_arguments(self, parser):
        parser.add_argument('--script', help="Script to run", required=True)
        parser.add_argument('--commit', help="Commit", const=True, nargs="?", required=False, default=False, type=bool)
        parser.add_argument('--data', help="Data in JSON format", nargs="+", required=False, type=str)

    def handle(self, *args, **options):
        import pprint
        name = options['script']
        commit = options['commit']
        script_content_type = ContentType.objects.get(app_label='extras', model='script')
        job_result = JobResult.objects.create(
            name=name,
            obj_type=script_content_type,
            user=None,
            job_id=uuid.uuid4(),
        )

        module, script_name = job_result.name.split('.', 1)
        script = get_script(module, script_name)()

        if options['data'] is None:
            unclean_data = {'_commit': options['commit']}
        elif len(script._get_vars()) == len(options['data']):
            pos = 0
            unclean_data = {'_commit': options['commit']}
            for attr, val in script._get_vars().items():
                unclean_data[attr] = options['data'][pos]
                pos += 1
        elif len(options['data']) == 1:
            unclean_data = json.loads(options['data'][0])
        else:
            raise NotImplemented()

        form = script.as_form(unclean_data)
        if form.is_valid():
            data = form.cleaned_data
            logger = logging.getLogger(f"netbox.scripts.{module}.{script_name}")
            logger.info(f"running script (commit={commit})")

            job_result.status = JobResultStatusChoices.STATUS_RUNNING
            job_result.save()

            """
            core script execution task. we capture this within a subfunction to allow for conditionally wrapping it with
            the change_logging context manager (which is bypassed if commit == false).
            """
            try:
                with transaction.atomic():
                    script.output = script.run(data=data, commit=commit)
                    job_result.set_status(JobResultStatusChoices.STATUS_COMPLETED)

                    if not commit:
                        raise AbortTransaction()
            except AbortTransaction:
                script.log_info("database changes have been reverted automatically.")

            except Exception as e:
                stacktrace = traceback.format_exc()
                script.log_failure(
                    f"an exception occurred: `{type(e).__name__}: {e}`\n```\n{stacktrace}\n```"
                )
                script.log_info("database changes have been reverted due to error.")
                logger.error(f"exception raised during script execution: {e}")
                job_result.set_status(JobResultStatusChoices.STATUS_ERRORED)

            finally:
                job_result.data = ScriptOutputSerializer(script).data
                job_result.save()

            logger.info(f"script completed in {job_result.duration}")
        else:
            script.log_failure("Some data is missing.")
            job_result.set_status(JobResultStatusChoices.STATUS_ERRORED)
            job_result.save()
