from django.urls import path

from .views import PullView, PushView

app_name = 'sync'

urlpatterns = [
    path('pull/', PullView.as_view(), name='pull'),
    path('push/', PushView.as_view(), name='push'),
]
