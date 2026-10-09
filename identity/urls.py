from django.urls import path
from . import views

app_name='identity'

urlpatterns = [
    path('me/', views.MeView.as_view(), name='me'),
    path('me/username/', views.ChangeUsernameView.as_view(), name='change-username'),
    path('me/username/check/', views.UsernameCheckView.as_view(), name='username-check'),
    path('me/avatar/', views.AvatarView.as_view(), name='avatar'),
]
