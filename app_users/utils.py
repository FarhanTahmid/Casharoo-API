import logging
import random
import string
from google.auth.transport import requests
from google.oauth2 import id_token
from casharoo import settings
from django.utils import timezone
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
    
    def _validate_id_token(self, token, device_type:str):
        """
        Verify the Google ID token and extract user information
        """
        device_type_list=['ANDROID','IOS','DESKTOP','WEB']
        try:
            if not device_type:
                return False,"Device type must be specified"
            if device_type.upper() not in device_type_list:
                return False,f"Device type must be from: {device_type_list}"
            
            if device_type.upper()=="ANDROID":
                audience=settings.ANDROID_OAUTH2_CLIENT_ID
            
            # Verify the token with Google
            id_info = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                audience
            )
            
            # Check if token is issued by Google
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                return False,'Invalid token issuer'
                
            return id_info
            
        except ValueError as e:
            return False,f'Invalid token: {str(e)}'
        
    
    def _create_user_with_google(self,validated_data):
        user_data = validated_data['user_data']
        email = user_data.get('email')
        
        if not email:
            return False,"Email not provided by Google"
        
        # check if the user is already registered
        
        try:
            user=AppUser.objects.get(email=email)
            return False,"Account with this email already exists!"
        except AppUser.DoesNotExist:
            # Create new user
            user=AppUser.objects.create_user(
                email=email,
                first_name=user_data.get('given_name', ''),
                last_name=user_data.get('family_name', ''),
                provider='google',
                provider_id=user_data.get('id'),
                is_verified=True
            )
        return user