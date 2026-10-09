import json
import os
import tempfile
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from billing import catalog_io
from billing.catalog import defaults
from billing.catalog.keys import ALL, BY_KEY, F, FLAG, KINDS
from billing.checks import default_plan_exists
from billing.models import BillingSettings, Feature, Plan, PlanFeature
from billing.seed import seed_live


def stored(plan_code, feature):
    """What the database says the plan gets, in the shape defaults.py uses."""
    row = PlanFeature.objects.get(plan__code=plan_code, feature__key=feature.key)
    if feature.kind == FLAG:
        return row.enabled
    return defaults.UNLIMITED if row.unlimited else row.limit


class DefaultsTests(TestCase):
    def test_every_key_is_well_formed_and_has_a_value_on_every_plan(self):
        self.assertEqual(len(BY_KEY), len(ALL), 'two features share a key')
        for feature in ALL:
            self.assertIn(feature.kind, KINDS)
            self.assertIn(feature, defaults.VALUES, f'{feature.key} has no defaults')
            self.assertEqual(len(defaults.VALUES[feature]), len(defaults.PLANS))
            for value in defaults.VALUES[feature]:
                if feature.kind == FLAG:
                    self.assertIsInstance(value, bool, feature.key)
                else:
                    self.assertTrue(value == defaults.UNLIMITED or (isinstance(value, int) and value >= 0), feature.key)

    def test_a_higher_plan_never_gives_less(self):
        for feature in ALL:
            if feature == F.ADS:
                continue  # the one flag that is better off
            values = [
                float('inf') if value == defaults.UNLIMITED else int(value)
                for value in defaults.VALUES[feature]
            ]
            self.assertEqual(values, sorted(values), f'{feature.key} shrinks on a higher plan')


class SeedTests(TestCase):
    def test_a_migrated_database_already_holds_the_default_tiers(self):
        self.assertEqual(list(Plan.objects.order_by('rank').values_list('code', flat=True)), defaults.PLAN_CODES)
        self.assertEqual(Plan.objects.get(is_default=True).code, defaults.FREE)
        self.assertTrue(BillingSettings.objects.filter(pk=1).exists())
        for code in defaults.PLAN_CODES:
            for feature in ALL:
                self.assertEqual(stored(code, feature), defaults.value_for(code, feature), f'{code}.{feature.key}')
        self.assertFalse(Feature.objects.filter(is_system=False).exists())

    def test_seeding_again_changes_nothing(self):
        self.assertEqual(seed_live(), [])

    def test_admin_changes_survive_a_seed_and_force_puts_defaults_back(self):
        row = PlanFeature.objects.get(plan__code='free', feature__key=F.PERSONAL_ACCOUNTS.key)
        row.limit = 9
        row.save()
        Plan.objects.filter(code='plus').update(name='Plus+')

        self.assertEqual(seed_live(), [])
        self.assertEqual(stored('free', F.PERSONAL_ACCOUNTS), 9)

        self.assertEqual(len(seed_live(force=True, dry_run=True)), 2)
        self.assertEqual(stored('free', F.PERSONAL_ACCOUNTS), 9, 'a dry run changed something')

        seed_live(force=True)
        self.assertEqual(stored('free', F.PERSONAL_ACCOUNTS), 4)
        self.assertEqual(Plan.objects.get(code='plus').name, 'Plus')

    def test_seed_restores_what_was_deleted(self):
        PlanFeature.objects.filter(plan__code='plus', feature__key=F.AI_CREDITS.key).delete()
        Plan.objects.filter(code='business').delete()
        changes = seed_live()
        self.assertIn('plus.ai.credits: add 300', changes)
        self.assertIn('plan business: add', changes)
        self.assertEqual(stored('business', F.TEAM_SEATS), 5)

    def test_the_kind_of_a_system_feature_is_always_what_the_code_says(self):
        Feature.objects.filter(key=F.AI_CREDITS.key).update(kind=FLAG)
        seed_live()
        self.assertEqual(Feature.objects.get(key=F.AI_CREDITS.key).kind, F.AI_CREDITS.kind)

    def test_commands(self):
        out = StringIO()
        call_command('billing_seed', stdout=out)
        self.assertIn('already loaded', out.getvalue())

        PlanFeature.objects.filter(plan__code='free', feature__key=F.TEAM_SEATS.key).update(limit=3)
        out = StringIO()
        call_command('billing_seed', '--check', stdout=out)
        self.assertIn('free.team.seats: 3 -> 0', out.getvalue())
        self.assertEqual(stored('free', F.TEAM_SEATS), 3, '--check changed something')


