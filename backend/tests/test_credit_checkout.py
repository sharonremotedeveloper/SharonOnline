from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import AttendanceAudit, Booking
from apps.bookings.services.lock_service import acquire_slot_lock, build_slot_lock_key
from apps.payments.models import (
    BookingFunding,
    CreditBundle,
    CreditPack,
    CreditPurchase,
    CreditWalletEntry,
    LedgerEntry,
    PaymentTransaction,
    SettlementAnomaly,
)
from apps.payments.services.credits import capture_credit_purchase
from apps.payments.tasks import release_cleared_escrow_task


@pytest.fixture(autouse=True)
def catalog(db):
    rows = [
        ('bundle_1', 'Single Lesson', 1, '8.00', '150.00', '7.50', '1200.00'),
        ('bundle_5', 'Starter Pack', 5, '38.00', '700.00', '35.50', '5700.00'),
        ('bundle_10', 'Fluency Builder', 10, '72.00', '1300.00', '67.00', '10800.00'),
        ('bundle_20', 'Mastery Intensive', 20, '136.00', '2400.00', '127.00', '20400.00'),
    ]
    for order, (code, name, credits, usd, zar, eur, jpy) in enumerate(rows):
        CreditPack.objects.update_or_create(code=code, defaults={
            'name': name, 'credits': credits, 'price_usd': Decimal(usd), 'price_zar': Decimal(zar),
            'price_eur': Decimal(eur), 'price_jpy': Decimal(jpy), 'display_order': order, 'is_active': True,
        })


def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def held_booking(teacher, student, *, age_minutes=0):
    start = timezone.now() + timedelta(days=2)
    token = f'token-{start.timestamp()}'
    booking = Booking.objects.create(
        teacher=teacher, student=student, start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT,
        slot_lock_token=token,
    )
    if age_minutes:
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(minutes=age_minutes))
        booking.refresh_from_db()
    acquire_slot_lock(str(teacher.id), start.isoformat(), str(student.id), token=token)
    return booking


def purchased_bundle(user, *, pack_code='bundle_5'):
    pack = CreditPack.objects.get(code=pack_code)
    purchase = CreditPurchase.objects.create(
        user=user, pack=pack, amount=pack.price_usd, currency='USD',
        fx_rate_to_zar=pack.price_zar / pack.price_usd, fx_source='credit_catalog')
    tx = PaymentTransaction.objects.create(
        credit_purchase=purchase, gateway='paypal', gateway_reference=f'CAP-{purchase.id}',
        amount=purchase.amount, currency=purchase.currency)
    return capture_credit_purchase(purchase, tx)


@pytest.mark.django_db
class TestCreditCatalogAndCheckout:
    def test_launch_catalog_is_seeded_and_public(self):
        response = APIClient().get('/api/v1/payments/credit-packs/')
        assert response.status_code == 200
        assert [(row['code'], row['credits']) for row in response.json()] == [
            ('bundle_1', 1), ('bundle_5', 5), ('bundle_10', 10), ('bundle_20', 20)]
        assert response.json()[1]['prices'] == {'USD': '38.00', 'ZAR': '700.00', 'EUR': '35.50', 'JPY': '5700.00'}

    def test_checkout_requires_exactly_one_target(self, student_user, teacher_user):
        booking = held_booking(teacher_user, student_user)
        pack = CreditPack.objects.get(code='bundle_5')
        api = client(student_user)
        assert api.post('/api/v1/payments/checkout/init/', {'gateway': 'paypal'}, format='json').status_code == 400
        both = api.post('/api/v1/payments/checkout/init/', {
            'booking_id': str(booking.id), 'credit_pack_id': pack.id, 'gateway': 'paypal'}, format='json')
        assert both.status_code == 400

    def test_pack_checkout_uses_catalog_amount_not_client_amount(self, student_user):
        pack = CreditPack.objects.get(code='bundle_10')
        response = client(student_user).post('/api/v1/payments/checkout/init/', {
            'credit_pack_id': pack.id, 'gateway': 'paypal', 'currency': 'EUR', 'amount': '0.01'}, format='json')
        assert response.status_code == 200, response.data
        purchase = CreditPurchase.objects.get(pk=response.data['target_id'])
        tx = PaymentTransaction.objects.get(credit_purchase=purchase)
        assert (purchase.amount, purchase.currency, tx.amount) == (Decimal('67.00'), 'EUR', Decimal('67.00'))

    def test_purchase_capture_is_idempotent_and_status_is_owner_scoped(self, student_user, admin_user):
        bundle = purchased_bundle(student_user)
        purchase = bundle.credit_purchase
        tx = PaymentTransaction.objects.get(credit_purchase=purchase)
        assert capture_credit_purchase(purchase, tx).pk == bundle.pk
        assert CreditBundle.objects.filter(credit_purchase=purchase).count() == 1
        assert CreditWalletEntry.objects.filter(credit_purchase=purchase, entry_type='purchase').count() == 1
        assert LedgerEntry.objects.filter(payment_transaction=tx).count() == 2
        assert client(student_user).get(f'/api/v1/payments/credit-purchases/{purchase.id}/').status_code == 200
        assert client(admin_user).get(f'/api/v1/payments/credit-purchases/{purchase.id}/').status_code == 404


