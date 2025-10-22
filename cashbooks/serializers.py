from rest_framework import serializers
from django.db import transaction
from .models import (
    CashBook, CashBookAdditionalMember, EntryCategory,
    PaymentMethod, Entry, EntryBills, EntryExtraFields
)


class CashBookAdditionalMemberSerializer(serializers.ModelSerializer):
    member_email = serializers.EmailField(source='member.email', read_only=True)
    member_username = serializers.CharField(source='member.username', read_only=True)
    added_by_email = serializers.EmailField(source='added_by.email', read_only=True)
    
    class Meta:
        model = CashBookAdditionalMember
        fields = ['id', 'member', 'member_email', 'member_username', 'role', 'added_at', 'added_by', 'added_by_email']
        read_only_fields = ['id', 'added_at', 'added_by']


class EntryCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryCategory
        fields = ['id', 'category_name', 'is_default', 'created_at']
        read_only_fields = ['id', 'is_default', 'created_at']


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'payment_method_name', 'is_default', 'created_at']
        read_only_fields = ['id', 'is_default', 'created_at']


class EntryBillsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryBills
        fields = ['id', 'bill_file', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class EntryExtraFieldsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntryExtraFields
        fields = ['id', 'field_name', 'field_value']
        read_only_fields = ['id']


class EntryListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    payment_method_name = serializers.CharField(source='payment_method.payment_method_name', read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    bills_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Entry
        fields = [
            'id', 'entry_type', 'amount', 'title', 'entry_date', 
            'category', 'category_name', 'payment_method', 'payment_method_name',
            'created_by', 'created_by_email', 'bills_count', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp', 'created_by']
    
    def get_bills_count(self, obj):
        return obj.bills.count()


class EntryDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.category_name', read_only=True)
    payment_method_name = serializers.CharField(source='payment_method.payment_method_name', read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    bills = EntryBillsSerializer(many=True, read_only=True)
    extra_fields = EntryExtraFieldsSerializer(many=True, read_only=True)
    
    class Meta:
        model = Entry
        fields = [
            'id', 'entry_type', 'amount', 'title', 'remarks', 'entry_date',
            'category', 'category_name', 'payment_method', 'payment_method_name',
            'created_by', 'created_by_email', 'bills', 'extra_fields',
            'timestamp', 'updated_at'
        ]
        read_only_fields = ['id', 'timestamp', 'updated_at', 'created_by']


class EntryCreateUpdateSerializer(serializers.ModelSerializer):
    extra_fields_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False
    )
    
    class Meta:
        model = Entry
        fields = [
            'id', 'entry_type', 'amount', 'title', 'remarks', 'entry_date',
            'category', 'payment_method', 'extra_fields_data'
        ]
        read_only_fields = ['id']
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value
    
    def create(self, validated_data):
        extra_fields_data = validated_data.pop('extra_fields_data', [])
        
        with transaction.atomic():
            entry = Entry.objects.create(**validated_data)
            
            # Create extra fields
            for field_data in extra_fields_data:
                EntryExtraFields.objects.create(
                    entry=entry,
                    field_name=field_data.get('field_name'),
                    field_value=field_data.get('field_value')
                )
        
        return entry
    
    def update(self, instance, validated_data):
        extra_fields_data = validated_data.pop('extra_fields_data', None)
        
        with transaction.atomic():
            # Update entry
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            
            # Update extra fields if provided
            if extra_fields_data is not None:
                instance.extra_fields.all().delete()
                for field_data in extra_fields_data:
                    EntryExtraFields.objects.create(
                        entry=instance,
                        field_name=field_data.get('field_name'),
                        field_value=field_data.get('field_value')
                    )
        
        return instance


class CashBookListSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    balance = serializers.SerializerMethodField()
    members_count = serializers.SerializerMethodField()
    entries_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CashBook
        fields = [
            'id', 'book_name', 'description', 'owner', 'owner_email',
            'balance', 'members_count', 'entries_count',
            'created_at', 'last_edited_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'last_edited_at']
    
    def get_balance(self, obj):
        return float(obj.get_balance())
    
    def get_members_count(self, obj):
        return obj.cashbookadditionalmember_set.count()
    
    def get_entries_count(self, obj):
        return obj.entry_set.count()


class CashBookDetailSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    balance = serializers.SerializerMethodField()
    members = CashBookAdditionalMemberSerializer(source='cashbookadditionalmember_set', many=True, read_only=True)
    categories = EntryCategorySerializer(source='entrycategory_set', many=True, read_only=True)
    payment_methods = PaymentMethodSerializer(source='paymentmethod_set', many=True, read_only=True)
    
    class Meta:
        model = CashBook
        fields = [
            'id', 'book_name', 'description', 'owner', 'owner_email',
            'balance', 'members', 'categories', 'payment_methods',
            'created_at', 'last_edited_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'last_edited_at']
    
    def get_balance(self, obj):
        return float(obj.get_balance())


class CashBookCreateUpdateSerializer(serializers.ModelSerializer):
    
    balance = serializers.SerializerMethodField()

    class Meta:
        model = CashBook
        fields = ['id', 'book_name', 'description','created_at','last_edited_at','balance']
        read_only_fields = ['id']
    
    def create(self, validated_data):
        with transaction.atomic():
            cashbook = CashBook.objects.create(**validated_data)
            
            # Create default categories
            for category_name in EntryCategory.GENERAL_CATEGORIES:
                EntryCategory.objects.create(
                    cashbook=cashbook,
                    category_name=category_name,
                    is_default=True
                )
            
            # Create default payment methods
            for method_name in PaymentMethod.GENERAL_PAYMENT_METHODS:
                PaymentMethod.objects.create(
                    cashbook=cashbook,
                    payment_method_name=method_name,
                    is_default=True
                )
        
        return cashbook
    def get_balance(self, obj):
        return float(obj.get_balance())