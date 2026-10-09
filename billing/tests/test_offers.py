from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from billing import offers
from billing.entitlements import resolve
from billing.models import Campaign, CampaignClaim, Feature, FunnelEvent, Plan, PromoCode, PromoRedemption, Subscription
from billing.testing import grant_plan

from .base import BillingTestCase, User, client_for

REDEEM = '/api/v1/billing/promo/redeem/'


def plus():
    return Plan.objects.get(code='plus')


def credits():
    return Feature.objects.get(key='ai.credits')


class PromoCodeTests(BillingTestCase):
    def code(self, **fields):
        defaults = {'code': 'WELCOME30', 'kind': 'plan', 'benefit_plan': plus(), 'benefit_days': 30}
        return PromoCode.objects.create(**{**defaults, **fields})

    def test_a_plan_code_gives_the_plan_for_its_days(self):
        promo = self.code()
        offers.redeem(self.alice, 'WELCOME30')
        entitlements = resolve(self.alice)
        self.assertEqual((entitlements.plan.code, entitlements.source), ('plus', 'promo_code'))
        self.assertAlmostEqual(
            (entitlements.expires_at - timezone.now()).total_seconds(), timedelta(days=30).total_seconds(), delta=60,
        )
        subscription = Subscription.objects.get(user=self.alice)
        self.assertEqual((subscription.promo_code, subscription.reason), (promo, 'promo code WELCOME30'))
        self.assertEqual(PromoCode.objects.get(pk=promo.pk).redeemed_count, 1)
        self.assertTrue(FunnelEvent.objects.filter(user=self.alice, kind='redeem').exists())
        self.assertEqual(resolve(self.bob).plan.code, 'free')

    def test_a_code_is_typed_by_people(self):
        self.code()
        offers.redeem(self.alice, '  welcome 30 ')
        self.assertEqual(resolve(self.alice).plan.code, 'plus')

    def test_one_use_per_person(self):
        self.code()
        offers.redeem(self.alice, 'WELCOME30')
        with self.assertRaisesMessage(offers.OfferError, 'already used'):
            offers.redeem(self.alice, 'WELCOME30')
        self.assertEqual(Subscription.objects.filter(user=self.alice).count(), 1)
        offers.redeem(self.bob, 'WELCOME30')

    def test_every_dead_code_gets_the_same_answer(self):
        now = timezone.now()
        self.code(code='ENDED1', ends_at=now - timedelta(minutes=1))
        self.code(code='LATER1', starts_at=now + timedelta(days=1))
        self.code(code='TURNEDOFF', is_active=False)
        self.code(code='USEDUP', max_redemptions=1)
        offers.redeem(self.bob, 'USEDUP')
        for code in ('ENDED1', 'LATER1', 'TURNEDOFF', 'USEDUP', 'NEVEREXISTED', ''):
            with self.assertRaises(offers.OfferError) as refused:
                offers.redeem(self.alice, code)
            self.assertEqual(str(refused.exception), offers.BAD_CODE, code)
        self.assertEqual(resolve(self.alice).plan.code, 'free')
        self.assertFalse(PromoRedemption.objects.filter(user=self.alice).exists())

    def test_a_code_can_be_kept_for_users_on_certain_plans(self):
        promo = self.code()
        promo.only_plans.add(Plan.objects.get(code='free'))
        grant_plan(self.alice, 'business')
        with self.assertRaisesMessage(offers.OfferError, 'current plan'):
            offers.redeem(self.alice, 'WELCOME30')
        offers.redeem(self.bob, 'WELCOME30')

    def test_a_quota_code_adds_credits_to_this_month(self):
        self.code(code='CREDITS50', kind='quota', benefit_plan=None, benefit_days=None,
                  benefit_feature=credits(), benefit_amount=50)
        offers.redeem(self.alice, 'CREDITS50')
        numbers = self.entitlements()['features']['ai.credits']
        self.assertEqual((numbers['limit'], numbers['bonus'], numbers['remaining']), (15, 50, 65))
        self.assertEqual(resolve(self.alice).plan.code, 'free')

    def test_validation(self):
        with self.assertRaises(ValidationError):
            PromoCode(code='ABC', kind='plan', benefit_plan=plus(), benefit_days=7).full_clean()
        with self.assertRaises(ValidationError):
            PromoCode(code='NODAYS99', kind='plan', benefit_plan=plus()).full_clean()
        with self.assertRaises(ValidationError):
            PromoCode(code='NOAMOUNT9', kind='quota', benefit_feature=credits()).full_clean()
        generated = PromoCode.objects.create(kind='plan', benefit_plan=plus(), benefit_days=7)
        self.assertEqual(len(generated.code), 12)
        self.assertNotEqual(generated.code, PromoCode.objects.create(kind='plan', benefit_plan=plus(), benefit_days=7).code)

    def test_the_endpoint_answers_with_the_new_entitlements(self):
        self.code()
        response = self.alice_client.post(REDEEM, {'code': 'welcome30'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['plan']['code'], response.data['source']), ('plus', 'promo_code'))

        again = self.alice_client.post(REDEEM, {'code': 'welcome30'}, format='json')
        self.assertEqual(again.status_code, 400)
        self.assertIn('already used', again.data['code'][0])
        for body in ({'code': 'NOPE'}, {'code': ''}, {}, {'code': ['WELCOME30']}):
            response = self.bob_client.post(REDEEM, body, format='json')
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.data['code'], [offers.BAD_CODE])
        self.assertEqual(resolve(self.bob).plan.code, 'free')

    def test_a_code_cannot_be_redeemed_for_someone_else(self):
        self.code()
        response = self.alice_client.post(
            f'{REDEEM}?user={self.bob.id}', {'code': 'WELCOME30', 'user': str(self.bob.id), 'user_id': str(self.bob.id)},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((resolve(self.alice).plan.code, resolve(self.bob).plan.code), ('plus', 'free'))


class CampaignTests(BillingTestCase):
    def campaign(self, **fields):
        now = timezone.now()
        defaults = {
            'slug': 'launch', 'name': 'Launch week', 'title': 'Launch week', 'title_bn': 'উদ্বোধনী সপ্তাহ',
            'body': 'Try Plus free for a week.', 'cta': 'Claim', 'is_active': True,
            'starts_at': now - timedelta(hours=1), 'ends_at': now + timedelta(days=3),
            'kind': 'plan', 'benefit_plan': plus(), 'benefit_days': 7,
            'placements': ['home_banner', 'upgrade_sheet'],
        }
        return Campaign.objects.create(**{**defaults, **fields})

    def offers(self, client=None):
        return self.entitlements(client)['offers']

    def claim(self, slug='launch', client=None):
        return (client or self.alice_client).post(f'/api/v1/billing/offers/{slug}/claim/')

    def test_a_running_campaign_reaches_its_audience_with_its_end_time(self):
        campaign = self.campaign()
        offer = self.offers()[0]
        self.assertEqual(
            (offer['slug'], offer['title'], offer['title_bn'], offer['placements'], offer['ends_at']),
            ('launch', 'Launch week', 'উদ্বোধনী সপ্তাহ', ['home_banner', 'upgrade_sheet'], campaign.ends_at.isoformat()),
        )
        self.assertEqual(offer['benefit'], {'kind': 'plan', 'plan': 'plus', 'days': 7})
        self.assertEqual((offer['claimable'], offer['claimed'], offer['applied']), (True, False, False))
        # Nothing was given yet
        self.assertEqual(resolve(self.alice).plan.code, 'free')

    def test_claiming_gives_the_benefit_once(self):
        campaign = self.campaign()
        response = self.claim()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data['plan']['code'], response.data['source']), ('plus', 'campaign'))
        offer = response.data['offers'][0]
        self.assertEqual((offer['claimed'], offer['claimable']), (True, False))
        self.assertEqual(Subscription.objects.get(user=self.alice).campaign, campaign)

        again = self.claim()
        self.assertEqual(again.status_code, 400)
        self.assertIn('already taken', again.data['detail'])
        self.assertEqual(Subscription.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).claimed_count, 1)

    def test_the_plan_outlasts_the_campaign_by_its_own_days(self):
        campaign = self.campaign()
        self.claim()
        after_campaign = campaign.ends_at + timedelta(days=1)
        self.assertEqual(resolve(self.alice, now=after_campaign).plan.code, 'plus')
        self.assertEqual(resolve(self.alice, now=timezone.now() + timedelta(days=8)).plan.code, 'free')

    def test_a_campaign_outside_its_window_or_switched_off_is_not_offered(self):
        now = timezone.now()
        self.campaign(slug='ended', ends_at=now - timedelta(minutes=1), starts_at=now - timedelta(days=2))
        self.campaign(slug='later', starts_at=now + timedelta(hours=1))
        self.campaign(slug='draft', is_active=False)
        self.assertEqual(self.offers(), [])
        for slug in ('ended', 'later', 'draft', 'never-existed'):
            self.assertEqual(self.claim(slug).status_code, 400, slug)
        self.assertFalse(Subscription.objects.exists())

    def test_only_the_audience_sees_and_claims_it(self):
        chosen = self.campaign(slug='vip', audience='users')
        chosen.audience_users.add(self.bob)
        free_only = self.campaign(slug='free-only', audience='plans')
        free_only.audience_plans.add(Plan.objects.get(code='free'))
        grant_plan(self.alice, 'business')

        self.assertEqual(self.offers(), [])
        self.assertEqual({offer['slug'] for offer in self.offers(self.bob_client)}, {'vip', 'free-only'})
        self.assertEqual(self.claim('vip').status_code, 400)
        self.assertEqual(self.claim('free-only').status_code, 400)
        self.assertEqual(self.claim('vip', self.bob_client).status_code, 200)

    def test_a_cap_on_claims_holds(self):
        self.campaign(max_claims=1)
        self.assertEqual(self.claim(client=self.bob_client).status_code, 200)
        self.assertFalse(self.offers()[0]['claimable'])
        self.assertEqual(self.claim().status_code, 400)
        self.assertEqual(resolve(self.alice).plan.code, 'free')

    def test_a_message_only_campaign_is_shown_and_gives_nothing(self):
        self.campaign(kind='none', benefit_plan=None, benefit_days=None)
        offer = self.offers()[0]
        self.assertEqual((offer['benefit'], offer['claimable']), ({'kind': 'none'}, False))
        self.assertEqual(self.claim().status_code, 400)

    def test_a_quota_campaign_adds_credits(self):
        self.campaign(kind='quota', benefit_plan=None, benefit_days=None, benefit_feature=credits(), benefit_amount=25)
        self.assertEqual(self.offers()[0]['benefit'], {'kind': 'quota', 'feature': 'ai.credits', 'amount': 25})
        response = self.claim()
        self.assertEqual(response.data['features']['ai.credits']['bonus'], 25)

    def test_a_store_offer_points_at_the_store(self):
        self.campaign(kind='store_offer', benefit_plan=None, benefit_days=None, store_offer_id='eid-40-off')
        offer = self.offers()[0]
        self.assertEqual(offer['benefit'], {'kind': 'store_offer', 'store_offer_id': 'eid-40-off'})
        self.assertFalse(offer['claimable'])

    def test_one_that_applies_by_itself_is_shown_as_applied_and_stays_visible(self):
        self.campaign(auto_apply=True, audience='plans').audience_plans.add(Plan.objects.get(code='free'))
        body = self.entitlements()
        self.assertEqual((body['plan']['code'], body['source']), ('plus', 'campaign'))
        offer = body['offers'][0]
        self.assertEqual((offer['applied'], offer['claimable']), (True, False))
        self.assertEqual(self.claim().status_code, 400)
        self.assertFalse(CampaignClaim.objects.exists())

    def test_higher_priority_comes_first(self):
        self.campaign(slug='small', priority=1)
        self.campaign(slug='big', priority=9)
        self.assertEqual([offer['slug'] for offer in self.offers()], ['big', 'small'])

    def test_validation(self):
        now = timezone.now()
        base = {
            'slug': 'x', 'name': 'x', 'title': 'x', 'starts_at': now, 'ends_at': now + timedelta(days=1),
            'placements': ['home_banner'],
        }
        Campaign(**base).full_clean()
        bad = [
            {'ends_at': now - timedelta(days=1)},
            {'placements': ['billboard']},
            {'placements': 'home_banner'},
            {'kind': 'plan'},
            {'kind': 'store_offer'},
            {'kind': 'none', 'auto_apply': True},
        ]
        for fields in bad:
            with self.assertRaises(ValidationError, msg=fields):
                Campaign(**{**base, **fields}).full_clean()


class GrantTests(BillingTestCase):
    def test_a_grant_records_who_and_why(self):
        staff = User.objects.create_user(email='staff@example.com', password='pass-12345', is_staff=True)
        subscription = offers.grant(self.alice, plus(), days=14, reason='beta tester', by=staff)
        self.assertEqual((subscription.source, subscription.reason, subscription.created_by),
                         ('grant', 'beta tester', staff))
        history = Subscription.pgh_event_model.objects.filter(pgh_obj_id=subscription.pk)
        self.assertEqual(history.count(), 1)
        offers.revoke(subscription, 'ended early')
        self.assertEqual(history.count(), 2)
        self.assertEqual(self.entitlements(client_for(self.alice))['plan']['code'], 'free')
