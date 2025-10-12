import uuid
from django.db import models
from django.core.validators import FileExtensionValidator
from app_users.models import AppUser

class CashBook(models.Model):
    id=models.UUIDField(null=False,blank=False,primary_key=True,editable=False)
    owner=models.ForeignKey(AppUser,on_delete=models.CASCADE,null=False,blank=False)
    
    book_name=models.CharField(null=False,blank=False,max_length=100)
    
    created_at=models.DateTimeField(null=False,blank=False,auto_now_add=True)
    last_edited_at=models.DateTimeField(null=True,blank=True)
    
    class Meta:
        verbose_name='Cash Book'
        verbose_name_plural='Cash Books'
    
    def __str__(self):
        return f"Cashbook ID: {self.id} -> Owner: {self.owner}"

class CashBookAdditionalMember(models.Model):
    id=models.UUIDField(null=False,blank=False,primary_key=True,editable=False)
    cashbook=models.ForeignKey(CashBook,on_delete=models.CASCADE,null=False)
    member=models.ForeignKey(AppUser,on_delete=models.DO_NOTHING,null=False,blank=False)
    
    class Meta:
        verbose_name='Cash Book External Member'
        verbose_name_plural='Cash Book External Members'

class EntryCategory(models.Model):
    
    GENERAL_CATEGORIES=[
        'Housing','Transportation','Food','Utilities','Clothing','Medical/Healthcare',
        'Insurance', 'Household Items/Supplies','Personal','Debt','Retirement','Education',
        'Savings','Gifts/Donations','Entertainment '
    ]
    
    id=models.UUIDField(primary_key=True,editable=False)
    cashbook=models.ForeignKey(CashBook,on_delete=models.CASCADE,null=False,blank=False)
    category_name=models.CharField(max_length=100,null=False,blank=False)
    
    created_at=models.DateTimeField(null=False,blank=False,auto_now_add=True)
    
    class Meta:
        verbose_name="Entry Category"
        verbose_name_plural="Entry Categories"
        indexes = [
            models.Index(fields=["cashbook", "category_name"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return f"Category: ID: {self.id} | Name: {self.category_name} -> Cashbook and Creator: Book ID:{self.cashbook.id} | Owner: {self.cashbook.owner.email}"

class PaymentMethod(models.Model):
    
    GENERAL_PAYMENT_METHODS=[
        'Cash','Credit Card','Debit Card','bKash','Nagad','Online','Offline'
    ]
    id=models.UUIDField(primary_key=True,editable=False)
    cashbook=models.ForeignKey(CashBook,on_delete=models.CASCADE,null=False,blank=False)
    payment_method_name=models.CharField(max_length=100,null=False,blank=False)
    
    created_at=models.DateTimeField(null=False,blank=False,auto_now_add=True)
    
    class Meta:
        verbose_name="Payment Method"
        verbose_name_plural="Payment Methods"
        indexes = [
            models.Index(fields=["cashbook", "payment_method_name"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return f"Payment Method: ID: {self.id} | Name: {self.payment_method_name} -> Cashbook and Creator: Book ID:{self.cashbook.id} | Owner: {self.cashbook.owner.email}"



class Entry(models.Model):
    
    ENTRY_TYPES=(
        ('Cash In','cash_in'),
        ('Cash Out','cash_out'),
    )
    
    id=models.UUIDField(primary_key=True,default=uuid.uuid4)
    cashbook=models.ForeignKey(CashBook,on_delete=models.CASCADE,null=False,blank=False)
    payment_method=models.ForeignKey(PaymentMethod,on_delete=models.SET_NULL,null=True,blank=True)
    additional_member=models.ForeignKey(CashBookAdditionalMember,on_delete=models.SET_NULL,null=True,blank=True)
    
    entry_type=models.CharField(null=False,blank=False,choices=ENTRY_TYPES,default='cash_in',max_length=10)
    amount=models.DecimalField(null=False,blank=False,decimal_places=2,max_digits=100)
    
    remarks=models.TextField(null=True,blank=True)
    
    timestamp=models.DateTimeField(null=False,blank=False,auto_now_add=True)
    
    class Meta:
        verbose_name="Cashbook Entry"
        verbose_name_plural="Cashbook Entries"
    
    def __str__(self):
        return f"Entry ID: {self.id} for Cashbook ID: {self.cashbook.id} | Type: {self.entry_type} | Amount: {self.amount}"


def get_user_bill_filepath(instance, filename):
    return f"user_files/cashbook/{instance.entry.cashbook.id}/entry_{instance.entry.id}/bills/{filename}"

class EntryBills(models.Model):
    
    allowed_extensions = ['pdf','jpg','jpeg','png']

    id=models.UUIDField(null=False,blank=False,primary_key=True,default=uuid.uuid4)
    entry=models.ForeignKey(Entry,on_delete=models.CASCADE)
    
    bill_file=models.FileField(null=False,blank=False,upload_to=get_user_bill_filepath,validators=[
            FileExtensionValidator(
                allowed_extensions=allowed_extensions,
                message='Please upload a valid file. Allowed formats are: %(allowed_extensions)s'
            )
        ])
    
    class Meta:
        verbose_name="Bill of Entry"
        verbose_name_plural="Bills of Entries"
    
    def __str__(self):
        return f"Bill ID: {self.id} for Entry ID: {self.entry.id} | Cashbook ID: {self.entry.cashbook.id}"

class EntryExtraFields(models.Model):
    
    id=models.UUIDField(null=False,blank=False,primary_key=True,default=uuid.uuid4)
    entry=models.ForeignKey(Entry,on_delete=models.CASCADE)
    
    field_name=models.CharField(null=False,blank=False,max_length=100)
    field_value=models.TextField(null=False,blank=False)
    
    class Meta:
        verbose_name="Extra Field of Entry"
        verbose_name_plural="Extra Fields of Entries"
        indexes = [
            models.Index(fields=["entry", "field_name"]),
        ]
    
    def __str__(self):
        return f"Extra Field ID: {self.id} | Name: {self.field_name} for Entry ID: {self.entry.id} | Cashbook ID: {self.entry.cashbook.id}"

   