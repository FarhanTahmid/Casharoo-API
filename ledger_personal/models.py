import pghistory
from django.db import models
from django.db.models import Q

from workspaces.models import WorkspaceOwnedModel


class Account(WorkspaceOwnedModel):
    """Where personal money sits: a wallet, a bank account, a bKash balance."""
    KIND_CHOICES = [
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('savings', 'Savings'),
        ('mobile_money', 'Mobile money'),
        ('card', 'Card'),
    ]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='cash')
    # One currency per account; every transaction on it carries the same code
    currency = models.CharField(max_length=3, default='BDT')
    opening_balance_minor = models.BigIntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.name} ({self.currency})"


class Category(WorkspaceOwnedModel):
    KIND_CHOICES = [
        ('expense', 'Expense'),
        ('income', 'Income'),
    ]
    DEFAULT_EXPENSE = [
        'Food', 'Transport', 'Housing', 'Utilities', 'Health', 'Education',
        'Shopping', 'Entertainment', 'Mobile & Internet', 'Gifts & Donations', 'Other',
    ]
    DEFAULT_INCOME = ['Salary', 'Business', 'Gift', 'Other income']

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='expense')

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.kind})"


@pghistory.track()
class Transaction(WorkspaceOwnedModel):
    KIND_CHOICES = [
        ('expense', 'Expense'),
        ('income', 'Income'),
        ('transfer', 'Transfer'),
    ]
    SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('sms', 'SMS'),
        ('email', 'Email'),
        ('upload', 'Statement upload'),
        ('ai', 'AI'),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='expense')
    # Signed, in minor units of `currency`: money into the account is positive
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, editable=False)
    # The two legs of a transfer between own accounts share this id
    transfer_group_id = models.UUIDField(null=True, blank=True)
    occurred_on = models.DateField()
    note = models.CharField(max_length=200, blank=True, default='')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual')

    class Meta:
        ordering = ['-occurred_on', '-created_at']
        indexes = [
            models.Index(fields=['workspace', 'account', 'occurred_on']),
            models.Index(fields=['workspace', 'category', 'occurred_on']),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(amount_minor=0), name='transaction_amount_not_zero'),
            models.CheckConstraint(
                condition=(
                    Q(kind='expense', amount_minor__lt=0, transfer_group_id__isnull=True)
                    | Q(kind='income', amount_minor__gt=0, transfer_group_id__isnull=True)
                    | Q(kind='transfer', transfer_group_id__isnull=False)
                ),
                name='transaction_sign_matches_kind',
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.amount_minor} {self.currency} on {self.occurred_on}"

    def get_parent_workspace_id(self):
        return self.account.workspace_id

    def save(self, *args, **kwargs):
        self.currency = self.account.currency
        super().save(*args, **kwargs)


class Budget(WorkspaceOwnedModel):
    """Monthly spending limit for one expense category."""
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='BDT')

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor__gt=0), name='budget_amount_positive'),
            models.UniqueConstraint(
                fields=['category'], condition=Q(deleted_at__isnull=True), name='one_budget_per_category'
            ),
        ]

    def __str__(self):
        return f"{self.category.name}: {self.amount_minor} {self.currency}"

    def get_parent_workspace_id(self):
        return self.category.workspace_id
