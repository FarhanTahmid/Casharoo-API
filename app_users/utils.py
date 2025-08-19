import random
import string
from django.utils import timezone
from datetime import timedelta
from app_users.models import EmailVerification

class AuthUtils:
    
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
        # Generate random code
        code = ''.join(random.choices(string.digits, k=6))
        
        # Set expiration time (1 hours from now)
        expires_at = timezone.now() + timedelta(hours=1)