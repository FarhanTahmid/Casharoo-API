from rest_framework import serializers
from .models import AppUser, UserSettings


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    # Kept on UserSettings, shown here so the app needs one call after login
    onboarded_at = serializers.DateTimeField(required=False, allow_null=True)
    primary_mode = serializers.ChoiceField(choices=UserSettings.MODE_CHOICES, required=False, allow_blank=True)

    SETTINGS_FIELDS = ('onboarded_at', 'primary_mode')

    class Meta:
        model = AppUser
        fields = ('id', 'email', 'username', 'first_name', 'last_name',
                 'full_name', 'bio', 'phone', 'profile_picture', 'date_joined',
                 'onboarded_at', 'primary_mode')
        read_only_fields = ('id', 'email', 'username', 'date_joined')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user_settings = UserSettings.objects.filter(user=instance).first()
        data['onboarded_at'] = (
            serializers.DateTimeField().to_representation(user_settings.onboarded_at)
            if user_settings and user_settings.onboarded_at else None
        )
        data['primary_mode'] = user_settings.primary_mode if user_settings else ''
        return data

    def update(self, instance, validated_data):
        changes = {field: validated_data.pop(field) for field in self.SETTINGS_FIELDS if field in validated_data}
        if changes:
            UserSettings.objects.update_or_create(user=instance, defaults=changes)
        return super().update(instance, validated_data)
