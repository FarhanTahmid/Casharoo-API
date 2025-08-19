from django.urls import path,include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name='app_users'

verification_routes=[
    path('send_verification_code/', views.AccountVerification.as_view({'get': 'send_verification_code'}), name='send_verification_code'),

]

urlpatterns = [
    # Authentication
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('auth-status/', views.AuthStatusView.as_view(), name='auth_status'),
    
    path('token-refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Email Verification
    path('verification/',include((verification_routes,'verification'),namespace='verification')),
    
]
