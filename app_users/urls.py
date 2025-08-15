from django.urls import path
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

]
