from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.notifications import registry
from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True, allow_null=True)
    email_last_error = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ('id', 'kind', 'title', 'body', 'payload', 'booking_id', 'created_at', 'read_at', 'email_state',
                  'email_last_error')
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True, help_text='Staff only: null for everyone else.'))
    def get_email_last_error(self, obj):
        return obj.email_last_error if self.context['request'].user.is_staff else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context['request'].user.is_staff:
            data.pop('email_last_error', None)
        return data


class UnreadCountSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)


class ReadAllResponseSerializer(serializers.Serializer):
    updated = serializers.IntegerField(min_value=0)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    email_by_kind = serializers.DictField(child=serializers.BooleanField(), required=False)
    in_app_by_kind = serializers.DictField(child=serializers.BooleanField(), required=False)

    class Meta:
        model = NotificationPreference
        fields = ('email_by_kind', 'in_app_by_kind', 'updated_at')
        read_only_fields = ('updated_at',)

    def validate(self, attrs):
        for field in ('email_by_kind', 'in_app_by_kind'):
            for kind_name, enabled in attrs.get(field, {}).items():
                try:
                    kind = registry.get(kind_name)
                except registry.UnknownKind:
                    raise serializers.ValidationError({field: {kind_name: 'Unknown notification kind.'}}) from None
                if kind.mandatory and enabled is False:
                    raise serializers.ValidationError({field: {kind_name: 'This notification is mandatory.'}})
        return attrs


class ResendWebhookResponseSerializer(serializers.Serializer):
    received = serializers.BooleanField()
    action = serializers.CharField()

