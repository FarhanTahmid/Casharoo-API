from unittest import mock

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings

from audit.utils.client_ip import get_client_ip
from .models import EmailAccounts
from .tasks import EmailDeliveryError, deliver_email


class EncryptedFieldTests(TestCase):
    def test_smtp_password_is_encrypted_at_rest(self):
        account = EmailAccounts.objects.create(
            name='Auth', email_address='no-reply@example.com', smtp_server='smtp.example.com',
            username='no-reply@example.com', password='s3cret-app-password', purpose='auth',
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT password FROM notifications_emailaccounts WHERE id = %s", [account.id])
            stored = cursor.fetchone()[0]
        self.assertTrue(stored.startswith('fernet:'))
        self.assertNotIn('s3cret-app-password', stored)
        self.assertEqual(EmailAccounts.objects.get(id=account.id).password, 's3cret-app-password')

    def test_saving_again_does_not_double_encrypt(self):
        account = EmailAccounts.objects.create(
            name='Auth', email_address='a@example.com', smtp_server='smtp.example.com', password='pw', purpose='auth',
        )
        account = EmailAccounts.objects.get(id=account.id)
        account.name = 'Renamed'
        account.save()
        self.assertEqual(EmailAccounts.objects.get(id=account.id).password, 'pw')


class EmailQueueTests(TestCase):
    @override_settings(EMAIL_BACKEND='notifications.backends.QueuedEmailBackend')
    def test_queued_backend_enqueues_instead_of_sending(self):
        message = EmailMultiAlternatives('Subject', 'Body', 'from@example.com', ['to@example.com'])
        message.attach_alternative('<p>Body</p>', 'text/html')
        with mock.patch('notifications.backends.send_email.defer') as defer:
            self.assertEqual(message.send(), 1)
        defer.assert_called_once_with(
            subject='Subject', body='Body', to=['to@example.com'],
            from_email='from@example.com', html_body='<p>Body</p>', purpose='auth',
        )

    def test_job_is_stored_in_the_database(self):
        from procrastinate.contrib.django.models import ProcrastinateJob
        from .tasks import send_email
        send_email.defer(subject='S', body='B', to=['to@example.com'])
        job = ProcrastinateJob.objects.get()
        self.assertEqual((job.queue_name, job.task_name), ('email', 'notifications.tasks.send_email'))

    @override_settings(EMAIL_DELIVERY_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_delivery_falls_back_to_django_backend_without_smtp_account(self):
        deliver_email('Subject', 'Body', ['to@example.com'], from_email='from@example.com', html_body='<p>Body</p>')
        self.assertEqual(mail.outbox[-1].subject, 'Subject')
        self.assertEqual(mail.outbox[-1].alternatives[0][0], '<p>Body</p>')

    def test_delivery_failure_raises_so_the_job_is_retried(self):
        EmailAccounts.objects.create(
            name='Auth', email_address='a@example.com', smtp_server='smtp.invalid', username='a', password='pw',
            purpose='default',
        )
        with mock.patch('notifications.email_handler.smtplib.SMTP_SSL', side_effect=OSError('unreachable')):
            with self.assertRaises(EmailDeliveryError):
                deliver_email('Subject', 'Body', ['to@example.com'])


class ClientIpTests(TestCase):
    def request(self, forwarded):
        return RequestFactory().get('/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR=forwarded)

    def test_forwarded_header_is_ignored_without_trusted_proxy(self):
        self.assertEqual(get_client_ip(self.request('6.6.6.6')), '10.0.0.1')

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_client_cannot_spoof_through_one_proxy(self):
        # The client sent "6.6.6.6"; our proxy appended the address it really saw
        self.assertEqual(get_client_ip(self.request('6.6.6.6, 203.0.113.9')), '203.0.113.9')
