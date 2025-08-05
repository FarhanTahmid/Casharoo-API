from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from .models import AppUser
import requests

class AppUserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = AppUser
        fields = ('email', 'password', 'password_confirm', 'first_name', 'last_name')
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Two Passwords don't match")
        return attrs
    def validate_email(self, value):
        if AppUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists")
        return value
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = AppUser.objects.create_user(**validated_data)
        return user

class AppUserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'),
                              username=email, password=password)
            
            if not user:
                if not AppUser.objects.filter(email=email).exists():
                    raise serializers.ValidationError('Invalid Email')
                else:
                    raise serializers.ValidationError('Invalid password')
            if not user.is_active:
                raise serializers.ValidationError('This User account is disabled.')
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError('Must include email and password.')

class GoogleAuthSerializer(serializers.Serializer):
    access_token = serializers.CharField()

    def validate_access_token(self, access_token):
        # Verify Google access token
        google_user_info_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(google_user_info_url, headers=headers)
            if response.status_code != 200:
                raise serializers.ValidationError('Invalid Google access token')
            
            user_data = response.json()
            return {
                'access_token': access_token,
                'user_data': user_data
            }
        except requests.RequestException:
            raise serializers.ValidationError('Failed to verify Google access token')

    def create(self, validated_data):
        user_data = validated_data['user_data']
        email = user_data.get('email')
        
        if not email:
            raise serializers.ValidationError('Email not provided by Google')

        # Check if user already exists
        try:
            user = AppUser.objects.get(email=email)
            # Update user info from Google if needed
            if not user.first_name and user_data.get('given_name'):
                user.first_name = user_data.get('given_name')
            if not user.last_name and user_data.get('family_name'):
                user.last_name = user_data.get('family_name')
            if user.provider == 'email':
                user.provider = 'google'
                user.provider_id = user_data.get('id')
            user.is_verified = True
            user.save()
        except AppUser.DoesNotExist:
            # Create new user
            user = AppUser.objects.create_user(
                email=email,
                first_name=user_data.get('given_name', ''),
                last_name=user_data.get('family_name', ''),
                provider='google',
                provider_id=user_data.get('id'),
                is_verified=True
            )
        
        return user

class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = AppUser.objects.get(email=value, is_active=True)
            self.user = user
        except AppUser.DoesNotExist:
            # Don't reveal if email exists or not for security
            pass
        return value

class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uidb64']))
            user = AppUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, AppUser.DoesNotExist):
            raise serializers.ValidationError('Invalid reset link')

        if not default_token_generator.check_token(user, attrs['token']):
            raise serializers.ValidationError('Invalid or expired reset link')
        
        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = AppUser
        fields = ('id', 'email', 'username', 'first_name', 'last_name', 
                 'full_name', 'bio', 'phone', 'profile_picture', 'date_joined',
                 'provider', 'is_verified')
        read_only_fields = ('id', 'email', 'username', 'date_joined', 'provider')

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match")
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect')
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
