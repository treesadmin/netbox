from django import forms

from utilities.forms import BootstrapMixin

OBJ_TYPE_CHOICES = (
    ('', 'All Objects'),
    ('Circuits', (
        ('provider', 'Providers'),
        ('circuit', 'Circuits'),
    )),
    ('DCIM', (
        ('site', 'Sites'),
        ('rack', 'Racks'),
        ('rackreservation', 'Rack reservations'),
        ('location', 'Locations'),
        ('devicetype', 'Device Types'),
        ('device', 'Devices'),
        ('virtualchassis', 'Virtual chassis'),
        ('cable', 'Cables'),
        ('powerfeed', 'Power feeds'),
    )),
    ('IPAM', (
        ('vrf', 'VRFs'),
        ('aggregate', 'Aggregates'),
        ('prefix', 'Prefixes'),
        ('ipaddress', 'IP Addresses'),
        ('vlan', 'VLANs'),
    )),
    ('Tenancy', (
        ('tenant', 'Tenants'),
    )),
    ('Virtualization', (
        ('cluster', 'Clusters'),
        ('virtualmachine', 'Virtual Machines'),
    )),
)


def build_options():
    options = [{"label": OBJ_TYPE_CHOICES[0][1], "items": []}]

    for label, choices in OBJ_TYPE_CHOICES[1:]:
        items = [
            {"label": choice_label, "value": value}
            for value, choice_label in choices
        ]


        options.append({"label": label, "items": items})
    return options


class SearchForm(BootstrapMixin, forms.Form):
    q = forms.CharField(
        label='Search'
    )
    obj_type = forms.ChoiceField(
        choices=OBJ_TYPE_CHOICES, required=False, label='Type'
    )
    options = build_options()
