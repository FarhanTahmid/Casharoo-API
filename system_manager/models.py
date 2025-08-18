from django.db import models

# Create your models here.

class EmailAccounts(models.Model):
    name = models.CharField(max_length=100, help_text="Friendly name for this email account")
    email_address = models.EmailField(max_length=100, help_text="Email address to send from")
    smtp_server = models.CharField(max_length=100, help_text="SMTP server address")
    smtp_port = models.IntegerField(default=465, help_text="SMTP server port")
    username = models.CharField(max_length=100, help_text="SMTP username",null=True,blank=True)
    password = models.CharField(max_length=100, help_text="SMTP password (Use app password for gmail accounts!)")
    use_tls = models.BooleanField(default=False, help_text="Use TLS for connection")
    use_ssl = models.BooleanField(default=True, help_text="Use SSL for connection")
    is_active = models.BooleanField(default=True, help_text="Is this account active?")
    
    PURPOSE_CHOICES = [
        ('default','Default'),
        ('marketing', 'Marketing Emails'),
        ('transactional', 'Transactional Emails'),
        ('notification', 'Notification Emails'),
        ('support', 'Support Emails'),
        ('auth','Authentication'),
        ('no-reply','No Reply'),
        ('other', 'Other'),
    ]
    
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, help_text="Email purpose")

    class Meta:
        verbose_name = "Email Account"
        verbose_name_plural = "Email Accounts"
    
    def __str__(self):
        return str(self.pk)

class EmailTemplate(models.Model):
    """Model to store email templates"""
    name = models.CharField(max_length=100, help_text="Template name (e.g: auth_signup)",unique=True)
    subject = models.CharField(max_length=200, help_text="Email subject")
    body_text = models.TextField(help_text="Plain text email body")
    body_html = models.TextField(blank=True, null=True, help_text="HTML email body")
    
    PURPOSE_CHOICES = [
        ('default','Default'),
        ('marketing', 'Marketing Emails'),
        ('transactional', 'Transactional Emails'),
        ('notification', 'Notification Emails'),
        ('support', 'Support Emails'),
        ('auth','Authentication'),
        ('other', 'Other'),
    ]
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, help_text="Template purpose")
    
    def __str__(self):
        return str(self.pk)

class EmailLog(models.Model):
    """
    Model to track email sending status and history
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('RETRY', 'Retry'),
    )
    
    to_emails = models.TextField()  # Store as comma-separated list
    sender_email = models.EmailField(null=True, blank=True)
    subject = models.CharField(max_length=255)
    purpose = models.CharField(max_length=100, default='default')
    template_name = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'
    
    def __str__(self):
        return f"{self.subject} - {self.status} - {self.created_at}"