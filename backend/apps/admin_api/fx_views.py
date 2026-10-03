"""Admin screen API for the EUR/JPY FX rate table (Task 10.1d)."""
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.models import FxRate
from apps.payments.services.fx import FxRateSanityError, latest_row, max_age, record_rate
from apps.users.permissions import IsPlatformAdmin


def _row(row, now):
    age = now - row.valid_from
    return {
        'id': row.pk, 'currency': row.currency, 'rate_to_zar': str(row.rate_to_zar), 'source': row.source,
        'valid_from': row.valid_from.isoformat(), 'set_by': row.set_by.username if row.set_by_id else None,
        'age_hours': round(age.total_seconds() / 3600, 1), 'stale': age > max_age(),
    }


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class FxRateView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        now = timezone.now()
        current = []
        for currency in FxRate.SUPPORTED:
            row = latest_row(currency, now)
            current.append(_row(row, now) if row else {'currency': currency, 'rate_to_zar': None, 'stale': True,
                                                      'source': None, 'valid_from': None, 'age_hours': None,
                                                      'id': None, 'set_by': None})
        history = [_row(r, now) for r in FxRate.objects.select_related('set_by')[:20]]
        return Response({'max_age_hours': max_age().total_seconds() / 3600, 'current': current, 'history': history})

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response({'error': 'JSON object expected.'}, status=status.HTTP_400_BAD_REQUEST)
        currency = str(request.data.get('currency', '')).upper()
        try:
            rate = Decimal(str(request.data.get('rate')))
        except InvalidOperation:
            return Response({'error': 'rate must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        confirm = request.data.get('confirm') is True
        try:
            row = record_rate(currency, rate, set_by=request.user, confirm=confirm)
        except FxRateSanityError as exc:
            return Response({'error': str(exc), 'code': 'confirmation_required'}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_row(row, timezone.now()), status=status.HTTP_201_CREATED)
