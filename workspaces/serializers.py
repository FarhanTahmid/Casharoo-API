from rest_framework import serializers

from casharoo.money import validate_currency
from .models import Workspace, Membership


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            'id', 'name', 'kind', 'owner', 'default_currency', 'role',
            'version', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'kind', 'owner', 'version', 'created_at', 'updated_at']

    def get_role(self, obj) -> str:
        return obj.role_of(self.context['request'].user)

    def validate_default_currency(self, value):
        return validate_currency(value)


class MembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Membership
        fields = ['id', 'user', 'user_email', 'role', 'created_at']
        read_only_fields = fields
