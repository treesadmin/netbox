import csv
import json
import re
from io import StringIO

import django_filters
from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db.models import Count, Q
from django.forms import BoundField
from django.forms.fields import JSONField as _JSONField, InvalidJSONInput
from django.urls import reverse

from utilities.choices import unpack_grouped_choices
from utilities.utils import content_type_name
from utilities.validators import EnhancedURLValidator
from . import widgets
from .constants import *
from .utils import expand_alphanumeric_pattern, expand_ipaddress_pattern, parse_csv, validate_csv

__all__ = (
    'ColorField',
    'CommentField',
    'ContentTypeChoiceField',
    'ContentTypeMultipleChoiceField',
    'CSVChoiceField',
    'CSVContentTypeField',
    'CSVDataField',
    'CSVFileField',
    'CSVModelChoiceField',
    'CSVMultipleContentTypeField',
    'CSVTypedChoiceField',
    'DynamicModelChoiceField',
    'DynamicModelMultipleChoiceField',
    'ExpandableIPAddressField',
    'ExpandableNameField',
    'JSONField',
    'LaxURLField',
    'SlugField',
    'TagFilterField',
)


class CommentField(forms.CharField):
    """
    A textarea with support for Markdown rendering. Exists mostly just to add a standard help_text.
    """
    widget = forms.Textarea
    default_label = ''
    # TODO: Port Markdown cheat sheet to internal documentation
    default_helptext = '<i class="mdi mdi-information-outline"></i> '\
                       '<a href="https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet" target="_blank" tabindex="-1">'\
                       'Markdown</a> syntax is supported'

    def __init__(self, *args, **kwargs):
        required = kwargs.pop('required', False)
        label = kwargs.pop('label', self.default_label)
        help_text = kwargs.pop('help_text', self.default_helptext)
        super().__init__(required=required, label=label, help_text=help_text, *args, **kwargs)


class SlugField(forms.SlugField):
    """
    Extend the built-in SlugField to automatically populate from a field called `name` unless otherwise specified.
    """

    def __init__(self, slug_source='name', *args, **kwargs):
        label = kwargs.pop('label', "Slug")
        help_text = kwargs.pop('help_text', "URL-friendly unique shorthand")
        widget = kwargs.pop('widget', widgets.SlugWidget)
        super().__init__(label=label, help_text=help_text, widget=widget, *args, **kwargs)
        self.widget.attrs['slug-source'] = slug_source


class ColorField(forms.CharField):
    """
    A field which represents a color in hexadecimal RRGGBB format.
    """
    widget = widgets.ColorSelect


class TagFilterField(forms.MultipleChoiceField):
    """
    A filter field for the tags of a model. Only the tags used by a model are displayed.

    :param model: The model of the filter
    """
    widget = widgets.StaticSelectMultiple

    def __init__(self, model, *args, **kwargs):
        def get_choices():
            tags = model.tags.annotate(
                count=Count('extras_taggeditem_items')
            ).order_by('name')
            return [(str(tag.slug), f'{tag.name} ({tag.count})') for tag in tags]

        # Choices are fetched each time the form is initialized
        super().__init__(label='Tags', choices=get_choices, required=False, *args, **kwargs)


class LaxURLField(forms.URLField):
    """
    Modifies Django's built-in URLField to remove the requirement for fully-qualified domain names
    (e.g. http://myserver/ is valid)
    """
    default_validators = [EnhancedURLValidator()]


