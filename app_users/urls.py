from django.urls import path,include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name='app_users'

urlpatterns = [
    # Authentication
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('auth-status/', views.AuthStatusView.as_view(), name='auth_status'),
    
    path('token-refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Email Verification
    path('send_verification_code/', views.AccountVerification.as_view({'get': 'send_verification_code'}), name='send_verification_code'),
    path('verify_account/',views.AccountVerification.as_view({'post':'verify_account'}),name='verify_account'),
    
    # Password reset and forgot password
    
    
]
