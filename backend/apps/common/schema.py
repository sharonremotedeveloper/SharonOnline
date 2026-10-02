"""Typed response shapes for the OpenAPI schema (Task 8.8). These document the live contract the frontend types are generated from."""
from rest_framework import serializers


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class CreditBundleRowSerializer(serializers.Serializer):
    pack_name = serializers.CharField()
    remaining = serializers.IntegerField()
    total = serializers.IntegerField()
    purchased_at = serializers.DateTimeField()


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
