from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from datetime import timedelta
from decimal import Decimal

from apps.users.permissions import IsPlatformAdmin
from apps.teachers.models import TeacherProfile
from apps.bookings.models import Booking
from apps.bookings.services.state_machine import InvalidTransition, transition_booking
from apps.payments.models import BookingFunding, CreditBundle, CreditWalletEntry, LedgerEntry, PaymentTransaction
from apps.payments.services.credits import grant_credit
from apps.payments.services.settlement import is_settled, successful_transaction
from apps.payments.services.funding import funding_for_settlement
from apps.payments.services.pricing import usd_to_zar_rate
from apps.common.money import money_str
from apps.admin_api.models import DisputeCase
from apps.users.models import User
from apps.admin_api.serializers import (
    AdminTelemetrySerializer,
    PendingTeacherApplicationSerializer,
    VerifyTeacherActionSerializer,
    LiveSessionRadarSerializer,
    DisputeCaseSerializer,
    ResolveDisputeSerializer,
    FinanceEscrowItemSerializer,
    PayoutBatchItemSerializer,
)

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class AdminTelemetryView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        gmv_today = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.SUCCESS,
            currency='USD',
            created_at__gte=today_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        gmv_month = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.SUCCESS,
            currency='USD',
            created_at__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        gmv_today = money_str(gmv_today, 'USD')
        gmv_month = money_str(gmv_month, 'USD')

        # Active Zoom sessions (within +/- 30 minutes of now)
        active_zoom = Booking.objects.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS],
            start_time_utc__lte=now + timedelta(minutes=15),
            end_time_utc__gte=now - timedelta(minutes=30)
        ).count()

        open_disputes = DisputeCase.objects.filter(status=DisputeCase.Status.OPEN).count()
        pending_vetting = TeacherProfile.objects.filter(is_verified=False).count()

        # Escrow liabilities: live from LedgerEntry
        from apps.payments.models import LedgerEntry, LedgerAccount
        ledger_escrow = LedgerEntry.objects.filter(
            account=LedgerAccount.LIABILITY_STUDENT_ESCROW
        ).aggregate(
            cr=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.CREDIT)),
            dr=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.DEBIT))
        )
        cr_zar = ledger_escrow['cr'] or Decimal('0.00')
        dr_zar = ledger_escrow['dr'] or Decimal('0.00')
        actual_escrow_zar = max(cr_zar - dr_zar, Decimal('0.00'))
        if actual_escrow_zar > 0:
            escrow_zar = money_str(actual_escrow_zar, 'ZAR')
            escrow_usd = money_str(actual_escrow_zar / usd_to_zar_rate(), 'USD')
        else:
            escrow_usd = money_str(0, 'USD')
            escrow_zar = money_str(0, 'ZAR')

        total_students = User.objects.filter(role=User.Role.STUDENT).count()
        total_teachers = TeacherProfile.objects.count()

        data = {
            'gmv_today_usd': gmv_today,
            'gmv_month_usd': gmv_month,
            'active_zoom_sessions_count': active_zoom,
            'open_disputes_count': open_disputes,
            'pending_vetting_count': pending_vetting,
            'escrow_liability_usd': escrow_usd,
            'escrow_liability_zar': escrow_zar,
            'total_students_count': total_students,
            'total_teachers_count': total_teachers,
        }
        return Response(data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class PendingTeachersListView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        unverified = TeacherProfile.objects.filter(is_verified=False).select_related('user')
        serializer = PendingTeacherApplicationSerializer(unverified, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class VerifyTeacherView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, pk):
        serializer = VerifyTeacherActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_verified = serializer.validated_data['is_verified']
        rejection_reason = serializer.validated_data.get('rejection_reason', '')

        try:
            profile = TeacherProfile.objects.get(pk=pk)
            profile.is_verified = is_verified
            if not is_verified:
                profile.is_active = False
            profile.save()

            return Response({
                'success': True,
                'teacher_id': str(profile.id),
                'is_verified': profile.is_verified,
                'message': "Tutor audition approved and published live." if is_verified else "Application rejected with feedback."
            })
        except TeacherProfile.DoesNotExist:
            return Response({'error': 'Teacher profile not found'}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class LiveSessionsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        now = timezone.now()
        # In-progress, confirmed, or completed today
        recent_bookings = Booking.objects.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED]
        ).select_related('teacher', 'teacher__user', 'student', 'material')[:10]

        serializer = LiveSessionRadarSerializer(recent_bookings, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class DisputesListView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        disputes = DisputeCase.objects.all().select_related('booking', 'student', 'teacher', 'teacher__user')
        serializer = DisputeCaseSerializer(disputes, many=True)
        return Response(serializer.data)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class ResolveDisputeView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        serializer = ResolveDisputeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resolution = serializer.validated_data['resolution']
        admin_notes = serializer.validated_data.get('admin_notes', '')

        with transaction.atomic():
            # Row-locked so two admins (or a double click) cannot both settle the same dispute.
            dispute = (DisputeCase.objects.select_for_update(of=('self',))
                       .select_related('booking', 'student', 'teacher', 'teacher__user').filter(pk=pk).first())
            if dispute is None:
                return Response({'error': 'Dispute case not found'}, status=status.HTTP_404_NOT_FOUND)
            if dispute.status != DisputeCase.Status.OPEN:
                return Response({'error': 'This dispute has already been resolved.'}, status=status.HTTP_409_CONFLICT)

            booking = dispute.booking
            if booking.status != Booking.Status.DISPUTED:
                return Response({'error': f"Booking is '{booking.status}', not awaiting arbitration."},
                                status=status.HTTP_409_CONFLICT)
            funding = funding_for_settlement(booking, context='admin_dispute_resolution')
            if funding is None:
                return Response({'error': 'Settlement stopped: booking funding provenance is missing.'},
                                status=status.HTTP_409_CONFLICT)

            # A grace booking's money is not in escrow: a payment that is still pending cannot be released at all, and one
            # that failed can only be settled by the platform paying the tutor (release) - never a split or student credit.
            if funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING and \
                    resolution != DisputeCase.Resolution.FULL_REFUND_STUDENT:
                return Response({'error': 'This lesson\'s PayPal payment has not cleared yet, so no money can be released. '
                                          'Wait for it to clear or fail.', 'code': 'payment_not_cleared'},
                                status=status.HTTP_409_CONFLICT)
            if funding.source_type == BookingFunding.SourceType.PLATFORM_ABSORBED and \
                    resolution == DisputeCase.Resolution.SPLIT_50_50:
                return Response({'error': 'The student never paid for this lesson, so there is nothing to split or credit.',
                                 'code': 'payment_not_collected'}, status=status.HTTP_409_CONFLICT)

            # A lesson whose money already left escrow (e.g. a tutor no-show that was refunded, then disputed when the tutor's
            # late Zoom event arrived) cannot also be paid out to the tutor: the student is already whole.
            if resolution != DisputeCase.Resolution.FULL_REFUND_STUDENT and is_settled(booking):
                return Response({'error': 'The money for this lesson was already refunded or settled, so it cannot be released to the tutor '
                                          'from here. Resolve it as a full refund (no further money moves) or take it to finance.',
                                 'code': 'already_settled'}, status=status.HTTP_409_CONFLICT)

            target = (Booking.Status.CANCELLED if resolution == DisputeCase.Resolution.FULL_REFUND_STUDENT
                      else Booking.Status.COMPLETED)
            try:
                transition_booking(booking, target, actor=request.user, reason=f'dispute resolved: {resolution}')
            except InvalidTransition as exc:
                return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)

            dispute.status = DisputeCase.Status.RESOLVED
            dispute.resolution = resolution
            dispute.admin_notes = admin_notes
            dispute.resolved_at = timezone.now()
            dispute.save()

            # Financial settlement execution + immutable GAAP/SARB double-entry ledger entries
            from apps.payments.models import RefundRequest
            from apps.payments.services.ledger_service import record_dispute_settlement_entry
            from apps.payments.services.refunds import AlreadySettled, request_refund
            paid_tx = successful_transaction(booking)
            if resolution == DisputeCase.Resolution.FULL_REFUND_STUDENT:
                # D-6: the student's money goes back through the gateway (they may convert it to wallet credit).
                try:
                    request_refund(booking, RefundRequest.Reason.DISPUTE, event_type=LedgerEntry.EventType.DISPUTE_RESOLVED,
                                   dispute_case=dispute, description=f"Dispute {dispute.id} decided for the student")
                except AlreadySettled:
                    pass        # the student was already refunded by the earlier outcome; nothing more to pay
            else:
                if resolution == DisputeCase.Resolution.SPLIT_50_50:
                    # Platform absorbs cost: student receives 1 courtesy credit AND tutor receives the cleared payout
                    grant_credit(dispute.student, source=CreditBundle.Source.BONUS, pack_name='Dispute Settlement Credit',
                                 unit_amount=funding.captured_amount, currency=funding.currency,
                                 fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source,
                                 booking=booking, idempotency_key=f'dispute-split:{dispute.id}')
                if funding.source_type == BookingFunding.SourceType.PLATFORM_ABSORBED:
                    # release_tutor on a lesson whose payment failed: the platform funds the tutor (ledger 5040 -> 2020)
                    from apps.payments.services.ledger_service import record_absorbed_tutor_payment_entry
                    record_absorbed_tutor_payment_entry(
                        booking, funding, event_type=LedgerEntry.EventType.DISPUTE_RESOLVED, dispute_case=dispute)
                else:
                    record_dispute_settlement_entry(dispute_case=dispute, resolution=resolution, payment_transaction=paid_tx)

            if resolution != DisputeCase.Resolution.FULL_REFUND_STUDENT:
                # The tutor was just paid by this decision: mark the escrow cleared so the 24h job can never pay again.
                paid = successful_transaction(booking)
                if paid:
                    paid.escrow_cleared = True
                    paid.save(update_fields=['escrow_cleared', 'updated_at'])
                booking.escrow_cleared_at = timezone.now()
                booking.save(update_fields=['escrow_cleared_at', 'updated_at'])

        return Response({
            'success': True,
            'dispute_id': str(dispute.id),
            'resolution': resolution,
            'message': f"Dispute resolved with action: {resolution}. Ledger updated atomically."
        })


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class EscrowLedgerView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        from apps.payments.services.ledger_service import get_ledger_telemetry
        from apps.payments.models import LedgerEntry

        telemetry = get_ledger_telemetry()
        now = timezone.now()
        bookings = Booking.objects.filter(
            status__in=[
                Booking.Status.CONFIRMED,
                Booking.Status.IN_PROGRESS,
                Booking.Status.COMPLETED,
                Booking.Status.COMPLETED_PENDING_MEMO,
                Booking.Status.COMPLETED_MEMO_FORFEITED,
                Booking.Status.DISPUTED,
                Booking.Status.STUDENT_NO_SHOW,
                Booking.Status.TEACHER_NO_SHOW,
                Booking.Status.INTERRUPTED_POWER,
                Booking.Status.CANCELLED_BY_STUDENT,       # refunded
                Booking.Status.STUDENT_LATE_CANCELLED,     # fee kept, released to the tutor at +24h
                Booking.Status.CANCELLED_BY_TEACHER,       # refunded
            ]
        ).select_related('teacher', 'teacher__user', 'student', 'funding')[:30]

        items = []
        for b in bookings:
            release_time = b.start_time_utc + timedelta(hours=24)
            is_holding = (now < release_time) and (b.escrow_cleared_at is None)
            funding = getattr(b, 'funding', None)
            if funding is None:
                funding_for_settlement(b, context='admin_escrow_view')
                continue
            gross_zar = Decimal(funding.captured_amount) * Decimal(funding.fx_rate_to_zar)
            gross_usd = gross_zar / usd_to_zar_rate()
            platform_fee = gross_usd * Decimal('0.20')
            net_tutor_zar = gross_zar * Decimal('0.80')

            has_cleared_entry = LedgerEntry.objects.filter(
                booking=b,
                event_type=LedgerEntry.EventType.ESCROW_CLEARED
            ).exists()
            has_refund_entry = LedgerEntry.objects.filter(
                booking=b,
                event_type__in=[
                    LedgerEntry.EventType.REFUND_ISSUED,
                    LedgerEntry.EventType.OUTAGE_REFUND,
                ]
            ).exists() or (b.status == Booking.Status.CANCELLED and LedgerEntry.objects.filter(
                booking=b, event_type=LedgerEntry.EventType.DISPUTE_RESOLVED).exists())
            # An arbitration that paid the tutor (release / split) counts as cleared.
            has_cleared_entry_by_dispute = (not has_refund_entry) and LedgerEntry.objects.filter(
                booking=b, event_type=LedgerEntry.EventType.DISPUTE_RESOLVED).exists()

            if has_refund_entry:
                escrow_status = 'refunded'
            elif has_cleared_entry or has_cleared_entry_by_dispute or b.escrow_cleared_at is not None:
                escrow_status = 'cleared'
            elif is_holding:
                escrow_status = 'holding'
            else:
                escrow_status = 'holding'

            items.append({
                'id': f"esc-{str(b.id)[:8]}",
                'booking_ref': f"BK-{str(b.id)[:6].upper()}",
                'student_name': b.student.get_full_name() or b.student.username,
                'teacher_name': b.teacher.user.get_full_name() or b.teacher.user.username,
                'lesson_date': b.start_time_utc.strftime('%Y-%m-%d %H:%M'),
                'amount_usd': money_str(gross_usd, 'USD'),
                'amount_zar': money_str(gross_zar, 'ZAR'),
                'platform_fee_usd': money_str(platform_fee, 'USD'),
                'teacher_net_zar': money_str(net_tutor_zar, 'ZAR'),
                'escrow_status': escrow_status,
                'payment_pending': funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING,
                'release_date': release_time.strftime('%Y-%m-%d %H:%M')
            })

        if request.query_params.get('view') == 'items' or request.query_params.get('mode') == 'items':
            return Response(items)

        return Response({
            'live_balances': telemetry['live_balances'],
            'summary': telemetry['summary'],
            'trial_balance': telemetry['trial_balance'],
            'items': items,
        })


