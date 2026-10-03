import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from cashbook.models import CashBook, CashBookAdditionalMember, Entry, EntryCategory
from ledger_personal.models import Account, Category, Transaction
from workspaces.models import Membership
from workspaces.services import create_workspace, get_personal_workspace
from workspaces.tests import UnprivilegedRoleMixin

User = get_user_model()

PULL = '/api/v1/sync/pull/'
PUSH = '/api/v1/sync/push/'


def new_id():
    return str(uuid.uuid4())


class SyncTestCase(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email='alice@example.com', password='pass-12345')
        self.bob = User.objects.create_user(email='bob@example.com', password='pass-12345')
        self.alice_client = APIClient()
        self.alice_client.force_authenticate(self.alice)
        self.bob_client = APIClient()
        self.bob_client.force_authenticate(self.bob)
        self.personal = get_personal_workspace(self.alice)
        self.shop = create_workspace(owner=self.alice, name='Shop')

    def push(self, client, workspace, *mutations):
        response = client.post(PUSH, {'workspace': str(workspace.id), 'mutations': list(mutations)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def pull(self, client, workspace, since=0, **params):
        response = client.get(PULL, {'workspace': str(workspace.id), 'since': since, **params})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def upsert(self, table, row_id=None, **data):
        return {'id': new_id(), 'table': table, 'op': 'upsert', 'row_id': row_id or new_id(), 'data': data}

    def delete(self, table, row_id):
        return {'id': new_id(), 'table': table, 'op': 'delete', 'row_id': row_id}

    def push_book_with_entry(self, client=None, workspace=None):
        """Returns (book mutation, entry mutation, results)"""
        book = self.upsert('cashbooks', book_name='Till', currency='BDT')
        entry = self.upsert(
            'entries', cashbook_id=book['row_id'], entry_type='cash_in', amount_minor=5000,
            entry_date='2026-10-01', title='Sale',
        )
        results = self.push(client or self.alice_client, workspace or self.shop, book, entry)
        return book, entry, results


class PushTests(SyncTestCase):
    def test_create_with_client_ids(self):
        book, entry, results = self.push_book_with_entry()
        self.assertEqual([r['status'] for r in results], ['applied', 'applied'])
        saved = Entry.objects.get(id=entry['row_id'])
        self.assertEqual((saved.amount_minor, saved.currency, saved.created_by), (5000, 'BDT', self.alice))
        self.assertEqual(saved.workspace, self.shop)
        # The response carries the server's row so the client can match it
        self.assertEqual(results[1]['row']['version'], 1)
        self.assertGreater(results[1]['row']['server_seq'], results[0]['row']['server_seq'])

    def test_replayed_mutation_is_not_applied_twice(self):
        book, entry, _ = self.push_book_with_entry()
        edit = self.upsert('entries', entry['row_id'], amount_minor=700)
        first = self.push(self.alice_client, self.shop, edit)
        second = self.push(self.alice_client, self.shop, edit)
        self.assertEqual(first[0]['status'], 'applied')
        self.assertEqual(second[0]['status'], 'applied')
        self.assertEqual(Entry.objects.get(id=entry['row_id']).version, 2)

    def test_edits_to_different_fields_both_survive(self):
        book, entry, _ = self.push_book_with_entry()
        self.push(self.alice_client, self.shop, self.upsert('entries', entry['row_id'], amount_minor=900))
        self.push(self.alice_client, self.shop, self.upsert('entries', entry['row_id'], title='Corrected'))
        saved = Entry.objects.get(id=entry['row_id'])
        self.assertEqual((saved.amount_minor, saved.title, saved.version), (900, 'Corrected', 3))

    def test_delete_is_a_tombstone_and_wins_over_a_later_edit(self):
        book, entry, _ = self.push_book_with_entry()
        results = self.push(
            self.alice_client, self.shop,
            self.delete('entries', entry['row_id']),
            self.delete('entries', entry['row_id']),
            self.upsert('entries', entry['row_id'], amount_minor=1),
        )
        self.assertEqual([r['status'] for r in results], ['applied', 'applied', 'rejected'])
        self.assertEqual(results[2]['error']['code'], 'deleted')
        self.assertIsNotNone(results[2]['row']['deleted_at'])
        self.assertEqual(Entry.all_objects.get(id=entry['row_id']).amount_minor, 5000)

    def test_invalid_rows_are_rejected_without_stopping_the_batch(self):
        book = self.upsert('cashbooks', book_name='Till', currency='BDT')
        bad_amounts = [
            self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_in', amount_minor=amount,
                        entry_date='2026-10-01')
            for amount in (10.5, '100', -5, 0, True)
        ]
        bad_date = self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_in', amount_minor=5,
                               entry_date='yesterday')
        good = self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_out', amount_minor=5,
                           entry_date='2026-10-01')
        results = self.push(self.alice_client, self.shop, book, *bad_amounts, bad_date, good)
        self.assertEqual([r['status'] for r in results], ['applied'] + ['rejected'] * 6 + ['applied'])
        self.assertTrue(all(r['error']['code'] == 'invalid' for r in results[1:7]))
        self.assertEqual(Entry.objects.count(), 1)

    def test_currency_and_parent_cannot_change(self):
        book, entry, _ = self.push_book_with_entry()
        other = self.upsert('cashbooks', book_name='Safe', currency='BDT')
        results = self.push(
            self.alice_client, self.shop, other,
            self.upsert('cashbooks', book['row_id'], currency='USD'),
            self.upsert('entries', entry['row_id'], cashbook_id=other['row_id']),
        )
        self.assertEqual([r.get('error', {}).get('code') for r in results], [None, 'immutable', 'immutable'])

    def test_server_owned_columns_are_ignored(self):
        book, entry, _ = self.push_book_with_entry()
        self.push(self.alice_client, self.shop, self.upsert(
            'entries', entry['row_id'], workspace_id=str(self.personal.id), version=99,
            created_by_id=str(self.bob.id), currency='USD', deleted_at='2020-01-01T00:00:00Z',
        ))
        saved = Entry.objects.get(id=entry['row_id'])
        self.assertEqual((saved.workspace, saved.version, saved.created_by, saved.currency),
                         (self.shop, 2, self.alice, 'BDT'))

    def test_personal_ledger_tables(self):
        account = Account.objects.get(workspace=self.personal)
        category = Category.objects.filter(workspace=self.personal, kind='expense').first()
        savings = self.upsert('accounts', name='Savings', kind='savings', currency='BDT')
        group = new_id()
        results = self.push(
            self.alice_client, self.personal, savings,
            self.upsert('transactions', account_id=str(account.id), category_id=str(category.id), kind='expense',
                        amount_minor=-2500, occurred_on='2026-10-01', note='Lunch'),
            self.upsert('transactions', account_id=str(account.id), kind='transfer', amount_minor=-10000,
                        transfer_group_id=group, occurred_on='2026-10-01'),
            self.upsert('transactions', account_id=savings['row_id'], kind='transfer', amount_minor=10000,
                        transfer_group_id=group, occurred_on='2026-10-01'),
            self.upsert('budgets', category_id=str(category.id), amount_minor=500000, currency='BDT'),
            # An expense must be negative, and a transfer needs its group
            self.upsert('transactions', account_id=str(account.id), kind='expense', amount_minor=2500,
                        occurred_on='2026-10-01'),
            self.upsert('transactions', account_id=str(account.id), kind='transfer', amount_minor=-1,
                        occurred_on='2026-10-01'),
        )
        self.assertEqual([r['status'] for r in results], ['applied'] * 5 + ['rejected'] * 2)
        self.assertEqual(Transaction.objects.filter(workspace=self.personal).count(), 3)
        self.assertEqual(sum(t.amount_minor for t in Transaction.objects.filter(transfer_group_id=group)), 0)


