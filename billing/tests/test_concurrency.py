"""
Races, run on real parallel connections: two requests reaching for the last
place, the last credit or the last use of a code must not both get it.
"""
import threading

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TransactionTestCase

from billing import gates, offers
from billing.catalog.keys import F
from billing.models import Campaign, Plan, PromoCode, PromoRedemption, Subscription, UsageCounter
from billing.testing import set_limit
from cashbook.models import CashBook
from workspaces.models import Workspace
from workspaces.services import create_workspace

User = get_user_model()


def in_parallel(count, work):
    """Run work(index) on `count` threads released together. Returns what each returned or raised."""
    start = threading.Barrier(count)
    results = [None] * count

    def run(index):
        try:
            start.wait(timeout=30)
            results[index] = work(index)
        except Exception as error:  # the outcome under test
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


class RaceTests(TransactionTestCase):
    # The default plans come from a migration; keep them across this class's table flushes
    serialized_rollback = True

    def setUp(self):
        self.alice = User.objects.create_user(email='alice@example.com', password='pass-12345')

    def test_the_last_credits_go_to_exactly_as_many_as_fit(self):
        results = in_parallel(12, lambda index: gates.take(self.alice, F.AI_CREDITS, 3, key=f'call-{index}'))
        taken = [result for result in results if not isinstance(result, Exception)]
        refused = [result for result in results if isinstance(result, gates.PlanLimit)]
        self.assertEqual((len(taken), len(refused)), (5, 7), results)  # 15 credits, 3 each
        self.assertEqual(UsageCounter.objects.get(user=self.alice, feature_key='ai.credits').used, 15)

    def test_one_retried_request_sent_twice_at_once_counts_once(self):
        results = in_parallel(6, lambda index: gates.take(self.alice, F.AI_CREDITS, 3, key='same-call'))
        self.assertFalse([result for result in results if isinstance(result, Exception)], results)
        self.assertEqual(len({event.pk for event in results}), 1, 'every caller is handed the one event')
        self.assertEqual(UsageCounter.objects.get(user=self.alice, feature_key='ai.credits').used, 3)

    def test_the_last_place_in_a_workspace_goes_to_one(self):
        shop = create_workspace(owner=self.alice, name='Shop')
        CashBook.objects.create(workspace=shop, book_name='Till 0')

        def create(index):
            with transaction.atomic():
                gates.check_limit(Workspace.objects.get(pk=shop.pk), F.BUSINESS_CASHBOOKS)
                return CashBook.objects.create(workspace=shop, book_name=f'Racing {index}')

        results = in_parallel(8, create)
        made = [result for result in results if isinstance(result, CashBook)]
        self.assertEqual(len(made), 1, results)  # Free allows 2, one existed
        self.assertEqual(CashBook.objects.filter(workspace=shop).count(), 2)

    def test_the_last_business_goes_to_one(self):
        def create(index):
            with transaction.atomic():
                gates.check_limit(User.objects.get(pk=self.alice.pk), F.BUSINESS_WORKSPACES)
                return create_workspace(owner=self.alice, name=f'Racing {index}')

        results = in_parallel(8, create)
        self.assertEqual(len([result for result in results if isinstance(result, Workspace)]), 1, results)
        self.assertEqual(Workspace.objects.filter(owner=self.alice, kind='business').count(), 1)

    def test_a_single_use_code_is_used_once(self):
        PromoCode.objects.create(
            code='ONLYONE1', kind='plan', benefit_plan=Plan.objects.get(code='plus'), benefit_days=7, max_redemptions=1,
        )
        users = [User.objects.create_user(email=f'racer{n}@example.com', password='pass-12345') for n in range(8)]
        results = in_parallel(8, lambda index: offers.redeem(users[index], 'ONLYONE1'))
        self.assertEqual(len([result for result in results if isinstance(result, PromoCode)]), 1, results)
        self.assertEqual(PromoRedemption.objects.count(), 1)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertEqual(PromoCode.objects.get(code='ONLYONE1').redeemed_count, 1)

    def test_one_person_cannot_use_a_code_twice_by_being_quick(self):
        PromoCode.objects.create(
            code='EVERYONE1', kind='plan', benefit_plan=Plan.objects.get(code='plus'), benefit_days=7,
        )
        results = in_parallel(6, lambda index: offers.redeem(self.alice, 'EVERYONE1'))
        self.assertEqual(len([result for result in results if isinstance(result, PromoCode)]), 1, results)
        self.assertEqual(Subscription.objects.filter(user=self.alice).count(), 1)

    def test_a_capped_campaign_is_claimed_as_often_as_the_cap(self):
        from datetime import timedelta

        from django.utils import timezone
        now = timezone.now()
        Campaign.objects.create(
            slug='first-three', name='First three', title='First three', is_active=True,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1),
            kind='plan', benefit_plan=Plan.objects.get(code='plus'), benefit_days=7, max_claims=3,
        )
        users = [User.objects.create_user(email=f'claimer{n}@example.com', password='pass-12345') for n in range(8)]
        results = in_parallel(8, lambda index: offers.claim(users[index], 'first-three'))
        self.assertEqual(len([result for result in results if isinstance(result, Campaign)]), 3, results)
        self.assertEqual(Subscription.objects.count(), 3)
        self.assertEqual(Campaign.objects.get(slug='first-three').claimed_count, 3)

    def test_a_top_up_with_one_key_lands_once(self):
        from billing import usage
        set_limit(self.alice, F.AI_CREDITS, 0)
        results = in_parallel(6, lambda index: usage.top_up(self.alice, F.AI_CREDITS, 5, 'reward-1'))
        self.assertEqual(len([result for result in results if result is True]), 1, results)
        self.assertEqual(UsageCounter.objects.get(user=self.alice, feature_key='ai.credits').bonus, 5)
