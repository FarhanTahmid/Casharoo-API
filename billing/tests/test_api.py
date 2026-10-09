from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.catalog.keys import ALL, F
from billing.entitlements import resolve
from billing.models import BillingEvent, BillingSettings, Feature, FunnelEvent, Plan, Stamp, Subscription
from billing.testing import grant_plan, set_limit, set_mode, set_plan_value
from ledger_personal.models import Account

from .base import ENTITLEMENTS, BillingTestCase, User, client_for

ME = '/api/v1/me/'
PLANS = '/api/v1/billing/plans/'
EVENTS = '/api/v1/billing/events/'
SIMULATE = '/api/v1/billing/dev/simulate/'
PULL = '/api/v1/sync/pull/'


class EntitlementsPayloadTests(BillingTestCase):
    def test_a_free_user_sees_their_plan_and_every_feature(self):
        body = self.entitlements()
        self.assertEqual(body['plan'], {
            'code': 'free', 'name': 'Free', 'name_bn': 'ফ্রি', 'rank': 0,
            'tagline': Plan.objects.get(code='free').tagline, 'tagline_bn': Plan.objects.get(code='free').tagline_bn,
        })
        self.assertEqual((body['source'], body['expires_at'], body['in_grace']), ('default', None, False))
        self.assertEqual(set(body['features']), {feature.key for feature in ALL})
        self.assertEqual(body['features']['personal.accounts'], {'kind': 'limit', 'limit': 4, 'unlimited': False})
        self.assertEqual(body['features']['budgets.month_override'], {'kind': 'flag', 'enabled': False})
        self.assertEqual(body['locks'], [])
        self.assertEqual(body['offers'], [])
        self.assertEqual((body['offline_grace_days'], body['warn_at_percent']), (3, 75))
        self.assertEqual(len(body['version']), 16)

    def test_a_paid_user_sees_the_end_date(self):
        subscription = grant_plan(self.alice, 'plus', days=30)
        body = self.entitlements()
        self.assertEqual((body['plan']['code'], body['source']), ('plus', 'grant'))
        self.assertEqual(body['expires_at'], subscription.current_period_end.isoformat())
        self.assertEqual(body['features']['personal.accounts'], {'kind': 'limit', 'limit': None, 'unlimited': True})

    def test_the_version_moves_only_when_something_the_app_shows_moves(self):
        first = self.entitlements()['version']
        self.assertEqual(self.entitlements()['version'], first)
        set_limit(self.alice, F.PERSONAL_ACCOUNTS, 9)
        self.assertNotEqual(self.entitlements()['version'], first)

    def test_with_enforcement_off_the_app_is_told_to_refuse_and_lock_nothing(self):
        subscription = grant_plan(self.alice, 'plus')
        for number in range(6):
            Account.objects.create(workspace=self.personal, name=f'Account {number}', kind='cash', currency='BDT')
        subscription.status = Subscription.STATUS_REVOKED
        subscription.save()
        body = self.entitlements()
        self.assertTrue(body['enforced'])
        self.assertEqual([lock['feature'] for lock in body['locks']], ['personal.accounts'])

        for mode in (BillingSettings.MODE_LOG_ONLY, BillingSettings.MODE_OFF):
            set_mode(mode)
            body = self.entitlements()
            self.assertFalse(body['enforced'], mode)
            self.assertEqual(body['locks'], [], mode)
            # What the plan gives is still shown
            self.assertEqual(body['features']['personal.accounts']['limit'], 4, mode)

    def test_a_hidden_feature_is_not_sent(self):
        Feature.objects.filter(key=F.DEVICES_MAX.key).update(client_visible=False)
        self.assertNotIn('devices.max', self.entitlements()['features'])
        self.assertNotIn('devices.max', self.alice_client.get(PLANS).data['plans'][0]['features'])

    def test_it_needs_a_session(self):
        for path in (ENTITLEMENTS, PLANS, '/api/v1/billing/keep/'):
            self.assertIn(APIClient().get(path).status_code, (401, 403), path)
        self.assertIn(APIClient().post('/api/v1/billing/promo/redeem/', {'code': 'X'}).status_code, (401, 403))

    def test_me_carries_the_same_entitlements_and_cannot_be_used_to_change_them(self):
        response = self.alice_client.get(ME)
        self.assertEqual(response.data['entitlements']['version'], self.entitlements()['version'])

        patched = self.alice_client.patch(ME, {
            'first_name': 'Alice',
            'entitlements': {'plan': {'code': 'business'}, 'features': {'personal.accounts': {'unlimited': True}}},
        }, format='json')
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data['first_name'], 'Alice')
        self.assertEqual(patched.data['entitlements']['plan']['code'], 'free')
        self.assertEqual(resolve(User.objects.get(pk=self.alice.pk)).plan.code, 'free')