class PushPermissionTests(SyncTestCase):
    def test_outsider_cannot_push_or_pull(self):
        self.assertEqual(self.bob_client.get(PULL, {'workspace': str(self.shop.id)}).status_code, 404)
        response = self.bob_client.post(PUSH, {'workspace': str(self.shop.id), 'mutations': []}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_cannot_write_rows_of_another_workspace_through_own(self):
        book, entry, _ = self.push_book_with_entry()
        bob_personal = get_personal_workspace(self.bob)
        results = self.push(
            self.bob_client, bob_personal,
            self.upsert('entries', entry['row_id'], amount_minor=1),
            self.delete('entries', entry['row_id']),
            self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_in', amount_minor=1,
                        entry_date='2026-10-01'),
        )
        self.assertEqual([r['status'] for r in results], ['rejected'] * 3)
        self.assertTrue(all(r['row'] is None for r in results))
        saved = Entry.objects.get(id=entry['row_id'])
        self.assertEqual((saved.amount_minor, saved.deleted_at), (5000, None))

    def test_category_from_another_book_is_rejected(self):
        book, entry, _ = self.push_book_with_entry()
        other = CashBook.objects.create(workspace=self.shop, book_name='Safe')
        foreign = EntryCategory.objects.create(cashbook=other, category_name='Rent')
        results = self.push(self.alice_client, self.shop,
                            self.upsert('entries', entry['row_id'], category_id=str(foreign.id)))
        self.assertEqual(results[0]['error']['code'], 'invalid')

    def test_staff_roles(self):
        book, entry, _ = self.push_book_with_entry()
        safe = CashBook.objects.create(workspace=self.shop, book_name='Safe')
        Membership.objects.create(workspace=self.shop, user=self.bob, role=Membership.ROLE_STAFF)
        CashBookAdditionalMember.objects.create(cashbook_id=book['row_id'], member=self.bob, role='editor')

        results = self.push(
            self.bob_client, self.shop,
            self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_out', amount_minor=100,
                        entry_date='2026-10-01'),                                    # editor may add entries
            self.upsert('entries', cashbook_id=str(safe.id), entry_type='cash_out', amount_minor=100,
                        entry_date='2026-10-01'),                                    # not in a book without a grant
            self.upsert('entry_categories', cashbook_id=book['row_id'], category_name='X'),  # admin only
            self.upsert('cashbooks', book_name='Mine', currency='BDT'),              # managers only
            self.delete('cashbooks', book['row_id']),                                # owner only
            self.upsert('accounts', name='Wallet', currency='BDT'),                  # managers only
        )
        self.assertEqual([r['status'] for r in results], ['applied'] + ['rejected'] * 5)
        self.assertEqual([r['error']['code'] for r in results[1:]], ['forbidden'] * 5)


