from decimal import Decimal
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.bookings.models import Booking
from apps.payments.models import (
    BookingFunding, LedgerAccount, LedgerEntry, PaymentTransaction, TutorPayoutAccount,
)


WALLET = '/api/v1/payments/wallet/tutor/'
SETTINGS = '/api/v1/payments/payout-settings/'
ADMIN_PAYOUTS = '/api/v1/admin/payouts/batch/'


def client(user):
    value = APIClient()
    value.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return value


@pytest.fixture(autouse=True)
def payout_keys(settings):
    settings.PAYOUT_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
    settings.PAYOUT_DATA_ACTIVE_KEY = 'v1'


def payout_payload(**overrides):
    payload = {
        'current_password': 'password123',
        'account_holder_name': 'Test Tutor',
        'account_number': '1234567890',
        'bank_name': 'Capitec Bank',
        'branch_code': '470010',
        'account_type': 'savings',
        'identification_number': '9001015009087',
    }
    payload.update(overrides)
    return payload


def booking(teacher_user, student_user, *, status=Booking.Status.CONFIRMED, start_offset_minutes=0):
    start = timezone.now() + timedelta(minutes=start_offset_minutes)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, status=status,
        start_time_utc=start, end_time_utc=start + timedelta(minutes=25),
    )


def funding_for(booking_obj, reference):
    tx = PaymentTransaction.objects.create(
        booking=booking_obj, gateway='paypal', gateway_reference=reference,
        amount=Decimal('8.00'), currency='USD', status=PaymentTransaction.Status.SUCCESS,
        fx_rate_to_zar=Decimal('18.000000'), fx_source='capture_test',
    )
    return BookingFunding.objects.create(
        booking=booking_obj, source_type=BookingFunding.SourceType.GATEWAY,
        captured_amount=Decimal('8.00'), currency='USD', fx_rate_to_zar=Decimal('18.000000'),
        fx_source='capture_test', payment_transaction=tx,
    )


@pytest.mark.django_db
class TestPayoutSettings:
    def test_get_empty_and_save_returns_only_masked_values(self, teacher_user):
        api = client(teacher_user.user)
        assert api.get(SETTINGS).json() == {'configured': False}
        response = api.post(SETTINGS, payout_payload(), format='json')
        assert response.status_code == 201
        body = response.json()
        assert body['configured'] is True
        assert body['account_number_masked'] == '****7890'
        assert body['identification_masked'] == '****9087'
        assert 'account_number' not in body and 'identification_number' not in body

        record = TutorPayoutAccount.objects.get(tutor=teacher_user.user)
        assert record.account_last_four == '7890' and record.key_version == 'v1'
        assert all(secret not in record.encrypted_payload for secret in ('1234567890', 'Test Tutor', 'Capitec', '9001015009087'))

    def test_wrong_password_never_writes(self, teacher_user):
        response = client(teacher_user.user).post(
            SETTINGS, payout_payload(current_password='wrong'), format='json')
        assert response.status_code == 400
        assert 'current_password' in response.json()
        assert not TutorPayoutAccount.objects.exists()

    @pytest.mark.parametrize('changes,field', [
        ({'bank_name': 'Unsupported Bank'}, 'bank_name'),
        ({'branch_code': '123'}, 'branch_code'),
        ({'branch_code': '123456'}, 'branch_code'),
        ({'account_number': '12A456'}, 'account_number'),
        ({'account_type': 'business'}, 'account_type'),
    ])
    def test_bank_data_validation(self, teacher_user, changes, field):
        response = client(teacher_user.user).post(SETTINGS, payout_payload(**changes), format='json')
        assert response.status_code == 400 and field in response.json()

    def test_accounts_are_tutor_scoped(self, teacher_user, django_user_model):
        other = django_user_model.objects.create_user(
            username='other_tutor', email='other@example.com', password='password123', role='teacher')
        assert client(teacher_user.user).post(SETTINGS, payout_payload(), format='json').status_code == 201
        assert client(other).get(SETTINGS).json() == {'configured': False}

    def test_old_records_decrypt_during_key_rotation_and_updates_use_active_key(self, teacher_user, settings):
        api = client(teacher_user.user)
        assert api.post(SETTINGS, payout_payload(), format='json').status_code == 201
        old_key = settings.PAYOUT_DATA_KEYS['v1']
        settings.PAYOUT_DATA_KEYS = {'v1': old_key, 'v2': Fernet.generate_key().decode()}
        settings.PAYOUT_DATA_ACTIVE_KEY = 'v2'
        assert api.get(SETTINGS).json()['account_number_masked'] == '****7890'
        assert api.post(SETTINGS, payout_payload(account_number='9876543210'), format='json').status_code == 200
        record = TutorPayoutAccount.objects.get(tutor=teacher_user.user)
        assert record.key_version == 'v2' and record.account_last_four == '3210'

    def test_student_cannot_read_or_write_payout_settings(self, student_user):
        api = client(student_user)
        assert api.get(SETTINGS).status_code == 403
        assert api.post(SETTINGS, payout_payload(), format='json').status_code == 403


