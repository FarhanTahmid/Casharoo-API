import smtplib
import logging
import traceback
from datetime import datetime
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from django.template import Template, Context
from django.db import DatabaseError, OperationalError
from django.conf import settings
from django.utils import timezone
from ..models import EmailAccounts, EmailTemplate,EmailLog

logger = logging.getLogger("system_manager.utils.email_handler")

class EmailHandler:
    """Email handler class to manage sending emails using SMTP."""
        
    @staticmethod
    def get_email_account(purpose: Optional[str]):
        """
        Return an active EmailAccounts instance for the given purpose.
        Falls back to 'default' if specific purpose not found.
        Returns None only when nothing is available; logs all branches.
        """
        # Normalize/validate input
        normalized = (purpose or "").strip().lower()
        if not normalized:
            logger.warning("Empty purpose passed; using 'default'.", extra={"purpose": purpose})
            normalized = "default"

        try:
            # Try exact purpose first
            account = (
                EmailAccounts.objects
                .filter(purpose=normalized, is_active=True)
                .first()
            )
            if account:
                return account

            # Fallback to default (only if not already default)
            if normalized != "default":
                fallback = (
                    EmailAccounts.objects
                    .filter(purpose="default", is_active=True)
                    .first()
                )
                if fallback:
                    logger.info(
                        "Using default email account as fallback.",
                        extra={"requested_purpose": normalized, "fallback_id": fallback.id}
                    )
                    return fallback

            # Not found (this is a functional condition, not an error)
            logger.warning(
                "No active email account found for purpose (including default).",
                extra={"requested_purpose": normalized}
            )
            return None

        except (OperationalError, DatabaseError) as db_err:
            # DB-related: log as error with traceback
            logger.error(
                "Database error retrieving email account.",
                exc_info=True,
                extra={"requested_purpose": normalized}
            )
            return None

        except Exception:
            # Truly unexpected
            logger.exception(
                "Unexpected error retrieving email account.",
                extra={"requested_purpose": normalized}
            )
            return None
    
    @staticmethod
    def get_email_template(template_name,purpose=None):
        """
        Retrieve an EmailTemplate instance by name and purpose (if given only).
        Returns None if not found or if any error occurs.
        """
        query = {'name': template_name}
        if purpose:
            query['purpose'] = purpose
        
        try:
            template=EmailTemplate.objects.filter(**query).first()
            if template:
                return template
            return None
        except (OperationalError, DatabaseError) as db_err:
            # Log database-related errors
            logger.error(
                "Database error retrieving email template.",
                exc_info=True,
                extra={"template_name": template_name, "purpose": purpose}
            )
            return None
        except Exception:
            # Log any other unexpected errors
            logger.exception(
                "Unexpected error retrieving email template.",
                extra={"template_name": template_name, "purpose": purpose}
            )
            return None
    
    @staticmethod
    def render_template(template_content,context_data):
        """
        Render a template with the given context data.
        Returns the rendered string or None if an error occurs.
        """
        try:
            template=Template(template_content)
            context=Context(context_data)
            return template.render(context)
        except Exception as e:
            logger.error(
                "Error rendering template. {e}",
                exc_info=True,
                extra={"template_content": template_content, "context_data": context_data}
            )
            return None
    
    @classmethod
    def send_email(cls, to_emails, subject, text_content=None, html_content=None, purpose='default', 
                template_name=None, context_data=None, from_email=None, reply_to=None, 
                attachments=None, track=True, retry_failed=False):
        """
        Send email with comprehensive error handling and tracking
        
        Args:
            to_emails: Single email or list of emails
            subject: Email subject
            text_content: Plain text content
            html_content: HTML content (optional)
            purpose: Email purpose (for selecting account)
            template_name: Name of template to use (optional)
            context_data: Context data for template rendering
            from_email: Custom from email (optional)
            reply_to: Reply-to email address (optional)
            attachments: List of attachments (optional)
            track: Whether to track email sending in database
            retry_failed: Whether to retry failed emails
            
        Returns:
            Tuple: (success, message, log_id)
        """
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        
        # Get the appropriate email account
        email_account = cls.get_email_account(purpose)
        if not email_account:
            message = f"No active email account found for purpose '{purpose}'."
            logger.error(message)
            if track and email_log:
                email_log.status = 'FAILED'
                email_log.error_message = message
                email_log.save()
            return False, message, email_log.id if email_log else None

        # create email log entry if tracking is enabled
        email_log = None
        if track:
            email_log = EmailLog.objects.create(
                sender_email = email_account.email_address if email_account else from_email,
                to_emails=','.join(to_emails),
                subject=subject,
                purpose=purpose,
                template_name=template_name if template_name else '',
                status='PENDING'
            )
        # Use template if provided
        try:
            if template_name and context_data:
                template=cls.get_email_template(template_name,purpose)
                if template:
                    subject = cls.render_template(template.subject, context_data)
                    text_content = cls.render_template(template.body_text, context_data)
                    if template.body_html:
                        html_content = cls.render_template(template.body_html, context_data)
                else:
                    message = f"Email template with name: '{template_name}' and purpose: '{purpose}' was not found."
                    
        except Exception as e:
                message = f"Error retrieving email template '{template_name}': {str(e)}"
                logger.error(message, exc_info=True)
                if track and email_log:
                    email_log.sender_email = email_account.email_address
                    email_log.status = 'FAILED'
                    email_log.error_message = message
                    email_log.save()
                return False, message, email_log.id if email_log else None
        
        # Prepare email message
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email or email_account.email_address
            msg['To'] = ', '.join(to_emails)
            if reply_to:
                msg['Reply-To'] = reply_to
            # Attach text and HTML content
            msg.attach(MIMEText(text_content, 'plain'))
            if html_content:
                msg.attach(MIMEText(html_content, 'html'))
            
            # Attach files if provided
            if attachments:
                for attachment in attachments:
                    if isinstance(attachment, dict) and 'filename' in attachment and 'content' in attachment:
                        part = MIMEApplication(attachment['content'])
                        part.add_header('Content-Disposition', 'attachment', filename=attachment['filename'])
                        msg.attach(part)
            
        except Exception as e:
            message = f"Error preparing email headers: {str(e)}"
            logger.error(message, exc_info=True)
            if track and email_log:
                email_log.sender_email = email_account.email_address
                email_log.status = 'FAILED'
                email_log.error_message = message
                email_log.save()
            return False, message, email_log.id if email_log else None
        
        # Send email using SMTP
        try:
            logger.info(
                "Attempting to send email",
                extra={
                    "to_emails": to_emails,
                    "subject": subject,
                    "purpose": purpose,
                    "from_email": from_email or email_account.email_address
                }
            )
            # connect to SMTP server
            if email_account.use_ssl:
                server = smtplib.SMTP_SSL(email_account.smtp_server, email_account.smtp_port)
            else:
                server = smtplib.SMTP(email_account.smtp_server, email_account.smtp_port)
            
            if email_account.use_tls:
                server.starttls()
            
            # Set debug level if needed
            if settings.DEBUG:
                server.set_debuglevel(1)
            # Login if credentials are provided
            if email_account.username and email_account.password:
                server.login(email_account.username, email_account.password)
            else:
                logger.error(
                    "Email account credentials are missing.",
                    extra={"email_account_id": email_account.id}
                )
                if track and email_log:
                    email_log.sender_email = email_account.email_address
                    email_log.status = 'FAILED'
                    email_log.error_message = "Email account credentials are missing."
                    email_log.save()
                return False, "Email account credentials are missing.", email_log.id if email_log else None
            # Send the email
            server.sendmail(msg['From'], to_emails, msg.as_string())
            server.quit()
            
            if track and email_log:
                email_log.sender_email = email_account.email_address
                email_log.status = 'SENT'
                email_log.sent_at=datetime.now()
                email_log.save()
            
            success_msg = f"Email sent successfully"
            logger.info(success_msg, extra={"to_emails": to_emails, "subject": subject})
            return True, success_msg, email_log.id if email_log else None

        except smtplib.SMTPException as smtp_err:
            message = f"SMTP error sending email: {str(smtp_err)}"
            logger.error(message, exc_info=True)
            if track and email_log:
                email_log.sender_email = email_account.email_address
                email_log.status = 'FAILED'
                email_log.error_message = message
                email_log.save()
            return False, message, email_log.id if email_log else None
        except smtplib.SMTPServerDisconnected as e:
            message = f"SMTP server disconnected: {str(e)}"
            logger.error(message, exc_info=True)
            if track and email_log:
                email_log.sender_email = email_account.email_address
                email_log.status = 'FAILED'
                email_log.error_message = message
                email_log.save()
            return False, message, email_log.id if email_log else None
        except Exception as e:
            message = f"Unexpected error sending email: {str(e)}"
            logger.error(message, exc_info=True)
            if track and email_log:
                email_log.sender_email = email_account.email_address
                email_log.status = 'FAILED'
                email_log.error_message = message
                email_log.save()
            return False, message, email_log.id if email_log else None
    
    @staticmethod
    def verify_smtp_connection(email_account_id=None):
        """
        Verify SMTP connection settings for an email account
        
        Args:
            email_account_id: ID of email account to verify, or None for default
            
        Returns:
            Tuple: (success, message)
        """
        try:
            # Get the email account
            if email_account_id:
                try:
                    account = EmailAccounts.objects.get(id=email_account_id)
                except EmailAccounts.DoesNotExist:
                    logger.error(
                        "Email account not found for verification.",
                        extra={"email_account_id": email_account_id}
                    )
                    return False, "No email account found"
            else:
                account = EmailAccounts.objects.filter(purpose='default', is_active=True).first()
                
            if not account:
                logger.error(
                    "No active email account found for verification.",
                    extra={"email_account_id": email_account_id}
                )
                return False, "No email account found"
                    
            # Try connecting to the SMTP server
            if account.use_ssl:
                server = smtplib.SMTP_SSL(account.smtp_server, account.smtp_port)
            else:
                server = smtplib.SMTP(account.smtp_server, account.smtp_port)
                    
            if account.use_tls:
                server.starttls()
                    
            # Try login
            server.login(account.username, account.password)
            
            # Close connection
            server.quit()
            
            return True, "SMTP connection verified successfully"
            
        except smtplib.SMTPAuthenticationError:
            logger.error(
                "SMTP authentication failed for email account.",
                extra={"email_account_id": email_account_id}
            )
            return False, "SMTP authentication failed. Check username and password."
            
        except smtplib.SMTPConnectError:
            logger.error(
                "Failed to connect to SMTP server.",
                extra={"email_account_id": email_account_id}
            )
            return False, "Failed to connect to SMTP server. Check server and port settings."
            
        except Exception as e:
            logger.error(
                "Unexpected error verifying SMTP connection.",
                exc_info=True,
                extra={"email_account_id": email_account_id}
            )
            return False, f"SMTP verification failed: {str(e)}"
    
    # Helper function for manually checking email status    
    def check_email_status(email_log_id):
        """
        Check the status of a sent email
        
        Args:
            email_log_id: ID of the email log to check
            
        Returns:
            dict: Email status information
        """
        try:
            email_log = EmailLog.objects.get(id=email_log_id)
            return {
                'status': email_log.status,
                'subject': email_log.subject,
                'to': email_log.to_emails,
                'sent_at': email_log.sent_at,
                'error': email_log.error_message,
                'retry_count': email_log.retry_count
            }
        except EmailLog.DoesNotExist:
            return {'error': 'Email log not found'}
        except Exception as e:
            return {'error': f'Error checking email status: {str(e)}'}