@pytest.mark.django_db(transaction=True)
class TestCreditRedemption:
    def test_oldest_credit_is_consumed_and_discount_value_funds_booking(
        self, student_user, teacher_user, django_capture_on_commit_callbacks
    ):
        bundle = purchased_bundle(student_user, pack_code='bundle_5')
        booking = held_booking(teacher_user, student_user)
        with django_capture_on_commit_callbacks(execute=True):
            response = client(student_user).post(f'/api/v1/bookings/{booking.id}/redeem-credit/')
        assert response.status_code == 200, response.data
        booking.refresh_from_db(); bundle.refresh_from_db()
        funding = BookingFunding.objects.get(booking=booking)
        assert booking.status == Booking.Status.CONFIRMED
        assert bundle.remaining_credits == 4
        assert (funding.source_type, funding.captured_amount, funding.currency) == ('credit', Decimal('7.60'), 'USD')
        assert funding.credit_wallet_entry.credit_delta == -1
        assert not cache.get(build_slot_lock_key(str(teacher_user.id), booking.start_time_utc.isoformat()))
        assert LedgerEntry.objects.filter(booking=booking, event_type='credit_redeemed').count() == 2

    def test_retry_is_idempotent_and_insufficient_balance_is_rejected(
        self, student_user, teacher_user, django_capture_on_commit_callbacks
    ):
        purchased_bundle(student_user, pack_code='bundle_1')
        first = held_booking(teacher_user, student_user)
        with django_capture_on_commit_callbacks(execute=True):
            assert client(student_user).post(f'/api/v1/bookings/{first.id}/redeem-credit/').status_code == 200
        assert client(student_user).post(f'/api/v1/bookings/{first.id}/redeem-credit/').status_code == 200
        second = held_booking(teacher_user, student_user)
        assert client(student_user).post(f'/api/v1/bookings/{second.id}/redeem-credit/').status_code == 409
        assert CreditWalletEntry.objects.filter(entry_type='redemption').count() == 1

    def test_expired_hold_does_not_consume_credit(self, student_user, teacher_user):
        bundle = purchased_bundle(student_user, pack_code='bundle_1')
        booking = held_booking(teacher_user, student_user, age_minutes=11)
        response = client(student_user).post(f'/api/v1/bookings/{booking.id}/redeem-credit/')
        bundle.refresh_from_db(); booking.refresh_from_db()
        assert response.status_code == 409
        assert bundle.remaining_credits == 1 and booking.status == Booking.Status.PENDING_PAYMENT
        assert not BookingFunding.objects.filter(booking=booking).exists()


@pytest.mark.django_db
def test_payment_transaction_database_constraint_requires_one_target(student_user, teacher_user):
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentTransaction.objects.create(
            gateway='paypal', gateway_reference='NO-TARGET', amount=Decimal('1.00'), currency='USD')


@pytest.mark.django_db
def test_settlement_without_funding_stops_and_records_anomaly(teacher_user, student_user):
    end = timezone.now() - timedelta(hours=25)
    booking = Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=end - timedelta(minutes=25),
        end_time_utc=end, status=Booking.Status.COMPLETED)
    AttendanceAudit.objects.create(
        booking=booking, participant_email=teacher_user.user.email, total_minutes=25)
    result = release_cleared_escrow_task()
    assert result['cleared_count'] == 0
    assert SettlementAnomaly.objects.filter(booking=booking, code='missing_booking_funding').count() == 1
    assert not LedgerEntry.objects.filter(booking=booking).exists()