class PullTests(SyncTestCase):
    def test_pull_returns_changes_after_cursor_including_tombstones(self):
        book, entry, _ = self.push_book_with_entry()
        first = self.pull(self.alice_client, self.shop)
        self.assertEqual([r['id'] for r in first['changes']['cashbooks']], [uuid.UUID(book['row_id'])])
        self.assertEqual(first['changes']['entries'][0]['amount_minor'], 5000)
        self.assertFalse(first['has_more'])
        self.assertEqual(first['accessible_cashbook_ids'], [uuid.UUID(book['row_id'])])

        # Nothing new
        again = self.pull(self.alice_client, self.shop, since=first['next_since'])
        self.assertTrue(all(rows == [] for rows in again['changes'].values()))
        self.assertEqual(again['next_since'], first['next_since'])

        self.push(self.alice_client, self.shop, self.delete('entries', entry['row_id']))
        after = self.pull(self.alice_client, self.shop, since=first['next_since'])
        self.assertEqual(after['changes']['cashbooks'], [])
        self.assertIsNotNone(after['changes']['entries'][0]['deleted_at'])

    def test_bulk_updates_still_move_the_cursor(self):
        book, entry, _ = self.push_book_with_entry()
        cursor = self.pull(self.alice_client, self.shop)['next_since']
        Entry.objects.filter(id=entry['row_id']).update(title='Edited in admin')
        changed = self.pull(self.alice_client, self.shop, since=cursor)['changes']['entries']
        self.assertEqual([row['title'] for row in changed], ['Edited in admin'])

    def test_pull_pages_through_everything_exactly_once(self):
        book = self.upsert('cashbooks', book_name='Till', currency='BDT')
        entries = [
            self.upsert('entries', cashbook_id=book['row_id'], entry_type='cash_in', amount_minor=i + 1,
                        entry_date='2026-10-01')
            for i in range(7)
        ]
        self.push(self.alice_client, self.shop, book, *entries)

        seen, since, pages = [], 0, 0
        while True:
            page = self.pull(self.alice_client, self.shop, since=since, limit=3)
            seen += [str(row['id']) for row in page['changes']['entries']]
            since, pages = page['next_since'], pages + 1
            if not page['has_more']:
                break
        self.assertEqual(sorted(seen), sorted(e['row_id'] for e in entries))
        self.assertGreater(pages, 2)

    def test_personal_workspace_starts_with_defaults(self):
        changes = self.pull(self.alice_client, self.personal)['changes']
        self.assertEqual([a['name'] for a in changes['accounts']], ['Cash'])
        self.assertEqual(len(changes['categories']), len(Category.DEFAULT_EXPENSE) + len(Category.DEFAULT_INCOME))

    def test_staff_only_receive_granted_books(self):
        book, entry, _ = self.push_book_with_entry()
        safe = CashBook.objects.create(workspace=self.shop, book_name='Safe')
        Entry.objects.create(cashbook=safe, amount_minor=1, entry_date='2026-10-01')
        Account.objects.create(workspace=self.shop, name='Owner wallet')
        Membership.objects.create(workspace=self.shop, user=self.bob, role=Membership.ROLE_STAFF)
        grant = CashBookAdditionalMember.objects.create(cashbook_id=book['row_id'], member=self.bob, role='viewer')

        data = self.pull(self.bob_client, self.shop)
        self.assertEqual([str(r['id']) for r in data['changes']['cashbooks']], [book['row_id']])
        self.assertEqual([str(r['id']) for r in data['changes']['entries']], [entry['row_id']])
        self.assertEqual(data['changes']['accounts'], [])
        self.assertEqual(data['accessible_cashbook_ids'], [uuid.UUID(book['row_id'])])

        grant.soft_delete()
        data = self.pull(self.bob_client, self.shop)
        self.assertEqual(data['accessible_cashbook_ids'], [])
        self.assertEqual(data['changes']['entries'], [])


