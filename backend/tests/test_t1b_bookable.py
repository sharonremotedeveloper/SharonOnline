"""
Slice T1b: the single bookable predicate (plan §3.1) and its call sites, decided per site.

    bookable = approved (is_verified and is_active) and training_ok
    training_ok = TUTOR_TRAINING_GATE_ENABLED is off, or training_completed_at is set

New bookings (public list/detail, slots, reserve, reschedule target, checkout, credit redemption, payment confirmation) need a
bookable tutor. Money a tutor already earned (payout preview) and operations on existing lessons never consult it.
"""
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.admin_api.models import DisputeCase
from apps.bookings.models import Booking
from apps.payments.models import LedgerAccount, LedgerEntry, PaymentTransaction
from apps.payments.services.webhook_handler import process_payment_webhook, slot_unavailable_reason
from apps.teachers.models import TeacherAvailability, TeacherProfile
from payment_helpers import lesson

pytestmark = pytest.mark.django_db
S = Booking.Status
NOT_BOOKABLE = ['applied', 'submitted', 'in_review', 'changes_requested', 'rejected', 'suspended']


def api(user=None):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def every_day(tutor):
    TeacherAvailability.objects.filter(teacher=tutor).delete()
    for dow in range(7):
        TeacherAvailability.objects.create(teacher=tutor, day_of_week=dow, start_time=time(0, 0), end_time=time(23, 30))
    return tutor


# ------------------------------------------------------------------ the predicate
class TestPredicate:
    def test_only_approved_is_bookable_with_the_gate_off(self, settings):
        settings.TUTOR_TRAINING_GATE_ENABLED = False
        tutors = {s: f.make_teacher_profile(status=s, availability=False) for s in ['approved', *NOT_BOOKABLE]}
        assert set(TeacherProfile.objects.bookable()) == {tutors['approved']}
        assert {s for s, t in tutors.items() if t.is_bookable} == {'approved'}

    def test_the_gate_needs_training_when_on(self, settings):
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        untrained = f.make_teacher_profile(status='approved', availability=False)
        trained = f.make_teacher_profile(status='approved', availability=False, training_completed_at=timezone.now())
        suspended_trained = f.make_teacher_profile(status='suspended', availability=False, training_completed_at=timezone.now())
        assert set(TeacherProfile.objects.bookable()) == {trained}
        assert (untrained.is_bookable, trained.is_bookable, suspended_trained.is_bookable) == (False, True, False)

    def test_the_gate_is_off_by_default_and_provisional(self):
        from django.conf import settings as live
        assert live.TUTOR_TRAINING_GATE_ENABLED is False

    def test_bookable_is_chainable(self):
        tutor = f.make_teacher_profile(status='approved', availability=False)
        assert TeacherProfile.objects.filter(pk=tutor.pk).bookable().get() == tutor
        assert TeacherProfile.objects.bookable().filter(pk=tutor.pk).exists()


# ------------------------------------------------------------------ public list / detail / slots
class TestPublicSurfaces:
    @pytest.mark.parametrize('status', NOT_BOOKABLE)
    def test_list_detail_and_slots_hide_unbookable_tutors(self, status):
        tutor = f.make_teacher_profile(status=status)
        listed = api().get('/api/v1/teachers/').json()
        rows = listed['results'] if isinstance(listed, dict) else listed
        assert str(tutor.id) not in {r['id'] for r in rows}
        assert api().get(f'/api/v1/teachers/{tutor.id}/').status_code == 404
        assert api().get(f'/api/v1/bookings/slots/{tutor.id}/').status_code == 404

    def test_an_untrained_tutor_is_hidden_once_the_gate_is_on(self, settings):
        tutor = f.make_teacher_profile(status='approved')
        assert api().get(f'/api/v1/teachers/{tutor.id}/').status_code == 200
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        assert api().get(f'/api/v1/teachers/{tutor.id}/').status_code == 404
        assert api().get(f'/api/v1/bookings/slots/{tutor.id}/').status_code == 404
        listed = api().get('/api/v1/teachers/').json()
        assert str(tutor.id) not in {r['id'] for r in (listed['results'] if isinstance(listed, dict) else listed)}


