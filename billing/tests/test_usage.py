from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from billing import gates, usage
from billing.catalog.keys import F
from billing.gates import PlanLimit
from billing.models import BillingSettings, FunnelEvent, UsageCounter, UsageEvent
from billing.testing import grant_plan, set_limit, set_mode

from .base import BillingTestCase


class QuotaTests(BillingTestCase):
    """Free has 15 AI credits a month."""

    def used(self, user=None):
        counter = UsageCounter.objects.filter(user=user or self.alice, feature_key='ai.credits').first()
        return counter.used if counter else 0

    def test_credits_are_counted_until_they_run_out(self):
        gates.take(self.alice, F.AI_CREDITS, 8, key='scan-1')
        gates.take(self.alice, F.AI_CREDITS, 7, key='scan-2')
        self.assertEqual(self.used(), 15)
        with self.assertRaises(PlanLimit) as refused:
            gates.take(self.alice, F.AI_CREDITS, 1, key='scan-3')
        self.assertEqual(refused.exception.status_code, 402)
        self.assertEqual(refused.exception.meta, {
            'feature': 'ai.credits', 'reason': 'quota', 'limit': 15, 'current': None,
            'plan': 'free', 'upgrade_to': 'plus',
        })
        self.assertEqual(self.used(), 15)
        self.assertFalse(UsageEvent.objects.filter(idempotency_key='scan-3').exists())
        self.assertEqual(self.used(self.bob), 0)

    def test_a_request_that_is_too_big_takes_nothing(self):
        gates.take(self.alice, F.AI_CREDITS, 10, key='a')
        with self.assertRaises(PlanLimit):
            gates.take(self.alice, F.AI_CREDITS, 8, key='b')
        self.assertEqual(self.used(), 10)
        gates.take(self.alice, F.AI_CREDITS, 5, key='c')

    def test_the_same_key_counts_once(self):
        first = gates.take(self.alice, F.AI_CREDITS, 3, key='retry-me')
        again = gates.take(self.alice, F.AI_CREDITS, 3, key='retry-me')
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(self.used(), 3)

    def test_giving_back_happens_once(self):
        gates.take(self.alice, F.AI_CREDITS, 8, key='failed-call')
        self.assertTrue(usage.give_back('failed-call'))
        self.assertFalse(usage.give_back('failed-call'))
        self.assertFalse(usage.give_back('never-taken'))
        self.assertEqual(self.used(), 0)
        self.assertIsNotNone(UsageEvent.objects.get(idempotency_key='failed-call').refunded_at)

    def test_consume_gives_back_when_the_work_fails_and_keeps_it_when_it_succeeds(self):
        with gates.consume(self.alice, F.AI_CREDITS, 3, key='ok'):
            pass
        self.assertEqual(self.used(), 3)
        with self.assertRaises(RuntimeError):
            with gates.consume(self.alice, F.AI_CREDITS, 8, key='model-down'):
                raise RuntimeError('model is down')
        self.assertEqual(self.used(), 3)

    def test_consume_does_not_run_the_work_when_refused(self):
        ran = []
        with self.assertRaises(PlanLimit):
            with gates.consume(self.alice, F.AI_CREDITS, 99, key='too-much'):
                ran.append(True)
        self.assertEqual(ran, [])

    def test_a_new_month_starts_from_zero(self):
        usage.take(self.alice, F.AI_CREDITS, 15, 'sept', 15, period='2026-09')
        self.assertEqual(usage.snapshot(self.alice, F.AI_CREDITS, 15, period='2026-09')['remaining'], 0)
        event, taken = usage.take(self.alice, F.AI_CREDITS, 15, 'oct', 15, period='2026-10')
        self.assertTrue(taken)

    def test_period_keys_follow_the_local_calendar(self):
        # 31 October 20:00 UTC is already 1 November in Dhaka
        moment = datetime(2026, 10, 31, 20, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(usage.period_key(moment), '2026-11')
        reset = usage.resets_at(datetime(2026, 12, 15, 6, 0, tzinfo=dt_timezone.utc))
        self.assertEqual((reset.year, reset.month, reset.day, reset.hour), (2027, 1, 1, 0))

    def test_a_top_up_adds_to_this_month_only_and_only_once(self):
        gates.take(self.alice, F.AI_CREDITS, 15, key='all')
        self.assertTrue(usage.top_up(self.alice, F.AI_CREDITS, 5, 'ad-1'))
        self.assertFalse(usage.top_up(self.alice, F.AI_CREDITS, 5, 'ad-1'))
        gates.take(self.alice, F.AI_CREDITS, 5, key='more')
        with self.assertRaises(PlanLimit):
            gates.take(self.alice, F.AI_CREDITS, 1, key='even-more')
        numbers = self.entitlements()['features']['ai.credits']
        self.assertEqual((numbers['limit'], numbers['bonus'], numbers['used'], numbers['remaining']), (15, 5, 20, 0))
        self.assertEqual(usage.snapshot(self.alice, F.AI_CREDITS, 15, period='2099-01')['remaining'], 15)

    def test_an_unlimited_quota_is_still_counted(self):
        set_limit(self.alice, F.AI_CREDITS, None)
        gates.take(self.alice, F.AI_CREDITS, 5000, key='big')
        self.assertEqual(self.used(), 5000)
        numbers = self.entitlements()['features']['ai.credits']
        self.assertEqual((numbers['unlimited'], numbers['remaining']), (True, None))

    def test_use_inside_a_business_is_charged_to_its_owner(self):
        grant_plan(self.bob, 'business')
        event = gates.take(self.shop, F.AI_CREDITS, 4, key='shop-scan', actor=self.bob)
        self.assertEqual((event.user, event.workspace, event.actor), (self.alice, self.shop, self.bob))
        self.assertEqual((self.used(self.alice), self.used(self.bob)), (4, 0))
        with self.assertRaises(PlanLimit):
            gates.take(self.shop, F.AI_CREDITS, 12, key='shop-scan-2', actor=self.bob)

    def test_the_payload_shows_what_is_left_and_when_it_refills(self):
        gates.take(self.alice, F.AI_CREDITS, 4, key='x')
        numbers = self.entitlements()['features']['ai.credits']
        self.assertEqual((numbers['kind'], numbers['limit'], numbers['used'], numbers['remaining']), ('quota', 15, 4, 11))
        self.assertGreater(datetime.fromisoformat(numbers['resets_at']), timezone.now())

    def test_log_only_lets_use_through_uncounted_and_notes_it(self):
        gates.take(self.alice, F.AI_CREDITS, 15, key='all')
        set_mode(BillingSettings.MODE_LOG_ONLY)
        self.assertIsNone(gates.take(self.alice, F.AI_CREDITS, 3, key='over'))
        self.assertEqual(self.used(), 15)
        self.assertTrue(FunnelEvent.objects.filter(feature_key='ai.credits', enforced=False).exists())

    def test_amounts_must_be_positive(self):
        for amount in (0, -5):
            with self.assertRaises(ValueError):
                gates.take(self.alice, F.AI_CREDITS, amount, key=f'bad{amount}')
            with self.assertRaises(ValueError):
                usage.top_up(self.alice, F.AI_CREDITS, amount, f'bad-top{amount}')
        self.assertEqual(self.used(), 0)
