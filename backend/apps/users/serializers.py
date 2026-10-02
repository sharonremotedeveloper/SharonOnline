from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction
from django.db.models import Sum
from drf_spectacular.utils import extend_schema_field
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from pytz import country_names

from .models import StudentProfile, SupportInquiry, User
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


def validate_iso_country(value):
    """Accept blank or a real ISO 3166-1 alpha-2 country code and store it canonically."""
    value = value.strip().upper()
    if value and value not in country_names:
        raise serializers.ValidationError('Enter a valid ISO 3166-1 alpha-2 country code, e.g. "ZA" or "JP".')
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
        return user.credit_bundles.aggregate(total=Sum('remaining_credits'))['total'] or 0

    @extend_schema_field(serializers.CharField())
    def get_avatar_url(self, user):
        profile = getattr(user, 'teacher_profile', None) if user.role == User.Role.TEACHER else None
        return profile.resolved_avatar_url if profile else ''

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_is_verified(self, user):
        profile = getattr(user, 'teacher_profile', None) if user.role == User.Role.TEACHER else None
        return profile.is_verified if profile else None

    def validate_country(self, value):
        return validate_iso_country(value)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'email_verified', 'first_name', 'last_name', 'role', 'country', 'timezone', 'phone_number', 'created_at',
                  'credits', 'avatar_url', 'is_verified')
        read_only_fields = ('id', 'role', 'email_verified', 'created_at', 'credits', 'avatar_url', 'is_verified')
        extra_kwargs = {
            'email': {'validators': [UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with this email already exists.')]},
            'username': {'validators': [UnicodeUsernameValidator(), UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with that username already exists.')]},
            'timezone': {'validators': [validate_iana_timezone]},
            'country': {'validators': [validate_iso_country]},
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
            'country': {'validators': [validate_iso_country]},
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

    def validate_country(self, value):
        return validate_iso_country(value)

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
        if user.role == User.Role.STUDENT:
            StudentProfile.objects.create(user=user)
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


class StudentProfileSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(max_length=301)
    email = serializers.EmailField(read_only=True)
    country = serializers.CharField(max_length=2, allow_blank=True, validators=[validate_iso_country])
    timezone = serializers.CharField(max_length=64, validators=[validate_iana_timezone])
    target_level = serializers.CharField(max_length=64, allow_blank=True)
    learning_goals = serializers.CharField(max_length=2000, allow_blank=True)

    def to_representation(self, user):
        profile = getattr(user, 'student_profile', None)
        return {
            'id': str(user.id),
            'full_name': user.get_full_name() or user.username,
            'email': user.email,
            'country': user.country,
            'timezone': user.timezone,
            'target_level': profile.target_level if profile else '',
            'learning_goals': profile.learning_goals if profile else '',
        }

    def validate_full_name(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Enter your full name.')
        return value

    def validate_country(self, value):
        return validate_iso_country(value)

    def update(self, user, validated_data):
        if user.role != User.Role.STUDENT:
            raise serializers.ValidationError({'role': 'Only student accounts have a student profile.'})
        profile_data = {
            key: validated_data.pop(key)
            for key in ('target_level', 'learning_goals')
            if key in validated_data
        }
        with transaction.atomic():
            full_name = validated_data.pop('full_name', None)
            if full_name is not None:
                first_name, _, last_name = full_name.partition(' ')
                user.first_name = first_name
                user.last_name = last_name
            for field in ('country', 'timezone'):
                if field in validated_data:
                    setattr(user, field, validated_data[field])
            user.save(update_fields=['first_name', 'last_name', 'country', 'timezone', 'updated_at'])
            profile, _ = StudentProfile.objects.get_or_create(user=user)
            if profile_data:
                for field, value in profile_data.items():
                    setattr(profile, field, value)
                profile.save(update_fields=[*profile_data, 'updated_at'])
        return user


class SupportInquirySerializer(serializers.ModelSerializer):
    user_type = serializers.ChoiceField(
        source='sender_type', choices=SupportInquiry.SenderType.choices,
        required=False, default=SupportInquiry.SenderType.OTHER,
    )
    name = serializers.CharField(source='sender_name', max_length=150)
    email = serializers.EmailField(source='sender_email', max_length=254)

    class Meta:
        model = SupportInquiry
        fields = ('id', 'name', 'email', 'user_type', 'subject', 'message', 'status', 'delivery_state', 'created_at')
        read_only_fields = ('id', 'status', 'delivery_state', 'created_at')
        extra_kwargs = {
            'subject': {'max_length': 200},
            'message': {'max_length': 5000},
        }

    def validate_name(self, value):
        value = ' '.join(value.split())
        if not value:
            raise serializers.ValidationError('Enter your name.')
        return value

    def validate_subject(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a subject.')
        return value

    def validate_message(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a message.')
        return value


class SupportInquiryAcceptedSerializer(serializers.Serializer):
    detail = serializers.CharField()
    inquiry_id = serializers.UUIDField()