class DemoBusinessTests(SyncTestCase):
    def test_demo_business_is_created_once_and_can_be_deleted(self):
        response = self.alice_client.post('/api/v1/workspaces/demo/')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['is_demo'])
        self.assertEqual(self.alice_client.post('/api/v1/workspaces/demo/').data['id'], response.data['id'])

        demo_id = response.data['id']
        changes = self.alice_client.get(PULL, {'workspace': demo_id}).data['changes']
        self.assertEqual(len(changes['cashbooks']), 1)
        self.assertEqual(len(changes['entries']), 12)

        self.assertEqual(self.bob_client.delete(f'/api/v1/workspaces/{demo_id}/').status_code, 404)
        self.assertEqual(self.alice_client.delete(f'/api/v1/workspaces/{demo_id}/').status_code, 204)
        self.assertEqual(self.alice_client.delete(f'/api/v1/workspaces/{self.personal.id}/').status_code, 403)


class UnprivilegedRoleEndToEndTests(UnprivilegedRoleMixin, SyncTestCase):
    """
    The same flows on a database role that row-level security applies to,
    which is how production runs. Catches code that only works as a superuser.
    """

    def setUp(self):
        super().setUp()
        self.use_unprivileged_role()

    def test_signup_seed_push_pull_and_rest(self):
        # Created under RLS: the personal-workspace seed has to pass the policies
        carol = User.objects.create_user(email='carol@example.com', password='pass-12345')
        client = APIClient()
        client.force_authenticate(carol)
        personal = get_personal_workspace(carol)
        self.assertEqual(len(self.pull(client, personal)['changes']['accounts']), 1)

        demo = client.post('/api/v1/workspaces/demo/')
        self.assertEqual(demo.status_code, 201, demo.data)

        book, entry, results = self.push_book_with_entry()
        self.assertEqual([r['status'] for r in results], ['applied', 'applied'])
        self.assertEqual(len(self.pull(self.alice_client, self.shop)['changes']['entries']), 1)

        created = self.alice_client.post('/api/v1/cashbooks/', {'book_name': 'Bank', 'workspace': str(self.shop.id)})
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(len(self.alice_client.get('/api/v1/cashbooks/').data['results']), 2)

        # Bob still sees nothing of Alice's
        results = self.push(self.bob_client, get_personal_workspace(self.bob),
                            self.upsert('entries', entry['row_id'], amount_minor=1))
        self.assertEqual(results[0]['status'], 'rejected')
        self.assertEqual(self.bob_client.get('/api/v1/cashbooks/').data['results'], [])
