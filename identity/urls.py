from django.urls import path
from . import views

app_name='identity'

urlpatterns = [
    path('me/', views.MeView.as_view(), name='me'),
]
