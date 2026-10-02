from django.core.mail.backends.base import BaseEmailBackend

from .tasks import send_email


class QueuedEmailBackend(BaseEmailBackend):
    """
    Django email backend that hands every message to the background worker,
    so no request waits on SMTP. The job is enqueued on the request's own
    database connection: if the request rolls back, the email is not sent.

    Attachments are not carried over.
    """

    def send_messages(self, email_messages):
        for message in email_messages:
            html_body = next(
                (content for content, mimetype in getattr(message, 'alternatives', []) if mimetype == 'text/html'),
                None,
            )
            send_email.defer(
                subject=message.subject,
                body=message.body,
                to=list(message.to),
                from_email=message.from_email,
                html_body=html_body,
                purpose='auth',
            )
        return len(email_messages)