class AdsTests(BillingTestCase):
    def test_a_new_free_user_has_a_quiet_first_week(self):
        ads = self.entitlements()['ads']
        self.assertFalse(ads['enabled'])
        starts = timezone.datetime.fromisoformat(ads['starts_at'])
        self.assertEqual(starts, self.alice.date_joined + timedelta(days=7))
        self.assertIn('overview', ads['placements'])

    def test_after_the_first_week_free_shows_ads_and_paid_never_loads_them(self):
        User.objects.filter(pk__in=[self.alice.pk, self.bob.pk]).update(date_joined=timezone.now() - timedelta(days=8))
        self.alice.refresh_from_db()
        self.bob.refresh_from_db()
        ads = self.entitlements(client_for(self.alice))['ads']
        self.assertEqual((ads['enabled'], ads['starts_at']), (True, None))

        grant_plan(self.bob, 'plus')
        self.assertEqual(self.entitlements(client_for(self.bob))['ads'], {'enabled': False, 'starts_at': None, 'placements': []})

    def test_the_admin_tunes_ads_without_a_release(self):
        settings = BillingSettings.load()
        settings.ads_honeymoon_days, settings.ads_placements = 0, ['accounts']
        settings.save()
        self.assertEqual(self.entitlements()['ads'], {'enabled': True, 'starts_at': None, 'placements': ['accounts']})


class PlansEndpointTests(BillingTestCase):
    def test_public_plans_with_what_each_gives_cheapest_first(self):
        body = self.alice_client.get(PLANS).data
        self.assertEqual([plan['code'] for plan in body['plans']], ['free', 'plus', 'business'])
        business = body['plans'][2]
        self.assertEqual(business['features']['team.seats'], {'kind': 'limit', 'limit': 5, 'unlimited': False})
        self.assertEqual(business['features']['history.audit_trail'], {'kind': 'flag', 'enabled': True})
        names = {feature['key']: feature for feature in body['features']}
        self.assertEqual(names['storage.attachments_mb']['unit'], 'MB')

    def test_a_plan_made_in_the_admin_appears_and_a_hidden_one_does_not(self):
        gold = Plan.objects.create(code='gold', name='Gold', rank=30, sort=30)
        set_plan_value('gold', F.TEAM_SEATS, limit=20)
        Plan.objects.create(code='staff-only', name='Internal', rank=99, is_public=False)
        Plan.objects.create(code='retired', name='Retired', rank=5, is_active=False)
        body = self.alice_client.get(PLANS).data
        self.assertEqual([plan['code'] for plan in body['plans']], ['free', 'plus', 'business', 'gold'])
        self.assertEqual(body['plans'][3]['features']['team.seats']['limit'], 20)
        # A hidden plan still works for whoever was given it
        grant_plan(self.alice, 'staff-only')
        self.assertEqual(self.entitlements()['plan']['code'], 'staff-only')
        self.assertEqual(gold.values.count(), 1)


class FunnelEventTests(BillingTestCase):
    def test_the_app_reports_what_it_showed(self):
        response = self.alice_client.post(EVENTS, {'kind': 'paywall_view', 'feature': 'personal.accounts'}, format='json')
        self.assertEqual(response.status_code, 204)
        event = FunnelEvent.objects.get()
        self.assertEqual((event.user, event.kind, event.feature_key, event.plan_code, event.origin),
                         (self.alice, 'paywall_view', 'personal.accounts', 'free', 'app'))

    def test_it_cannot_report_things_only_the_server_knows(self):
        for kind in ('purchase', 'redeem', 'limit_hit', 'claim', '', None):
            self.assertEqual(self.alice_client.post(EVENTS, {'kind': kind}, format='json').status_code, 400, kind)
        self.assertFalse(FunnelEvent.objects.exists())
        self.assertEqual(resolve(self.alice).plan.code, 'free')

    def test_an_unknown_feature_name_is_dropped(self):
        self.alice_client.post(EVENTS, {'kind': 'upgrade_tap', 'feature': 'x' * 5000}, format='json')
        self.assertEqual(FunnelEvent.objects.get().feature_key, '')