@pytest.mark.django_db
class TestTutorWallet:
    def test_wallet_uses_funding_for_pending_and_ledger_2020_for_cleared(self, teacher_user, student_user):
        # The wallet lists newest first, so the three records need genuinely different creation times. Created back to back they
        # can share a clock tick (Windows timer granularity) and the order becomes undefined: pin each one explicitly.
        from unittest import mock
        base = timezone.now()

        def at(seconds):
            return mock.patch('django.utils.timezone.now', return_value=base + timedelta(seconds=seconds))

        with at(0):
            pending = booking(teacher_user, student_user)
            funding_for(pending, 'pending-ref')
        with at(10):
            cleared = booking(
                teacher_user, student_user, status=Booking.Status.COMPLETED, start_offset_minutes=30,
            )
            funding_for(cleared, 'cleared-ref')
            cleared.escrow_cleared_at = timezone.now()
            cleared.save(update_fields=['escrow_cleared_at', 'updated_at'])
        with at(20):
            LedgerEntry.objects.create(
                journal_batch_id='11111111-1111-1111-1111-111111111111',
                account=LedgerAccount.LIABILITY_TUTOR_PAYABLE, entry_type=LedgerEntry.EntryType.CREDIT,
                amount=Decimal('6.40'), currency='USD', fx_rate_to_zar=Decimal('18.000000'),
                fx_source='capture_test', amount_zar=Decimal('115.20'), event_type=LedgerEntry.EventType.ESCROW_CLEARED,
                description='Tutor payable', booking=cleared, user=teacher_user.user,
            )

        body = client(teacher_user.user).get(WALLET).json()
        assert Decimal(str(body['pending_escrow_zar'])) == Decimal('115.20')
        assert Decimal(str(body['cleared_balance_zar'])) == Decimal('115.20')
        assert body['fx_context'] == [{'currency': 'USD', 'fx_rate_to_zar': 18.0, 'fx_source': 'capture_test'}]
        assert [row['status'] for row in body['transactions']] == ['cleared', 'pending']
        assert body['payout_bank_account'] is None

    def test_payout_debit_reduces_cleared_balance_and_appears_in_history(self, teacher_user):
        for entry_type, event_type, amount in (
            (LedgerEntry.EntryType.CREDIT, LedgerEntry.EventType.ESCROW_CLEARED, '200.00'),
            (LedgerEntry.EntryType.DEBIT, LedgerEntry.EventType.PAYOUT_EXECUTED, '75.00'),
        ):
            LedgerEntry.objects.create(
                journal_batch_id='22222222-2222-2222-2222-222222222222' if entry_type == 'credit' else '33333333-3333-3333-3333-333333333333',
                account=LedgerAccount.LIABILITY_TUTOR_PAYABLE, entry_type=entry_type,
                amount=Decimal(amount), currency='ZAR', fx_rate_to_zar=Decimal('1.000000'), fx_source='transaction_currency',
                amount_zar=Decimal(amount), event_type=event_type, description='entry', user=teacher_user.user,
            )
        body = client(teacher_user.user).get(WALLET).json()
        assert Decimal(str(body['cleared_balance_zar'])) == Decimal('125.00')
        assert body['transactions'][0]['status'] == 'paid_out'

    def test_admin_payout_preview_only_includes_configured_accounts(self, teacher_user, admin_user):
        LedgerEntry.objects.create(
            journal_batch_id='44444444-4444-4444-4444-444444444444',
            account=LedgerAccount.LIABILITY_TUTOR_PAYABLE, entry_type=LedgerEntry.EntryType.CREDIT,
            amount=Decimal('100.00'), currency='ZAR', fx_rate_to_zar=Decimal('1.000000'),
            fx_source='transaction_currency', amount_zar=Decimal('100.00'),
            event_type=LedgerEntry.EventType.ESCROW_CLEARED, description='payable', user=teacher_user.user,
        )
        assert client(admin_user).get(ADMIN_PAYOUTS).json() == []
        assert client(teacher_user.user).post(SETTINGS, payout_payload(), format='json').status_code == 201
        body = client(admin_user).get(ADMIN_PAYOUTS).json()
        assert len(body) == 1
        assert body[0]['bank_name'] == 'Capitec Bank' and body[0]['account_number_masked'] == '****7890'


@pytest.mark.django_db
class TestPayoutSettingsThrottle:
    def test_password_guesses_are_limited_but_reading_is_not(self, teacher_user):
        from django.core.cache import cache
        cache.clear()
        c = client(teacher_user.user)
        for _ in range(5):
            res = c.post(SETTINGS, payout_payload(current_password='wrong-password'), format='json')
            assert res.status_code == 400
        assert c.post(SETTINGS, payout_payload(current_password='still-wrong'), format='json').status_code == 429
        assert c.get(SETTINGS).status_code == 200           # the masked read stays available
        assert not TutorPayoutAccount.objects.exists()
