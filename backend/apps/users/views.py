from drf_spectacular.utils import extend_schema, inline_serializer
from apps.common.schema import DetailSerializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import User
from .serializers import (
    RegisterSerializer, UserSerializer, CustomTokenObtainPairSerializer, PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer, PasswordChangeSerializer, EmailVerifyConfirmSerializer,
)
from .services import queue_password_reset_email, queue_verification_email, revoke_all_sessions
from .throttles import LoginUsernameThrottle, PasswordResetEmailThrottle
from .tokens import user_from_verify_token

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle, LoginUsernameThrottle)
    throttle_scope = 'login'

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'register'
    serializer_class = RegisterSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        queue_verification_email(user)

class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user


@extend_schema(request=inline_serializer('LogoutRequest', {'refresh': serializers.CharField()}), responses={205: None, 400: DetailSerializer})
class LogoutView(APIView):
    """
    Blacklists the supplied refresh token so it can no longer mint access tokens.

    Deliberately not gated on a live access token: the refresh token is itself the proof of ownership, and an
    expired access token must not leave a 14-day refresh token impossible to revoke.
    """
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'login'

    def post(self, request):
        refresh = request.data.get('refresh') if hasattr(request.data, 'get') else None
        if not refresh or not isinstance(refresh, str):
            return Response({'refresh': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


@extend_schema(request=PasswordResetRequestSerializer, responses={202: DetailSerializer})
class PasswordResetRequestView(APIView):
    """
    Always answers 202 with the same body, whether or not the address belongs to an account (no enumeration).
    The e-mail is sent by a Celery task after commit, so response time does not reveal it either.
    """
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle, PasswordResetEmailThrottle)
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        for user in User.objects.filter(email__iexact=email, is_active=True):
            if user.has_usable_password():
                queue_password_reset_email(user)
        return Response({'detail': 'If an account exists for that address, a reset link is on its way.'}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=PasswordResetConfirmSerializer, responses={200: DetailSerializer})
class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'password_reset_confirm'

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        user.set_password(serializer.validated_data['new_password'])
        user.email_verified = True  # the reset link only ever went to this address
        user.save(update_fields=['password', 'email_verified', 'updated_at'])
        revoke_all_sessions(user)
        return Response({'detail': 'Password updated. Please sign in.'})


@extend_schema(request=PasswordChangeSerializer, responses={200: DetailSerializer})
class PasswordChangeView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'password_change'

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password', 'updated_at'])
        revoke_all_sessions(user)  # includes this device's refresh token: the client must sign in again
        return Response({'detail': 'Password changed. Please sign in again.'})


@extend_schema(request=None, responses={202: DetailSerializer})
class EmailVerifyRequestView(APIView):
    """(Re)send the verification e-mail for the signed-in user's current address."""
    permission_classes = (IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'email_verify'

    def post(self, request):
        if not request.user.email_verified:
            queue_verification_email(request.user)
        return Response({'detail': 'If your e-mail is not yet verified, a link is on its way.'}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=EmailVerifyConfirmSerializer, responses={200: DetailSerializer})
class EmailVerifyConfirmView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'email_verify_confirm'

    def post(self, request):
        serializer = EmailVerifyConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_from_verify_token(serializer.validated_data['token'])
        if user is None or not user.is_active:
            return Response({'token': 'This confirmation link is invalid or has expired. Request a new one from your account.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=['email_verified', 'updated_at'])
        return Response({'detail': 'E-mail confirmed.'})