class StampTests(BillingTestCase):
    def stamp(self, client=None):
        response = (client or self.alice_client).get(PULL, {'workspace': str(self.personal.id), 'since': 0})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['billing_stamp']

    def test_a_pull_tells_the_app_when_to_fetch_its_entitlements_again(self):
        first = self.stamp()
        self.assertEqual(self.stamp(), first)

        grant_plan(self.alice, 'plus')
        after_grant = self.stamp()
        self.assertNotEqual(after_grant, first)

        set_plan_value('plus', F.BUSINESS_WORKSPACES, limit=3)
        after_plan_edit = self.stamp()
        self.assertNotEqual(after_plan_edit, after_grant)

        settings = BillingSettings.load()
        settings.warn_at_percent = 90
        settings.save()
        self.assertNotEqual(self.stamp(), after_plan_edit)

    def test_one_users_change_does_not_wake_everyone(self):
        bob_before = Stamp.current(self.bob.pk)
        grant_plan(self.alice, 'plus')
        set_limit(self.alice, F.AI_CREDITS, 99)
        self.assertEqual(Stamp.current(self.bob.pk), bob_before)


class DevProviderTests(BillingTestCase):
    def simulate(self, **body):
        return self.alice_client.post(SIMULATE, body, format='json')

    def test_a_purchase_and_its_whole_life(self):
        bought = self.simulate(action='purchase', plan='plus', period='yearly')
        self.assertEqual(bought.status_code, 200, bought.data)
        self.assertEqual((bought.data['plan']['code'], bought.data['source']), ('plus', 'store'))
        subscription = Subscription.objects.get(user=self.alice)
        self.assertEqual((subscription.provider, subscription.product.period), ('dev', 'yearly'))
        self.assertAlmostEqual(
            (subscription.current_period_end - timezone.now()).days, 364, delta=1,
        )
        self.assertTrue(FunnelEvent.objects.filter(user=self.alice, kind='purchase', plan_code='plus').exists())

        cancelled = self.simulate(action='cancel')
        self.assertEqual(cancelled.data['plan']['code'], 'plus')
        self.assertTrue(Subscription.objects.get(user=self.alice).cancel_at_period_end)

        expired = self.simulate(action='expire')
        self.assertEqual((expired.data['plan']['code'], expired.data['in_grace']), ('plus', True))

        renewed = self.simulate(action='renew')
        self.assertEqual((renewed.data['plan']['code'], renewed.data['in_grace']), ('plus', False))

        refunded = self.simulate(action='refund')
        self.assertEqual((refunded.data['plan']['code'], refunded.data['source']), ('free', 'default'))
        self.assertEqual(Subscription.objects.filter(user=self.alice).count(), 1, 'one purchase, one row')
        self.assertEqual(BillingEvent.objects.filter(provider='dev', status='processed').count(), 5)

    def test_bad_requests(self):
        self.assertEqual(self.simulate(action='renew').status_code, 400)
        self.assertEqual(self.simulate(action='purchase', plan='gold').status_code, 400)
        self.assertEqual(self.simulate(action='purchase', plan='plus', period='weekly').status_code, 400)
        self.assertEqual(self.simulate(action='steal').status_code, 400)
        self.assertFalse(Subscription.objects.exists())

    def test_it_only_acts_for_the_caller(self):
        self.simulate(action='purchase', plan='business', user=str(self.bob.id))
        self.assertEqual((resolve(self.alice).plan.code, resolve(self.bob).plan.code), ('business', 'free'))

    @override_settings(BILLING_DEV_TOOLS=False)
    def test_the_view_refuses_where_dev_tools_are_off_even_if_it_were_routed(self):
        self.assertEqual(self.simulate(action='purchase', plan='business').status_code, 404)
        self.assertEqual(resolve(self.alice).plan.code, 'free')
