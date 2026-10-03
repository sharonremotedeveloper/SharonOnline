from rest_framework import serializers


class EskomOutageSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    note = serializers.CharField(allow_blank=True)


class EskomStatusSerializer(serializers.Serializer):
    area_id = serializers.CharField()
    area_name = serializers.CharField()
    stage = serializers.IntegerField(min_value=0, max_value=8)
    outages = EskomOutageSerializer(many=True)
    next_outage_start = serializers.DateTimeField(allow_null=True)
    next_outage_end = serializers.DateTimeField(allow_null=True)
    has_inverter_backup = serializers.BooleanField()
    has_lte_failover = serializers.BooleanField()
    stale = serializers.BooleanField()
    provider_status = serializers.CharField()
    retrieved_at = serializers.DateTimeField()

