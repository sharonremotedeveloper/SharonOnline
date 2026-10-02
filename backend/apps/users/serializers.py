from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from .models import User

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
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
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'country', 'timezone', 'phone_number', 'created_at')
        read_only_fields = ('id', 'role', 'created_at')
        extra_kwargs = {
            'email': {'validators': [UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with this email already exists.')]},
            'username': {'validators': [UnicodeUsernameValidator(), UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with that username already exists.')]},
            'timezone': {'validators': [validate_iana_timezone]},
        }

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
            'username': {'validators': [UnicodeUsernameValidator(), UniqueValidator(queryset=User.objects.all(), lookup='iexact', message='A user with that username already exists.')]},
            'timezone': {'validators': [validate_iana_timezone]},
        }

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
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