@extend_schema(responses=PayoutBatchItemSerializer(many=True))
class PayoutBatchView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        from apps.payments.models import LedgerAccount, LedgerEntry
        from apps.payments.serializers import masked_payout_account
        from apps.payments.services.payout_crypto import PayoutDataError

        items = []
        teachers = TeacherProfile.objects.filter(
            is_verified=True, user__payout_account__isnull=False,
        ).select_related('user', 'user__payout_account')
        for t in teachers:
            totals = LedgerEntry.objects.filter(
                user=t.user, account=LedgerAccount.LIABILITY_TUTOR_PAYABLE
            ).aggregate(
                credits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.CREDIT)),
                debits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.DEBIT)),
                lessons=Count('booking', distinct=True, filter=Q(event_type__in=[
                    LedgerEntry.EventType.ESCROW_CLEARED, LedgerEntry.EventType.PAYMENT_FAILURE_ABSORBED])),
            )
            payable = (totals['credits'] or Decimal('0.00')) - (totals['debits'] or Decimal('0.00'))
            if payable <= 0:
                continue
            try:
                payout = masked_payout_account(t.user.payout_account)
            except (PayoutDataError, ImproperlyConfigured):
                continue
            items.append({
                'id': f"pay-{t.id}",
                'teacher_id': str(t.id),
                'teacher_name': t.user.get_full_name() or t.user.username,
                'bank_name': payout['bank_name'],
                'account_number_masked': payout['account_number_masked'],
                'branch_code': payout['branch_code'],
                'cleared_lessons_count': totals['lessons'] or 0,
                'payout_amount_zar': money_str(payable, 'ZAR'),
                'status': 'pending'
            })

        return Response(items)


class ExecutePayoutBatchView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={503: OpenApiTypes.OBJECT})
    def post(self, request):
        return Response({
            'success': False,
            'code': 'payout_execution_disabled',
            'message': 'Payout execution is disabled until an approved banking rail and maker-checker workflow exist.'
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

