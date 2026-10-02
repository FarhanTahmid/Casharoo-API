from rest_framework import generics, permissions

from .serializers import UserProfileSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """
    Profile of the signed-in user.

    Sign-up, login, logout, email verification, password reset and change,
    Google sign-in, MFA and session management are served by django-allauth's
    headless API under /_allauth/app/v1/.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
