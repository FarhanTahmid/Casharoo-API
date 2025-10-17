import uuid
from django.db import models
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from app_users.models import AppUser

class CashBook(models.Model):
    id = models.UUIDField(null=False, blank=False, primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(AppUser, on_delete=models.CASCADE, null=False, blank=False)
    
    book_name = models.CharField(null=False, blank=False, max_length=100)
    description = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    last_edited_at = models.DateTimeField(null=True, blank=True, auto_now=True)
    
    class Meta:
        verbose_name = 'Cash Book'
        verbose_name_plural = 'Cash Books'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.book_name} - {self.owner.email}"
    
    def get_balance(self):
        """Calculate current balance"""
        from django.db.models import Sum, Q
        
        cash_in = self.entry_set.filter(entry_type='cash_in').aggregate(
            total=Sum('amount'))['total'] or 0
        cash_out = self.entry_set.filter(entry_type='cash_out').aggregate(
            total=Sum('amount'))['total'] or 0
        
        return cash_in - cash_out
    
    def has_permission(self, user, permission_type='view'):
        """Check if user has permission for this cashbook"""
        if self.owner == user:
            return True
        
        member = self.cashbookadditionalmember_set.filter(member=user).first()
        if not member:
            return False
        
        if permission_type == 'view':
            return True
        elif permission_type == 'edit':
            return member.role in ['editor', 'admin']
        elif permission_type == 'admin':
            return member.role == 'admin'
        
        return False


class CashBookAdditionalMember(models.Model):
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('editor', 'Editor'),
        ('admin', 'Admin'),
    ]
    
    id = models.UUIDField(null=False, blank=False, primary_key=True, default=uuid.uuid4, editable=False)
    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, null=False)
    member = models.ForeignKey(AppUser, on_delete=models.CASCADE, null=False, blank=False)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
    
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(AppUser, on_delete=models.SET_NULL, null=True, related_name='members_added')
    
    class Meta:
        verbose_name = 'Cash Book Additional Member'
        verbose_name_plural = 'Cash Book Additional Members'
        unique_together = ['cashbook', 'member']
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.member.email} - {self.role} in {self.cashbook.book_name}"


class EntryCategory(models.Model):
    GENERAL_CATEGORIES = [
        'Housing', 'Transportation', 'Food', 'Utilities', 'Clothing', 'Medical/Healthcare',
        'Insurance', 'Household Items/Supplies', 'Personal', 'Debt', 'Retirement', 'Education',
        'Savings', 'Gifts/Donations', 'Entertainment', 'Income', 'Other'
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, null=False, blank=False)
    category_name = models.CharField(max_length=100, null=False, blank=False)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    
    class Meta:
        verbose_name = "Entry Category"
        verbose_name_plural = "Entry Categories"
        unique_together = ['cashbook', 'category_name']
        indexes = [
            models.Index(fields=["cashbook", "category_name"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ['category_name']
    
    def __str__(self):
        return f"{self.category_name} - {self.cashbook.book_name}"


class PaymentMethod(models.Model):
    GENERAL_PAYMENT_METHODS = [
        'Cash', 'Credit Card', 'Debit Card', 'bKash', 'Nagad', 
        'Rocket', 'Bank Transfer', 'Online', 'Other'
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, null=False, blank=False)
    payment_method_name = models.CharField(max_length=100, null=False, blank=False)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    
    class Meta:
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"
        unique_together = ['cashbook', 'payment_method_name']
        indexes = [
            models.Index(fields=["cashbook", "payment_method_name"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ['payment_method_name']
    
    def __str__(self):
        return f"{self.payment_method_name} - {self.cashbook.book_name}"


class Entry(models.Model):
    ENTRY_TYPES = (
        ('cash_in', 'Cash In'),
        ('cash_out', 'Cash Out'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cashbook = models.ForeignKey(CashBook, on_delete=models.CASCADE, null=False, blank=False)
    category = models.ForeignKey(EntryCategory, on_delete=models.SET_NULL, null=True, blank=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(AppUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='entries_created')
    
    entry_type = models.CharField(null=False, blank=False, choices=ENTRY_TYPES, default='cash_out', max_length=10)
    amount = models.DecimalField(null=False, blank=False, decimal_places=2, max_digits=15)
    
    title = models.CharField(max_length=200, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)
    
    entry_date = models.DateField(null=False, blank=False)
    timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Cashbook Entry"
        verbose_name_plural = "Cashbook Entries"
        ordering = ['-entry_date', '-timestamp']
        indexes = [
            models.Index(fields=['cashbook', 'entry_date']),
            models.Index(fields=['entry_type']),
            models.Index(fields=['created_by']),
        ]
    
    def __str__(self):
        return f"{self.title or self.entry_type} - {self.amount} - {self.cashbook.book_name}"


def get_user_bill_filepath(instance, filename):
    return f"user_files/cashbook/{instance.entry.cashbook.id}/entry_{instance.entry.id}/bills/{filename}"


class EntryBills(models.Model):
    allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png']

    id = models.UUIDField(null=False, blank=False, primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name='bills')
    
    bill_file = models.FileField(
        null=False, 
        blank=False, 
        upload_to=get_user_bill_filepath,
        validators=[
            FileExtensionValidator(
                allowed_extensions=allowed_extensions,
                message='Please upload a valid file. Allowed formats are: %(allowed_extensions)s'
            )
        ]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Bill of Entry"
        verbose_name_plural = "Bills of Entries"
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Bill for {self.entry.title or self.entry.id}"


class EntryExtraFields(models.Model):
    id = models.UUIDField(null=False, blank=False, primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name='extra_fields')
    
    field_name = models.CharField(null=False, blank=False, max_length=100)
    field_value = models.TextField(null=False, blank=False)
    
    class Meta:
        verbose_name = "Extra Field of Entry"
        verbose_name_plural = "Extra Fields of Entries"
        indexes = [
            models.Index(fields=["entry", "field_name"]),
        ]
    
    def __str__(self):
        return f"{self.field_name}: {self.field_value} - {self.entry.title or self.entry.id}"