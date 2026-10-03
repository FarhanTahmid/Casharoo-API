import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from workspaces.models import Workspace
from .models import AppUser

AUTH = '/_allauth/app/v1/auth'
PASSWORD = 'a-long-pass-987'


def code_from_last_email():
    """Verification codes are emailed on their own line"""
    return re.search(r'^\s*([A-Z0-9]{4,}(?:-[A-Z0-9]+)*)\s*$', mail.outbox[-1].body, re.MULTILINE).group(1)


class AuthTestCase(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit counters
        self.client = APIClient()

    def post(self, path, data, token=None):
        headers = {'X-Session-Token': token} if token else {}
        return self.client.post(f'{AUTH}{path}', data, format='json', headers=headers)

    def signup(self, email='alice@example.com'):
        """Sign up and verify the email; returns the session token"""
        response = self.post('/signup', {'email': email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 401, response.content)  # pending email verification
        token = response.json()['meta']['session_token']
        response = self.post('/email/verify', {'key': code_from_last_email()}, token=token)
        self.assertEqual(response.status_code, 200, response.content)
        # Logging in rotates the session token
        return response.json()['meta'].get('session_token', token)


class SignupAndLoginTests(AuthTestCase):
    def test_signup_requires_email_verification_then_grants_access(self):
        response = self.post('/signup', {'email': 'alice@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 401)
        token = response.json()['meta']['session_token']

        # Not usable against the API until the email is verified
        me = self.client.get('/api/v1/me/', headers={'X-Session-Token': token})
        self.assertIn(me.status_code, (401, 403))

        response = self.post('/email/verify', {'key': code_from_last_email()}, token=token)
        self.assertEqual(response.status_code, 200, response.content)
        token = response.json()['meta'].get('session_token', token)

        me = self.client.get('/api/v1/me/', headers={'X-Session-Token': token})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data['email'], 'alice@example.com')

        user = AppUser.objects.get(email='alice@example.com')
        self.assertTrue(user.password.startswith(('argon2', 'md5')))
        self.assertEqual(Workspace.objects.get(owner=user).kind, 'personal')

    def test_login_and_logout(self):
        self.signup()
        response = self.post('/login', {'email': 'alice@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200, response.content)
        token = response.json()['meta']['session_token']
        headers = {'X-Session-Token': token}
        self.assertEqual(self.client.get('/api/v1/cashbooks/', headers=headers).status_code, 200)

        # Logout revokes the token on the server
        self.client.delete(f'{AUTH}/session', headers=headers)
        self.assertIn(self.client.get('/api/v1/me/', headers=headers).status_code, (401, 403))

    def test_wrong_password_is_rejected(self):
        self.signup()
        response = self.post('/login', {'email': 'alice@example.com', 'password': 'wrong-password'})
        self.assertEqual(response.status_code, 400)

    def test_api_requires_authentication(self):
        for path in ('/api/v1/me/', '/api/v1/cashbooks/', '/api/v1/workspaces/'):
            self.assertIn(self.client.get(path).status_code, (401, 403), path)

    def test_weak_password_is_rejected(self):
        response = self.post('/signup', {'email': 'alice@example.com', 'password': '12345'})
        self.assertEqual(response.status_code, 400)


class PasswordTests(AuthTestCase):
    def test_password_reset_needs_the_emailed_code(self):
        self.signup()
        self.assertEqual(self.post('/password/request', {'email': 'alice@example.com'}).status_code, 401)
        code = code_from_last_email()

        # Without the code the password cannot be changed
        response = self.post('/password/reset', {'key': 'WRONG1', 'password': 'new-long-pass-456'})
        self.assertNotEqual(response.status_code, 200)
        user = AppUser.objects.get(email='alice@example.com')
        self.assertTrue(user.check_password(PASSWORD))

    def test_password_reset_with_code(self):
        self.signup()
        response = self.post('/password/request', {'email': 'alice@example.com'})
        token = response.json()['meta']['session_token']
        response = self.post('/password/reset', {'key': code_from_last_email(), 'password': 'new-long-pass-456'}, token=token)
        self.assertIn(response.status_code, (200, 401), response.content)
        user = AppUser.objects.get(email='alice@example.com')
        self.assertTrue(user.check_password('new-long-pass-456'))

    def test_change_password(self):
        token = self.signup()
        response = self.client.post(
            '/_allauth/app/v1/account/password/change',
            {'current_password': PASSWORD, 'new_password': 'new-long-pass-456'},
            format='json', headers={'X-Session-Token': token},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(AppUser.objects.get(email='alice@example.com').check_password('new-long-pass-456'))


class ProfileTests(AuthTestCase):
    def test_profile_update_cannot_change_email(self):
        user = AppUser.objects.create_user(email='alice@example.com', password=PASSWORD)
        self.client.force_authenticate(user)
        response = self.client.patch('/api/v1/me/', {'first_name': 'Alice', 'email': 'evil@example.com'})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.email), ('Alice', 'alice@example.com'))


class OnboardingTests(AuthTestCase):
    def test_onboarding_choice_is_kept_on_the_server(self):
        user = AppUser.objects.create_user(email='alice@example.com', password=PASSWORD)
        self.client.force_authenticate(user)
        profile = self.client.get('/api/v1/me/').json()
        self.assertEqual((profile['onboarded_at'], profile['primary_mode']), (None, ''))

        response = self.client.patch(
            '/api/v1/me/', {'onboarded_at': '2026-10-03T10:00:00Z', 'primary_mode': 'business'}, format='json'
        )
        self.assertEqual(response.status_code, 200, response.content)
        profile = self.client.get('/api/v1/me/').json()
        self.assertTrue(profile['onboarded_at'].startswith('2026-10-03'))
        self.assertEqual(profile['primary_mode'], 'business')
        self.assertEqual(self.client.patch('/api/v1/me/', {'primary_mode': 'galaxy'}).status_code, 400)


class SchemaTests(AuthTestCase):
    def test_health_and_openapi_schema(self):
        self.assertEqual(self.client.get('/health/').json(), {'status': 'ok'})
        self.assertEqual(self.client.get('/health/?db=1').json(), {'status': 'ok', 'database': 'ok'})
        response = self.client.get('/api/v1/schema/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('/api/v1/cashbooks/', response.data['paths'])
        self.assertIn('/api/v1/me/', response.data['paths'])
