from django import forms
from django.contrib import admin
from .models import EmailAccounts, EmailTemplate, EmailLog


class EmailAccountsForm(forms.ModelForm):
    # Never render the stored password back into the page
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False), required=False,
        help_text="Leave blank to keep the current password."
    )

    class Meta:
        model = EmailAccounts
        fields = '__all__'

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not password:
            if not self.instance.pk:
                raise forms.ValidationError('Password is required.')
            return self.instance.password
        return password


@admin.register(EmailAccounts)
class EmailAccountsAdmin(admin.ModelAdmin):
    form = EmailAccountsForm
    list_display = ('name', 'email_address', 'purpose','smtp_server','smtp_port','is_active')
    list_filter = ('purpose','is_active','smtp_server','smtp_port','is_active')
    search_fields = ('name', 'email_address', 'smtp_server','purpose')

@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'purpose')
    list_filter = ('purpose',)
    search_fields = ('name', 'subject', 'body_text','body_html','purpose')

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('to_emails', 'subject', 'status', 'created_at','purpose')
    list_filter = ('status', 'created_at','purpose')
    search_fields = ('to_emails', 'subject', 'status','purpose')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
