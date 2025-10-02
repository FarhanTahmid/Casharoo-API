import logging
from rest_framework import status, generics, permissions,viewsets
from rest_framework.decorators import api_view, permission_classes,action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings
from django.template.loader import render_to_string
from .models import AppUser,EmailVerification
from .serializers import (
    AppUserRegistrationSerializer, AppUserLoginSerializer,
    PasswordResetSerializer, PasswordResetConfirmSerializer,
    UserProfileSerializer, ChangePasswordSerializer
)
from .utils import AuthUtils

def get_tokens_for_user(user):
    """Generate JWT tokens for user"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class AuthStatusView(APIView):
    """Check if user is authenticated or not"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    logger=logging.getLogger('app_users.views.AuthStatusView')
    
    def get(self, request):
        '''Check if the user is authenticated and return user details'''
        try:
            user=request.user
            serializer = UserProfileSerializer(user)
            return Response({
                'isAuthenticated': True,
                'user_data': serializer.data
            }, status=status.HTTP_200_OK)
        except (InvalidToken, TokenError) as e:
            return Response({
                'isAuthenticated': False,
                'error': 'Invalid or expired token',
                'detail': str(e)
            }, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            self.logger.error(f"Exception occured while checking auth status: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong!"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class RegisterView(APIView):
    """User registration with email and password"""
    permission_classes = [permissions.AllowAny]
    logger=logging.getLogger('app_users.views.RegisterView')

    def post(self, request):
        try:
            serializer = AppUserRegistrationSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.save()
                tokens = get_tokens_for_user(user)
                
                return Response({
                    'message': 'User registered successfully',
                    'user': UserProfileSerializer(user).data,
                    'tokens': tokens
                }, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            self.logger.error(f"Exception occured while registering user: {e}",exc_info=True)
            return Response({
                'error':"Something went wrong! Please try again later."
            },status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(APIView):
    """User login with email and password"""
    permission_classes = [permissions.AllowAny]
    logger=logging.getLogger('app_users.views.LoginView')

    def post(self, request):
        try:
            serializer = AppUserLoginSerializer(data=request.data, context={'request': request})
            if serializer.is_valid():
                user = serializer.validated_data['user']
                tokens = get_tokens_for_user(user)
                
                return Response({
                    'message': 'Login successful',
                    'user': UserProfileSerializer(user).data,
                    'tokens': tokens
                }, status=status.HTTP_200_OK)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            self.logger.error(f"Error occured while login {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong! Please try again later."}
            )

class LogoutView(APIView):
    """Logout user by blacklisting refresh token"""
    permission_classes = [permissions.IsAuthenticated]
    logger=logging.getLogger('app_users.views.LogoutView')

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            self.logger.error(f"Exception occured while logging out: {e}",exc_info=True)
            return Response({
                'error': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)

class AccountVerification(viewsets.ViewSet):
    '''Verify account of the user by sending verification code via email address'''
    permission_classes=[permissions.IsAuthenticated]
    logger=logging.getLogger('app_users.views.AccountVerification')
    
    @action(detail=False,methods=['get'])
    def send_verification_code(self,request):
        '''Send verification code to user's email address'''
        try:
            user=AppUser.objects.get(id=request.user.id)
            if user.is_verified:
                return Response(
                    {'error':"User is already verified"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            previous_unused_codes=EmailVerification.objects.filter(user=user,is_used=False)
            if previous_unused_codes:
                for codes in previous_unused_codes:
                    codes.expires_at=timezone.now()
                    codes.save()
            auth_utils=AuthUtils()
            email_status,message=auth_utils._send_verification_code(user=user)
            if email_status:
                return Response({
                    'message':message
                },status=status.HTTP_200_OK)
            else:
                return Response({
                    'error':message
                },status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            self.logger.error(f"Error while sending verification code: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong! Please try again later!"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False,methods=['post'])
    def verify_account(self,request):
        try:
            verification_code=request.data.get('verification_code')
            user=AppUser.objects.get(id=request.user.id)
            
            auth_utils=AuthUtils()
            verification_status,message=auth_utils._verify_user(user=user,verification_code=verification_code)
            
            if verification_status:
                user.is_verified=True
                user.save()
                return Response(
                    {'message':message},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error':message},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            self.logger.error(f"Error while verifying account: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong!"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ForgotPasswordViewset(viewsets.ViewSet):
    permission_classes=[permissions.AllowAny]
    logger=logging.getLogger('app_users.views.ForgotPasswordViewset')

    @action(detail=False,methods=['post'])
    def send_verification_code(self,request):
        '''Send verification code to given email'''
        try:
            # As emails are unique, search user with this email and send the code to that email
            get_email=request.data.get('email')
            
            # get user with the email
            try:
                user=AppUser.objects.get(email=get_email)
            except AppUser.DoesNotExist:
                return Response(
                    {'error':"No account is associated with this email."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if user:
                auth_utils=AuthUtils()
                previous_unused_codes=EmailVerification.objects.filter(user=user,is_used=False)
                if previous_unused_codes:
                    for codes in previous_unused_codes:
                        codes.expires_at=timezone.now()
                        codes.save()
                email_status,message=auth_utils._send_verification_code(user=user)
                if email_status:
                    return Response({
                        'message':message
                    },status=status.HTTP_200_OK)
                else:
                    return Response({
                        'error':message
                    },status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            self.logger.error(f"Error while sending verification code: {e}",exc_info=True)
            return Response(
                {'error':"Can not send email at this time. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False,methods=['post'])
    def verify_code(self,request):
        try:
            verification_code=request.data.get('verification_code')
            email=request.data.get('email')
            
            if not verification_code or not email:
                return Response(
                    {'error':"verification_code and email is required!"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                user=AppUser.objects.get(email=email)
            except AppUser.DoesNotExist:
                return Response(
                    {'error':"No user found with this email address"}
                )
            auth_utils=AuthUtils()
            verification_status,message=auth_utils._verify_user(user=user,verification_code=verification_code)
            
            if verification_status:
                user.is_verified=True
                user.save()
                return Response(
                    {'message':message},
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error':message},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            self.logger.error(f"Error while verifying code: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong!"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False,methods=['post'])
    def reset_password(self,request):
        '''Reset the account password with new password'''
        try:
            # email will be sent by frontend by a secured way
            email=request.data.get('email')
            new_password=request.data.get('password')
            if email and new_password:
                # get user by email
                try:
                    user=AppUser.objects.get(email=email)
                except AppUser.DoesNotExist:
                    return Response(
                        {'error':"Can not reset password! Please try again later"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                if user:
                    # update password
                    user.set_password(new_password)
                    user.save()
                    return Response(
                        {'message':"Password was updated! Login with new credentials"},
                        status=status.HTTP_200_OK
                    )
            else:
                return Response(
                    {'error':"Missing fields!"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            self.logger.error(f"Error while sending resetting password: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong! Please try again later!"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class ChangePasswordViewset(viewsets.ViewSet):
    permission_classes=[permissions.IsAuthenticated]
    logger=logging.getLogger('app_users.views.ChangePasswordViewset')

    @action(detail=False,methods=['post'])
    def change_password(self,request):
        try:
            # change password
            current_password=request.data.get('current_password')
            new_password=request.data.get('new_password')
            
            if current_password and new_password:
                if not request.user.check_password(current_password):
                    return Response(
                        {'error':"Incorrect current password!"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if request.user.check_password(new_password):
                    return Response({
                        'error': 'New password must be different from current password'
                    }, status=status.HTTP_400_BAD_REQUEST)
                # update password
                request.user.set_password(new_password)
                request.user.save()
                return Response(
                    {'message':"Password was changed successfully!"},
                    status=status.HTTP_200_OK
                )

            else:
                return Response(
                    {'error':"Missing fields!"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            self.logger.error(f"Error while changing password: {e}",exc_info=True)
            return Response(
                {'error':"Something went wrong. Please try again later!"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GoogleAuth(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    
    @action(detail=False, methods=['post'])
    def google_auth(self, request):
        """
        Authenticate user with Google OAuth
        
        Expected payload:
        {
            "id_token": "google_id_token_here",
            "device_type": "device type here" # e.g: "ANDROID","IOS","DESKTOP","WEBAPP"
        }
        """
        # Get id_token and device_type from payload
        id_token = request.data.get('id_token')
        device_type = request.data.get('device_type')
        
        if not id_token or not device_type:
            return Response(
                {
                    'success': False,
                    'error': "Both id_token and device_type are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        auth_utils = AuthUtils()
        
        # Step 1: Validate the Google ID token
        id_info, message = auth_utils._validate_id_token(
            token=id_token, 
            device_type=device_type
        )
        if id_info is None:
            return Response(
                {
                    'success': False,
                    'error': message
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Step 2: Create or get user with Google data
        user, user_message = auth_utils._create_or_get_user_with_google(id_info)
        
        if user is None:
            return Response(
                {
                    'success': False,
                    'error': user_message
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Step 3: Generate JWT tokens
        tokens = auth_utils._generate_tokens(user)
        
        if tokens is None:
            return Response(
                {
                    'success': False,
                    'error': "Failed to generate authentication tokens"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Step 4: Get user data for response
        user_data = auth_utils._get_user_data(user)
        
        # Step 5: Return success response
        return Response(
            {
                'success': True,
                'message': 'Authentication successful',
                'user': user_data,
                'tokens': tokens
            },
            status=status.HTTP_200_OK
        )        

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_detail(request):
    """Get current user details"""
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def check_email_exists(request):
    """Check if email already exists"""
    email = request.data.get('email')
    if not email:
        return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    exists = AppUser.objects.filter(email=email).exists()
    return Response({'exists': exists})