class JSONField(_JSONField):
    """
    Custom wrapper around Django's built-in JSONField to avoid presenting "null" as the default text.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.help_text:
            self.help_text = 'Enter context data in <a href="https://json.org/">JSON</a> format.'
            self.widget.attrs['placeholder'] = ''

    def prepare_value(self, value):
        if isinstance(value, InvalidJSONInput):
            return value
        if value is None:
            return ''
        return json.dumps(value, sort_keys=True, indent=4)


class ContentTypeChoiceMixin:

    def __init__(self, queryset, *args, **kwargs):
        # Order ContentTypes by app_label
        queryset = queryset.order_by('app_label', 'model')
        super().__init__(queryset, *args, **kwargs)

    def label_from_instance(self, obj):
        try:
            return content_type_name(obj)
        except AttributeError:
            return super().label_from_instance(obj)


class ContentTypeChoiceField(ContentTypeChoiceMixin, forms.ModelChoiceField):
    pass


class ContentTypeMultipleChoiceField(ContentTypeChoiceMixin, forms.ModelMultipleChoiceField):
    pass


#
# CSV fields
#

class CSVDataField(forms.CharField):
    """
    A CharField (rendered as a Textarea) which accepts CSV-formatted data. It returns data as a two-tuple: The first
    item is a dictionary of column headers, mapping field names to the attribute by which they match a related object
    (where applicable). The second item is a list of dictionaries, each representing a discrete row of CSV data.

    :param from_form: The form from which the field derives its validation rules.
    """
    widget = forms.Textarea

    def __init__(self, from_form, *args, **kwargs):

        form = from_form()
        self.model = form.Meta.model
        self.fields = form.fields
        self.required_fields = [
            name for name, field in form.fields.items() if field.required
        ]

        super().__init__(*args, **kwargs)

        self.strip = False
        if not self.label:
            self.label = ''
        if not self.initial:
            self.initial = ','.join(self.required_fields) + '\n'
        if not self.help_text:
            self.help_text = 'Enter the list of column headers followed by one line per record to be imported, using ' \
                             'commas to separate values. Multi-line data and values containing commas may be wrapped ' \
                             'in double quotes.'

    def to_python(self, value):
        reader = csv.reader(StringIO(value.strip()))

        return parse_csv(reader)

    def validate(self, value):
        headers, records = value
        validate_csv(headers, self.fields, self.required_fields)

        return value


class CSVFileField(forms.FileField):
    """
    A FileField (rendered as a file input button) which accepts a file containing CSV-formatted data. It returns
    data as a two-tuple: The first item is a dictionary of column headers, mapping field names to the attribute
    by which they match a related object (where applicable). The second item is a list of dictionaries, each
    representing a discrete row of CSV data.

    :param from_form: The form from which the field derives its validation rules.
    """

    def __init__(self, from_form, *args, **kwargs):

        form = from_form()
        self.model = form.Meta.model
        self.fields = form.fields
        self.required_fields = [
            name for name, field in form.fields.items() if field.required
        ]

        super().__init__(*args, **kwargs)

    def to_python(self, file):
        if file is None:
            return None

        csv_str = file.read().decode('utf-8').strip()
        reader = csv.reader(csv_str.splitlines())
        headers, records = parse_csv(reader)

        return headers, records

    def validate(self, value):
        if value is None:
            return None

        headers, records = value
        validate_csv(headers, self.fields, self.required_fields)

        return value


class CSVChoiceField(forms.ChoiceField):
    """
    Invert the provided set of choices to take the human-friendly label as input, and return the database value.
    """
    STATIC_CHOICES = True

    def __init__(self, *, choices=(), **kwargs):
        super().__init__(choices=choices, **kwargs)
        self.choices = unpack_grouped_choices(choices)


class CSVTypedChoiceField(forms.TypedChoiceField):
    STATIC_CHOICES = True


class CSVModelChoiceField(forms.ModelChoiceField):
    """
    Provides additional validation for model choices entered as CSV data.
    """
    default_error_messages = {
        'invalid_choice': 'Object not found.',
    }

    def to_python(self, value):
        try:
            return super().to_python(value)
        except MultipleObjectsReturned:
            raise forms.ValidationError(
                f'"{value}" is not a unique value for this field; multiple objects were found'
            )


class CSVContentTypeField(CSVModelChoiceField):
    """
    Reference a ContentType in the form <app>.<model>
    """
    STATIC_CHOICES = True

    def prepare_value(self, value):
        return f'{value.app_label}.{value.model}'

    def to_python(self, value):
        if not value:
            return None
        try:
            app_label, model = value.split('.')
        except ValueError:
            raise forms.ValidationError('Object type must be specified as "<app>.<model>"')
        try:
            return self.queryset.get(app_label=app_label, model=model)
        except ObjectDoesNotExist:
            raise forms.ValidationError('Invalid object type')


class CSVMultipleContentTypeField(forms.ModelMultipleChoiceField):
    STATIC_CHOICES = True

    # TODO: Improve validation of selected ContentTypes
    def prepare_value(self, value):
        if type(value) is str:
            ct_filter = Q()
            for name in value.split(','):
                app_label, model = name.split('.')
                ct_filter |= Q(app_label=app_label, model=model)
            return list(ContentType.objects.filter(ct_filter).values_list('pk', flat=True))
        return super().prepare_value(value)


#
# Expansion fields
#

class ExpandableNameField(forms.CharField):
    """
    A field which allows for numeric range expansion
      Example: 'Gi0/[1-3]' => ['Gi0/1', 'Gi0/2', 'Gi0/3']
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.help_text:
            self.help_text = """
                Alphanumeric ranges are supported for bulk creation. Mixed cases and types within a single range
                are not supported. Examples:
                <ul>
                    <li><code>[ge,xe]-0/0/[0-9]</code></li>
                    <li><code>e[0-3][a-d,f]</code></li>
                </ul>
                """

    def to_python(self, value):
        if not value:
            return ''
        if re.search(ALPHANUMERIC_EXPANSION_PATTERN, value):
            return list(expand_alphanumeric_pattern(value))
        return [value]


