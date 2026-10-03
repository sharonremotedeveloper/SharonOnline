from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db.models import Sum
from drf_spectacular.utils import extend_schema_field
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from .models import User
from .services import queue_verification_email
from .tokens import check_reset_token, user_from_uid

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Login by e-mail (Task 8.6). Resolved to the real username here so authentication, throttling and failure
        # responses are identical for both identifiers. Ambiguous/unknown e-mails fall through and fail like any bad login.
        ident = (attrs.get('username') or '').strip()
        if '@' in ident:
            matches = list(User.objects.filter(email__iexact=ident, is_active=True).values_list('username', flat=True)[:2])
            if len(matches) == 1:
                attrs['username'] = matches[0]
        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['username'] = user.username
        token['email'] = user.email
        token['timezone'] = user.timezone
        token['country'] = user.country
        return token

def validate_iana_timezone(value):
    """Reject anything that is not a real IANA zone (slot generation feeds this straight into zoneinfo)."""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise serializers.ValidationError('Enter a valid IANA timezone, e.g. "Africa/Johannesburg".')
    return value


class UserSerializer(serializers.ModelSerializer):
    # Role-specific extras the UI needs on every page (navbar, checkout). Null-ish for roles they do not apply to.
    credits = serializers.SerializerMethodField(help_text='Remaining lesson credits (students only; otherwise null).')
    avatar_url = serializers.SerializerMethodField(help_text='Tutor profile photo URL (tutors only; otherwise empty).')
    is_verified = serializers.SerializerMethodField(help_text='Vetting status (tutors only; otherwise null).')

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_credits(self, user):
        if user.role != User.Role.STUDENT:
            return None
        return user.credit_bundles.active().aggregate(total=Sum('remaining_credits'))['total'] or 0

    @extend_schema_field(serializers.CharField())
    def get_avatar_url(self, user):
        profile = getattr(user, 'teacher_profile', None) if user.role == User.Role.TEACHER else None
        return profile.resolved_avatar_url if profile else ''

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_is_verified(self, user):
        profile = getattr(user, 'teacher_profile', None) if user.role == User.Role.TEACHER else None
        return profile.is_verified if profile else None

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'email_verified', 'first_name', 'last_name', 'role', 'country', 'timezone', 'phone_number', 'created_at',
                  'credits', 'avatar_url', 'is_verified')
        read_only_fields = ('id', 'role', 'email_verified', 'created_at', 'credits', 'avatar_url', 'is_verified')
        extra_kwargs = {
            'email': {'validators': [UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with this email already exists.')]},
            'username': {'validators': [UnicodeUsernameValidator(), UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with that username already exists.')]},
            'timezone': {'validators': [validate_iana_timezone]},
        }

    def update(self, instance, validated_data):
        new_email = validated_data.get('email')
        changed = new_email is not None and new_email.lower() != instance.email.lower()
        if changed:
            validated_data['email_verified'] = False  # the new address has not proven anything yet
        user = super().update(instance, validated_data)
        if changed:
            queue_verification_email(user)
        return user


def validate_username_without_at(value):
    # '@' would make a username look like someone else's e-mail and be ambiguous now that login accepts an e-mail.
    if '@' in value:
        raise serializers.ValidationError('Usernames cannot contain "@". Sign in with your e-mail instead.')
    return value


class RegisterSerializer(serializers.ModelSerializer):
    # Validated in validate() with the user's own attributes so the similarity validator can actually fire.
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)
    # Admins are never self-service: only student/teacher can be requested at signup.
    role = serializers.ChoiceField(choices=[User.Role.STUDENT, User.Role.TEACHER], default=User.Role.STUDENT, required=False)
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with this email already exists.')],
    )

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'password_confirm', 'first_name', 'last_name', 'role', 'country', 'timezone')
        extra_kwargs = {
            'username': {'validators': [UnicodeUsernameValidator(), validate_username_without_at, UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with that username already exists.')]},
            'timezone': {'validators': [validate_iana_timezone]},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Password fields didn't match."})
        candidate = User(username=attrs.get('username', ''), email=attrs.get('email', ''),
                         first_name=attrs.get('first_name', ''), last_name=attrs.get('last_name', ''))
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', User.Role.STUDENT),
            country=validated_data.get('country', ''),
            timezone=validated_data.get('timezone', 'UTC')
        )
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class _NewPasswordMixin(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, max_length=128)
    new_password_confirm = serializers.CharField(write_only=True, max_length=128)

    def _check_new_password(self, attrs, user):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({'new_password_confirm': "Password fields didn't match."})
        try:
            validate_password(attrs['new_password'], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})


class PasswordResetConfirmSerializer(_NewPasswordMixin):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=256)

    INVALID = 'This reset link is invalid or has expired. Request a new one.'

    def validate(self, attrs):
        user = user_from_uid(attrs['uid'])
        # One message for "no such user", "wrong token" and "used/expired token": nothing to enumerate.
        if user is None or not user.is_active or not check_reset_token(user, attrs['token']):
            raise serializers.ValidationError({'token': self.INVALID})
        self._check_new_password(attrs, user)
        attrs['user'] = user
        return attrs


class PasswordChangeSerializer(_NewPasswordMixin):
    old_password = serializers.CharField(write_only=True, max_length=128)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs['old_password']):
            raise serializers.ValidationError({'old_password': 'Your current password is incorrect.'})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({'new_password': 'Choose a password you have not used just now.'})
        self._check_new_password(attrs, user)
        return attrs


class EmailVerifyConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
