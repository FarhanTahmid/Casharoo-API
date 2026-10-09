from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit.utils.audit_utils import AuditLogMixin
from . import services
from .serializers import (
    AvatarUploadSerializer,
    ChangeUsernameSerializer,
    UserProfileSerializer,
    UsernameCheckSerializer,
)
from .usernames import suggestions, validate_username


class MeView(generics.RetrieveUpdateAPIView):
    """
    Profile of the signed-in user.

    Sign-up, login (email or username), logout, email verification, password
    reset and change, Google sign-in, MFA and session management are served by
    django-allauth's headless API under /_allauth/app/v1/.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UsernameCheckView(APIView):
    """Whether the signed-in user can take this username. Called as they type"""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'username_check'

    @extend_schema(
        parameters=[OpenApiParameter('username', OpenApiTypes.STR, required=True)],
        responses=UsernameCheckSerializer,
    )
    def get(self, request):
        username = request.query_params.get('username', '').strip()
        result = {'available': True, 'current': False, 'reason': None, 'message': None, 'suggestions': []}
        try:
            validate_username(username, request.user)
            result['current'] = username.lower() == request.user.username.lower()
        except DjangoValidationError as error:
            result.update(available=False, reason=error.code, message=error.messages[0])
            if error.code == 'taken':
                result['suggestions'] = suggestions(username)
        return Response(result)


class ChangeUsernameView(AuditLogMixin, APIView):
    """Change the username. Needs the password, unless the account has none (Google sign-in)"""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'profile_sensitive'

    @extend_schema(request=ChangeUsernameSerializer, responses=UserProfileSerializer)
    def post(self, request):
        serializer = ChangeUsernameSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            old = services.change_username(request.user, serializer.validated_data['username'])
        except DjangoValidationError as error:
            raise ValidationError({'username': error.messages})
        request.user.refresh_from_db()
        self.log_action(
            request, 'UPDATE', 'AppUser', request.user.pk,
            changes={'username': {'old': old, 'new': request.user.username}},
            operation='username_changed',
        )
        return Response(UserProfileSerializer(request.user, context={'request': request}).data)


class AvatarView(AuditLogMixin, APIView):
    """
    The signed-in user's profile picture. The app crops it; the server checks
    it is a real picture and stores a small square JPEG.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_throttles(self):
        if self.request.method in ('POST', 'DELETE'):
            self.throttle_scope = 'profile_sensitive'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @extend_schema(responses={(200, 'image/jpeg'): OpenApiTypes.BINARY})
    def get(self, request):
        picture = request.user.profile_picture
        if not picture or not picture.storage.exists(picture.name):
            raise Http404
        response = FileResponse(picture.open('rb'), content_type='image/jpeg')
        # The URL changes with the picture, so it can be kept
        response['Cache-Control'] = 'private, max-age=31536000, immutable'
        return response

    @extend_schema(request={'multipart/form-data': AvatarUploadSerializer}, responses=UserProfileSerializer)
    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data['file']
        try:
            services.set_avatar(request.user, upload)
        except DjangoValidationError as error:
            raise ValidationError({'file': error.messages})
        self.log_action(request, 'UPDATE', 'AppUser', request.user.pk,
                        changes={'profile_picture': upload}, operation='avatar_changed')
        return Response(UserProfileSerializer(request.user, context={'request': request}).data)

    @extend_schema(responses={204: None})
    def delete(self, request):
        services.remove_avatar(request.user)
        self.log_action(request, 'DELETE', 'AppUser', request.user.pk, operation='avatar_removed')
        return Response(status=status.HTTP_204_NO_CONTENT)
