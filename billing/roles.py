"""
The two kinds of staff the billing admin is built for. A superuser can do
everything; put anyone else in one of these groups and tick "staff status".

- Billing admin: edits plans, features, campaigns, promo codes and settings.
- Support: looks at everything; grants a plan for up to 30 days, adds
  overrides and credits, revokes a subscription, clears a user's keep choice.
"""
BILLING_ADMIN = 'Billing admin'
SUPPORT = 'Support'

READ_ONLY_FOR_EVERYONE = ('usagecounter', 'usageevent', 'billingevent', 'funnelevent', 'promoredemption', 'campaignclaim', 'stamp')

SUPPORT_EXTRA = {
    'add_subscription', 'change_subscription',
    'add_entitlementoverride', 'change_entitlementoverride', 'delete_entitlementoverride',
    'delete_keepselection',
}
# Looking users up is part of both jobs
OTHER_APPS = {'identity': ('view_appuser',), 'workspaces': ('view_workspace', 'view_membership')}


def ensure_roles(sender=None, **kwargs):
    """
    Create the groups and give them their permissions. Runs after every
    migrate. It only ever adds, so permissions removed from a group by hand
    come back, and extra ones given by hand stay.
    """
    from django.contrib.auth.models import Group, Permission

    billing = list(Permission.objects.filter(content_type__app_label='billing'))
    if not billing:
        return  # the permissions are made by the same signal; next migrate will find them

    def codenames(permissions, wanted):
        return [permission for permission in permissions if wanted(permission.codename)]

    def model_of(codename):
        return codename.split('_', 1)[1]

    everything = codenames(
        billing,
        lambda code: code.startswith('view_') or model_of(code) not in READ_ONLY_FOR_EVERYONE,
    )
    support = codenames(billing, lambda code: code.startswith('view_') or code in SUPPORT_EXTRA)
    shared = [
        permission
        for app_label, wanted in OTHER_APPS.items()
        for permission in Permission.objects.filter(content_type__app_label=app_label, codename__in=wanted)
    ]

    Group.objects.get_or_create(name=BILLING_ADMIN)[0].permissions.add(*everything, *shared)
    Group.objects.get_or_create(name=SUPPORT)[0].permissions.add(*support, *shared)
