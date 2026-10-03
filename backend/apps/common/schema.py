"""Typed response shapes for the OpenAPI schema (Task 8.8). These document the live contract the frontend types are generated from."""
from rest_framework import serializers


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class CreditBundleRowSerializer(serializers.Serializer):
    pack_name = serializers.CharField()
    remaining = serializers.IntegerField()
    total = serializers.IntegerField()
    purchased_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)


class CreditLedgerEntrySerializer(serializers.Serializer):
    id = serializers.CharField()
    description = serializers.CharField()
    credits_delta = serializers.IntegerField()
    date = serializers.DateField()
    type = serializers.ChoiceField(choices=['purchase', 'redemption', 'refund', 'bonus'])


class WalletSerializer(serializers.Serializer):
    total_credits = serializers.IntegerField()
    ledger = CreditLedgerEntrySerializer(many=True)
    bundles = CreditBundleRowSerializer(many=True)


class CancelRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000, default='')
    acknowledge_forfeit = serializers.BooleanField(required=False, default=False)


class CancelResultSerializer(serializers.Serializer):
    outcome = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()


class CancelPreviewSerializer(serializers.Serializer):
    can_cancel = serializers.BooleanField()
    outcome = serializers.CharField()
    message = serializers.CharField()
    seconds_until_start = serializers.IntegerField()
    refund_amount = serializers.CharField(allow_null=True)
    refund_currency = serializers.CharField(allow_null=True)
    bonus_credits = serializers.IntegerField()
    strike = serializers.BooleanField()
    free_cancel_until = serializers.DateTimeField(required=False)


class RescheduleRequestSerializer(serializers.Serializer):
    start_time_utc = serializers.DateTimeField()


class ErrorCodeSerializer(serializers.Serializer):
    error = serializers.CharField()
    code = serializers.CharField()


class ReviewResultSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    status = serializers.CharField()
    message = serializers.CharField()


class ReserveRequestSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    start_time_utc = serializers.DateTimeField()


class ReservationSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    status = serializers.CharField()
    teacher_id = serializers.UUIDField()
    start_time_utc = serializers.DateTimeField()
    end_time_utc = serializers.DateTimeField()
    lock_ttl_seconds = serializers.IntegerField()
    lock_expires_at = serializers.DateTimeField()
    message = serializers.CharField()