# ------------------------------------------------------------------ reserve / reschedule / checkout / credit
class TestNewBookingPaths:
    def test_reserve_refuses_an_untrained_tutor_when_the_gate_is_on(self, settings):
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        tutor = every_day(f.make_teacher_profile(status='approved'))
        start = (timezone.now() + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        res = api(f.make_student()).post('/api/v1/bookings/reserve/', {'teacher_id': str(tutor.id),
                                                                        'start_time_utc': start.isoformat()}, format='json')
        assert res.status_code == 404
        assert not Booking.objects.exists()

    @pytest.mark.parametrize('status', ['suspended', 'in_review'])
    def test_reserve_refuses_unbookable_statuses(self, status):
        tutor = every_day(f.make_teacher_profile(status=status))
        start = (timezone.now() + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        res = api(f.make_student()).post('/api/v1/bookings/reserve/', {'teacher_id': str(tutor.id),
                                                                        'start_time_utc': start.isoformat()}, format='json')
        assert res.status_code == 404

    def test_reschedule_to_a_new_slot_needs_a_bookable_tutor(self, settings):
        tutor = every_day(f.make_teacher_profile(status='approved'))
        student = f.make_student()
        booking = f.make_booking(teacher=tutor, student=student, status=S.CONFIRMED, offset_hours=48, funded=True)
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        new_start = (timezone.now() + timedelta(days=4)).replace(minute=0, second=0, microsecond=0)
        res = api(student).post(f'/api/v1/bookings/{booking.id}/reschedule/', {'start_time_utc': new_start.isoformat()}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'slot_unavailable'

    def test_checkout_refuses_a_hold_whose_tutor_was_suspended(self):
        tutor = f.make_teacher_profile(status='approved')
        student = f.make_student()
        booking = f.make_booking(teacher=tutor, student=student, status=S.PENDING_PAYMENT, offset_hours=48)
        f.advance_teacher(tutor, 'suspended')
        res = api(student).post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
        assert res.status_code == 409
        assert not PaymentTransaction.objects.exists()

    def test_checkout_refuses_an_untrained_tutor_when_the_gate_is_on(self, settings):
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        tutor = f.make_teacher_profile(status='approved')
        student = f.make_student()
        booking = f.make_booking(teacher=tutor, student=student, status=S.PENDING_PAYMENT, offset_hours=48)
        res = api(student).post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
        assert res.status_code == 409

    def test_credit_redemption_refuses_a_hold_whose_tutor_was_suspended(self):
        from apps.payments.models import CreditBundle
        from apps.payments.services.credits import CreditRedemptionError, grant_credit, redeem_booking_credit
        tutor = f.make_teacher_profile(status='approved')
        student = f.make_student()
        grant_credit(student, source=CreditBundle.Source.BONUS, pack_name='t', unit_amount=Decimal('9.00'), currency='USD',
                     fx_rate_to_zar=Decimal('18.750000'), fx_source='test', idempotency_key='t1b-credit')
        booking = f.make_booking(teacher=tutor, student=student, status=S.PENDING_PAYMENT, offset_hours=48)
        f.advance_teacher(tutor, 'suspended')
        with pytest.raises(CreditRedemptionError) as exc:
            redeem_booking_credit(booking=booking, student=student)
        assert exc.value.status_code == 409
        booking.refresh_from_db()
        assert booking.status == S.PENDING_PAYMENT


# ------------------------------------------------------------------ a payment that lands after the tutor was suspended
class TestLatePaymentForAnUnbookableTutor:
    def _pay(self, booking, ref='LATE-1'):
        PaymentTransaction.objects.create(booking=booking, gateway='payfast', gateway_reference=f'INIT-{ref}', merchant_reference=ref,
                                          amount=Decimal('168.75'), currency='ZAR')
        return process_payment_webhook(booking_id=str(booking.id), gateway='payfast', transaction_id=f'GW-{ref}',
                                       amount=Decimal('168.75'), currency='ZAR', status='success', raw_payload={})

    def test_the_guard_names_the_reason(self, teacher_user, student_user):
        booking = lesson(teacher_user, student_user, 60 * 48)
        assert slot_unavailable_reason(booking) == ''
        f.advance_teacher(teacher_user, 'suspended')
        booking = Booking.objects.select_related('teacher').get(pk=booking.pk)
        assert slot_unavailable_reason(booking) == 'tutor_not_bookable'

    def test_it_is_quarantined_like_def501_never_confirmed(self, teacher_user, student_user):
        booking = lesson(teacher_user, student_user, 60 * 48)
        f.advance_teacher(teacher_user, 'suspended')
        result = self._pay(booking)
        assert result['status'] == 'collision_quarantined' and result['reason'] == 'tutor_not_bookable'
        booking.refresh_from_db()
        assert booking.status == S.DISPUTED
        assert DisputeCase.objects.filter(booking=booking, status=DisputeCase.Status.OPEN).exists()
        quarantined = LedgerEntry.objects.filter(booking=booking, account=LedgerAccount.LIABILITY_QUARANTINE_DEPOSIT)
        assert quarantined.exists()

    def test_a_retry_of_the_same_payment_is_idempotent(self, teacher_user, student_user):
        booking = lesson(teacher_user, student_user, 60 * 48)
        f.advance_teacher(teacher_user, 'suspended')
        self._pay(booking)
        count = LedgerEntry.objects.count()
        again = process_payment_webhook(booking_id=str(booking.id), gateway='payfast', transaction_id='GW-LATE-1',
                                        amount=Decimal('168.75'), currency='ZAR', status='success', raw_payload={})
        assert again == {'status': 'already_processed'} and LedgerEntry.objects.count() == count

    def test_a_bookable_tutor_still_confirms(self, teacher_user, student_user):
        booking = lesson(teacher_user, student_user, 60 * 48)
        assert self._pay(booking)['status'] == 'success'
        booking.refresh_from_db()
        assert booking.status == S.CONFIRMED

    def test_grace_is_refused_for_an_unbookable_tutor(self, teacher_user, student_user, settings):
        from apps.payments.services import grace
        booking = lesson(teacher_user, student_user, 60 * 48)
        tx = PaymentTransaction.objects.create(booking=booking, gateway='paypal', gateway_reference='CAP-GRACE', merchant_reference='G1',
                                               amount=Decimal('9.00'), currency='USD', status=PaymentTransaction.Status.PENDING_CAPTURE,
                                               pending_reason='PENDING_REVIEW', payer_id='PAYER-T1B', fx_rate_to_zar=Decimal('18.750000'), fx_source='test')
        f.advance_teacher(teacher_user, 'suspended')
        decision = grace.confirm_grace_booking(tx)
        assert decision.allowed is False and decision.reason == 'tutor_not_bookable'
        booking.refresh_from_db()
        assert booking.status == S.PENDING_PAYMENT


# ------------------------------------------------------------------ payout preview: earned money is paid whatever the status
class TestPayoutPreview:
    @pytest.fixture(autouse=True)
    def keys(self, settings):
        from cryptography.fernet import Fernet
        settings.PAYOUT_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
        settings.PAYOUT_DATA_ACTIVE_KEY = 'v1'

    @pytest.fixture(autouse=True)
    def accept_the_test_code(self, monkeypatch):
        monkeypatch.setattr('apps.payments.serializers.check_code', lambda user, code: code == '123456')

    def _payable(self, tutor, amount='100.00'):
        LedgerEntry.objects.create(
            journal_batch_id=f'5555555{str(tutor.pk)[:1]}-5555-5555-5555-555555555555',
            account=LedgerAccount.LIABILITY_TUTOR_PAYABLE, entry_type=LedgerEntry.EntryType.CREDIT,
            amount=Decimal(amount), currency='ZAR', fx_rate_to_zar=Decimal('1.000000'), fx_source='transaction_currency',
            amount_zar=Decimal(amount), event_type=LedgerEntry.EventType.ESCROW_CLEARED, description='payable', user=tutor.user)
        body = {'verification_code': '123456', 'current_password': 'password123', 'account_holder_name': 'T', 'account_number': '1234567890',
                'bank_name': 'Capitec Bank', 'branch_code': '470010', 'account_type': 'savings',
                'identification_number': '9001015009087'}
        assert api(tutor.user).post('/api/v1/payments/payout-settings/', body, format='json').status_code == 201

    @pytest.mark.parametrize('path', [('suspended',), ('suspended', 'rejected')])
    def test_suspended_and_removed_tutors_still_get_what_they_earned(self, path):
        tutor = f.make_teacher_profile(status='approved')
        self._payable(tutor)
        f.advance_teacher(tutor, *path)
        rows = api(f.make_admin()).get('/api/v1/admin/payouts/batch/').json()
        assert [r['teacher_id'] for r in rows] == [str(tutor.id)]


# ------------------------------------------------------------------ Eskom sync and Google Calendar reconcile
class TestOperationalTutors:
    def _areas(self, provider_calls):
        from apps.integrations.tasks import sync_eskom_statuses

        class Provider:
            def fetch_area_status(self, area_id):
                provider_calls.append(area_id)
                return {'area_name': area_id, 'stage': 0, 'outages': [], 'retrieved_at': timezone.now()}
        sync_eskom_statuses(Provider())
        return set(provider_calls)

    def test_eskom_includes_suspended_tutors_with_lessons_and_excludes_applicants(self):
        f.make_teacher_profile(status='approved', eskom_area_id='live')
        suspended = f.make_teacher_profile(status='suspended', eskom_area_id='suspended-with-lesson')
        f.make_booking(teacher=suspended, status=S.CONFIRMED, offset_hours=3)
        f.make_teacher_profile(status='suspended', eskom_area_id='suspended-idle')
        f.make_teacher_profile(status='applied', eskom_area_id='applicant')
        f.make_teacher_profile(status='submitted', eskom_area_id='applicant-2')
        assert self._areas([]) == {'live', 'suspended-with-lesson'}

    def test_gcal_reconcile_follows_the_same_rule(self):
        from unittest import mock

        from apps.integrations.models import CalendarCredential
        from apps.integrations.tasks import reconcile_teacher_gcal_task, sync_tutor_busy_task

        def connected(profile):
            CalendarCredential.objects.create(user=profile.user, refresh_token_enc='x')
            return profile

        approved = connected(f.make_teacher_profile(status='approved'))
        suspended = connected(f.make_teacher_profile(status='suspended'))
        f.make_booking(teacher=suspended, status=S.CONFIRMED, offset_hours=3)
        connected(f.make_teacher_profile(status='suspended'))
        connected(f.make_teacher_profile(status='applied'))
        with mock.patch.object(sync_tutor_busy_task, 'delay') as delay:
            assert reconcile_teacher_gcal_task() == {'queued_tutors': 2}
        assert {call.args[0] for call in delay.call_args_list} == {str(approved.id), str(suspended.id)}

    def test_operational_is_distinct_with_several_lessons(self):
        tutor = f.make_teacher_profile(status='suspended')
        for hours in (3, 5, 7):
            f.make_booking(teacher=tutor, status=S.CONFIRMED, offset_hours=hours)
        assert list(TeacherProfile.objects.operational()) == [tutor]


# ------------------------------------------------------------------ the admin serializer reports the real status
@pytest.mark.parametrize('status', ['applied', 'submitted', 'in_review', 'changes_requested', 'rejected', 'approved', 'suspended'])
def test_admin_application_serializer_reports_the_real_status(status):
    from apps.admin_api.serializers import PendingTeacherApplicationSerializer
    tutor = f.make_teacher_profile(status=status, availability=False)
    assert PendingTeacherApplicationSerializer(tutor).data['status'] == status


# ------------------------------------------------------------------ operations on existing lessons never consult bookable()
def test_a_student_can_still_cancel_a_lesson_with_an_untrained_tutor(settings):
    tutor = f.make_teacher_profile(status='approved')
    student = f.make_student()
    booking = f.make_booking(teacher=tutor, student=student, status=S.CONFIRMED, offset_hours=48, funded=True)
    settings.TUTOR_TRAINING_GATE_ENABLED = True
    res = api(student).post(f'/api/v1/bookings/{booking.id}/cancel/', {}, format='json')
    assert res.status_code == 200 and res.json()['outcome'] == 'full_refund'


# ------------------------------------------------------------------ production guard: the gate must be on before launch
def test_production_guard_warns_while_the_training_gate_is_off(caplog):
    from test_settings_guard import GOOD
    from config.settings.guard import validate_production_settings
    with caplog.at_level('WARNING', logger='config.settings.guard'):
        validate_production_settings(dict(GOOD))
    assert any('TUTOR_TRAINING_GATE_ENABLED' in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level('WARNING', logger='config.settings.guard'):
        validate_production_settings({**GOOD, 'TUTOR_TRAINING_GATE_ENABLED': 'true'})
    assert not any('TUTOR_TRAINING_GATE_ENABLED' in r.getMessage() for r in caplog.records)