class DefaultPlanTests(TestCase):
    def test_there_can_only_be_one_default(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Plan.objects.filter(code='plus').update(is_default=True)

    def test_the_system_check_fails_without_a_default(self):
        self.assertEqual(default_plan_exists(None), [])
        Plan.objects.filter(is_default=True).update(is_default=False)
        errors = default_plan_exists(None)
        self.assertEqual([error.id for error in errors], ['billing.E001'])

    def test_the_default_plan_cannot_be_made_inactive(self):
        plan = Plan.objects.get(is_default=True)
        plan.is_active = False
        with self.assertRaises(ValidationError):
            plan.full_clean()


class PlanFeatureTests(TestCase):
    def test_a_limit_needs_a_number_or_unlimited(self):
        plan = Plan.objects.get(code='free')
        row = PlanFeature(plan=plan, feature=Feature.objects.get(key=F.DEVICES_MAX.key))
        with self.assertRaises(ValidationError):
            row.clean()
        row.unlimited, row.limit = True, 7
        row.clean()
        self.assertIsNone(row.limit)

    def test_a_flag_carries_no_number(self):
        row = PlanFeature(
            plan=Plan.objects.get(code='free'), feature=Feature.objects.get(key=F.ADS.key),
            enabled=True, limit=5, unlimited=True,
        )
        row.clean()
        self.assertEqual((row.enabled, row.limit, row.unlimited), (True, None, False))


class ExportImportTests(TestCase):
    def test_round_trip_carries_admin_changes(self):
        PlanFeature.objects.filter(plan__code='free', feature__key=F.PERSONAL_ACCOUNTS.key).update(limit=6)
        gold = Plan.objects.create(code='gold', name='Gold', rank=30)
        extra = Feature.objects.create(key='labs.dark_charts', kind=FLAG, name='Dark charts')
        PlanFeature.objects.create(plan=gold, feature=extra, enabled=True)
        data = json.loads(json.dumps(catalog_io.export()))

        gold.delete()
        extra.delete()
        seed_live(force=True)
        self.assertEqual(stored('free', F.PERSONAL_ACCOUNTS), 4)

        catalog_io.load(data)
        self.assertEqual(stored('free', F.PERSONAL_ACCOUNTS), 6)
        self.assertTrue(PlanFeature.objects.get(plan__code='gold', feature__key='labs.dark_charts').enabled)
        self.assertFalse(Feature.objects.get(key='labs.dark_charts').is_system)
        self.assertEqual(Plan.objects.filter(is_default=True).count(), 1)

    def test_bad_data_changes_nothing(self):
        data = catalog_io.export()
        for plan in data['plans']:
            plan['is_default'] = False
        with self.assertRaises(ValidationError):
            catalog_io.load(data)
        with self.assertRaises(ValidationError):
            catalog_io.load({'format': 99})
        self.assertEqual(Plan.objects.get(is_default=True).code, 'free')

    def test_commands_write_and_read_a_file(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'catalog.json')
        call_command('billing_export', path, stdout=StringIO())
        Plan.objects.filter(code='plus').update(name='Changed')
        call_command('billing_import', path, stdout=StringIO())
        self.assertEqual(Plan.objects.get(code='plus').name, 'Plus')
        with self.assertRaises(CommandError):
            call_command('billing_import', os.path.join(directory, 'missing.json'), stdout=StringIO())
