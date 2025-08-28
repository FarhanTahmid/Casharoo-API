import logging
import random
import string
from google.auth.transport import requests
from google.oauth2 import id_token
from casharoo import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from system_manager.models import EmailLog
from system_manager.utils.email_handler import EmailHandler
from app_users.models import EmailVerification,AppUser

class AuthUtils:
    logger=logging.getLogger('app_users.utils.AuthUtils')

    def _send_verification_code(self,user):
        """
        Generate and send verification code to user's email addresses.
        
        Args:
            user (User): The user object to send verification code to
            
        Returns:
            tuple: (email_status, message)
                - email_status (bool): True if email sent successfully
                - message (str): Success or error message
                
        Notes:
        - Verification code is 6 digits
        - Code expires in 5 minutes
        - Sent to both personal and office emails if available
        """
        try:
            # Generate random code
            code = ''.join(random.choices(string.digits, k=6))
            
            # Set expiration time (5 minutes)
            expires_at = timezone.now() + timedelta(minutes=5)
            
            # Save verification code
            EmailVerification.objects.create(user=user,verification_code=code,expires_at=expires_at)
            
            # send the verification code to user email
            context_data={
                'verification_code':code,
                'username':user.username,
            }
            # Send the email
            email_service=EmailHandler()
            
            email_status,email_message,log_id=email_service.send_email(
                to_emails=[user.email],
                subject="Email Verification for new Signup",
                text_content=f"Please verify your email using the code below!",
                purpose='auth',
                template_name='account_verification',
                context_data=context_data,
                attachments=None
            )
            # get the email log object
            email_log=EmailLog.objects.get(id=log_id)
            if email_log.status=='SENT':
                return email_status,email_message
        except Exception as e:
            self.logger.error(f"Exception occured while sending email! Error: {e}")
        
    
    def _verify_user(self,user,verification_code):
        try:
            try:
                verification_obj=EmailVerification.objects.get(
                    user=user,verification_code=verification_code
                )
            except EmailVerification.DoesNotExist:
                return False,"Incorrect Verification Code"
            if verification_obj.is_used:
                return False,"This code has already been used!"
            if verification_obj.is_expired:
                return False,"Verification code has expired!"
            else:
                verification_obj.is_used=True
                verification_obj.save()
                return True,"Email verification was successful!"
        except Exception as e:
            self.logger.error(f"Error occured while verifying user! {e}")
            return False,"Can not verify your account now! Please try again later."
    
    # Google Auth Utils
    
    def _validate_id_token(self, token, device_type: str):
        """
        Verify the Google ID token and extract user information
        """
        device_type_list = ['ANDROID', 'IOS', 'DESKTOP', 'WEBAPP']
        try:
            if not device_type:
                return None, "Device type must be specified"
            if device_type.upper() not in device_type_list:
                return None, f"Device type must be from: {device_type_list}"
            
            if device_type.upper() == "ANDROID":
                audience = settings.ANDROID_OAUTH2_CLIENT_ID
            else:
                audience = None
            
            if audience is None:
                return None, f"Audience not configured for device type: {device_type}"
                
            # Verify the token with Google
            try:
                id_info = id_token.verify_oauth2_token(
                    token, 
                    requests.Request(), 
                    audience
                )
            except Exception as e:
                return None, f"Cannot validate id token: {str(e)}"
            
            # Check if token is issued by Google
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                return None, 'Invalid token issuer'
                
            return id_info, "Validated id token!"
            
        except ValueError as e:
            return None, f'Invalid token: {str(e)}'
    
    def _create_or_get_user_with_google(self, user_data):
        """
        Create or get user from Google OAuth data
        Similar to serializer logic but in utility function
        """
        email = user_data.get('email')
        google_id = user_data.get('sub')  # Google uses 'sub' for user ID
        first_name = user_data.get('given_name', '')
        last_name = user_data.get('family_name', '')
        
        if not email:
            return None, "Email not provided by Google"
        
        # Try to find existing user by email
        try:
            user = AppUser.objects.get(email=email)
            
            # Donot login if user exists with same email but wasn't created via Google
            if user.provider != 'google':          
                return None, "An account is already registered with this email!"
            else:
                return user,"User found!"            
        except AppUser.DoesNotExist:
            # Create new user
            try:
                user = AppUser.objects.create_user(
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    provider='google',
                    provider_id=google_id,
                    is_verified=True  # Google accounts are pre-verified
                )
                return user, "New user created"
                
            except Exception as e:
                return None, f"Failed to create user: {str(e)}"
    
    def _generate_tokens(self, user):
        """
        Generate JWT tokens for user
        """
        try:
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Update last login
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            return {
                'access': str(access_token),
                'refresh': str(refresh),
            }
        except Exception as e:
            return None
    
    def _get_user_data(self, user):
        """
        Get user data for response
        """
        return {
            'id': str(user.id),
            'email': user.email,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'full_name': user.full_name,
            'is_verified': user.is_verified,
            'provider': user.provider,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'date_joined': user.date_joined.isoformat(),
        }