class ExpandableIPAddressField(forms.CharField):
    """
    A field which allows for expansion of IP address ranges
      Example: '192.0.2.[1-254]/24' => ['192.0.2.1/24', '192.0.2.2/24', '192.0.2.3/24' ... '192.0.2.254/24']
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.help_text:
            self.help_text = 'Specify a numeric range to create multiple IPs.<br />'\
                             'Example: <code>192.0.2.[1,5,100-254]/24</code>'

    def to_python(self, value):
        # Hackish address family detection but it's all we have to work with
        if '.' in value and re.search(IP4_EXPANSION_PATTERN, value):
            return list(expand_ipaddress_pattern(value, 4))
        elif ':' in value and re.search(IP6_EXPANSION_PATTERN, value):
            return list(expand_ipaddress_pattern(value, 6))
        return [value]


#
# Dynamic fields
#

class DynamicModelChoiceMixin:
    """
    :param query_params: A dictionary of additional key/value pairs to attach to the API request
    :param initial_params: A dictionary of child field references to use for selecting a parent field's initial value
    :param null_option: The string used to represent a null selection (if any)
    :param disabled_indicator: The name of the field which, if populated, will disable selection of the
        choice (optional)
    :param str fetch_trigger: The event type which will cause the select element to
        fetch data from the API. Must be 'load', 'open', or 'collapse'. (optional)
    """
    filter = django_filters.ModelChoiceFilter
    widget = widgets.APISelect

    def __init__(self, query_params=None, initial_params=None, null_option=None, disabled_indicator=None, fetch_trigger=None,
                 empty_label=None, *args, **kwargs):
        self.query_params = query_params or {}
        self.initial_params = initial_params or {}
        self.null_option = null_option
        self.disabled_indicator = disabled_indicator
        self.fetch_trigger = fetch_trigger

        # to_field_name is set by ModelChoiceField.__init__(), but we need to set it early for reference
        # by widget_attrs()
        self.to_field_name = kwargs.get('to_field_name')
        self.empty_option = empty_label or ""

        super().__init__(*args, **kwargs)

    def widget_attrs(self, widget):
        attrs = {
            'data-empty-option': self.empty_option
        }

        # Set value-field attribute if the field specifies to_field_name
        if self.to_field_name:
            attrs['value-field'] = self.to_field_name

        # Set the string used to represent a null option
        if self.null_option is not None:
            attrs['data-null-option'] = self.null_option

        # Set the disabled indicator, if any
        if self.disabled_indicator is not None:
            attrs['disabled-indicator'] = self.disabled_indicator

        # Set the fetch trigger, if any.
        if self.fetch_trigger is not None:
            attrs['data-fetch-trigger'] = self.fetch_trigger

        # Attach any static query parameters
        if (len(self.query_params) > 0):
            widget.add_query_params(self.query_params)

        return attrs

    def get_bound_field(self, form, field_name):
        bound_field = BoundField(form, self, field_name)

        # Set initial value based on prescribed child fields (if not already set)
        if not self.initial and self.initial_params:
            filter_kwargs = {}
            for kwarg, child_field in self.initial_params.items():
                if value := form.initial.get(child_field.lstrip('$')):
                    filter_kwargs[kwarg] = value
            if filter_kwargs:
                self.initial = self.queryset.filter(**filter_kwargs).first()

        if data := bound_field.value():
            field_name = getattr(self, 'to_field_name') or 'pk'
            filter = self.filter(field_name=field_name)
            try:
                self.queryset = filter.filter(self.queryset, data)
            except (TypeError, ValueError):
                # Catch any error caused by invalid initial data passed from the user
                self.queryset = self.queryset.none()
        else:
            self.queryset = self.queryset.none()

        # Set the data URL on the APISelect widget (if not already set)
        widget = bound_field.field.widget
        if not widget.attrs.get('data-url'):
            app_label = self.queryset.model._meta.app_label
            model_name = self.queryset.model._meta.model_name
            data_url = reverse(f'{app_label}-api:{model_name}-list')
            widget.attrs['data-url'] = data_url

        return bound_field


class DynamicModelChoiceField(DynamicModelChoiceMixin, forms.ModelChoiceField):
    """
    Override get_bound_field() to avoid pre-populating field choices with a SQL query. The field will be
    rendered only with choices set via bound data. Choices are populated on-demand via the APISelect widget.
    """

    def clean(self, value):
        """
        When null option is enabled and "None" is sent as part of a form to be submitted, it is sent as the
        string 'null'.  This will check for that condition and gracefully handle the conversion to a NoneType.
        """
        if self.null_option is not None and value == settings.FILTERS_NULL_CHOICE_VALUE:
            return None
        return super().clean(value)


class DynamicModelMultipleChoiceField(DynamicModelChoiceMixin, forms.ModelMultipleChoiceField):
    """
    A multiple-choice version of DynamicModelChoiceField.
    """
    filter = django_filters.ModelMultipleChoiceFilter
    widget = widgets.APISelectMultiple

    def clean(self, value):
        """
        When null option is enabled and "None" is sent as part of a form to be submitted, it is sent as the
        string 'null'.  This will check for that condition and gracefully handle the conversion to a NoneType.
        """
        if self.null_option is not None and settings.FILTERS_NULL_CHOICE_VALUE in value:
            value = [v for v in value if v != settings.FILTERS_NULL_CHOICE_VALUE]
            return [None, *value]
        return super().clean(value)
