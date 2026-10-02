from rest_framework import serializers
from .models import AppUser


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = AppUser
        fields = ('id', 'email', 'username', 'first_name', 'last_name',
                 'full_name', 'bio', 'phone', 'profile_picture', 'date_joined')
        read_only_fields = ('id', 'email', 'username', 'date_joined')
