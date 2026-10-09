import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from workspaces.services import create_workspace, get_personal_workspace

User = get_user_model()

PUSH = '/api/v1/sync/push/'
ENTITLEMENTS = '/api/v1/billing/entitlements/'


def new_id():
    return str(uuid.uuid4())


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class BillingTestCase(TestCase):
    """Alice and Bob, both new and so on the Free plan. Alice has a business as well."""

    def setUp(self):
        self.alice = User.objects.create_user(email='alice@example.com', password='pass-12345')
        self.bob = User.objects.create_user(email='bob@example.com', password='pass-12345')
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)
        self.personal = get_personal_workspace(self.alice)
        self.shop = create_workspace(owner=self.alice, name='Shop')

    def age(self, rows):
        """
        Give the rows distinct creation times in this order, oldest first.
        "The oldest stay editable" is decided by creation time, and a fast
        machine can create two rows within one tick of its clock.
        """
        start = timezone.now() - timedelta(days=1)
        for position, row in enumerate(rows):
            type(row).all_objects.filter(pk=row.pk).update(created_at=start + timedelta(minutes=position))

    def push(self, client, workspace, *mutations):
        response = client.post(PUSH, {'workspace': str(workspace.id), 'mutations': list(mutations)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def upsert(self, table, row_id=None, **data):
        return {'id': new_id(), 'table': table, 'op': 'upsert', 'row_id': row_id or new_id(), 'data': data}

    def delete(self, table, row_id):
        return {'id': new_id(), 'table': table, 'op': 'delete', 'row_id': str(row_id)}

    def account(self, name='Wallet', **data):
        return self.upsert('accounts', name=name, kind='cash', currency='BDT', **data)

    def push_one(self, mutation, client=None, workspace=None):
        return self.push(client or self.alice_client, workspace or self.personal, mutation)[0]

    def assertApplied(self, result):
        self.assertEqual(result['status'], 'applied', result.get('error'))

    def assertPlanLimit(self, result, feature, reason=None):
        self.assertEqual(result['status'], 'rejected', result)
        self.assertEqual(result['error']['code'], 'plan_limit', result)
        self.assertEqual(result['error']['meta']['feature'], str(feature), result)
        if reason is not None:
            self.assertEqual(result['error']['meta']['reason'], reason, result)

    def entitlements(self, client=None):
        response = (client or self.alice_client).get(ENTITLEMENTS)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data
