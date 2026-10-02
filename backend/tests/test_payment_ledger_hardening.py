from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.payments.models import (
    FulfillmentDispatch,
    GatewayAnomaly,
    LedgerAccount,
    LedgerEntry,
    PaymentTransaction,
)
from apps.payments.services.ledger_service import (
    UnbalancedJournalEntryError,
    record_journal_entries,
    record_payment_capture_entry,
)
from apps.payments.services.reconciliation import ReconciliationResult, reconcile_initialized_transaction
from apps.payments.services.webhook_handler import dispatch_fulfillment


def _booking(teacher_user, student_user):
    start = timezone.now() + timedelta(days=1)
    return Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED,
    )


@pytest.mark.django_db
def test_gateway_fee_is_persisted_and_balanced_in_currency_and_zar(teacher_user, student_user):
    booking = _booking(teacher_user, student_user)
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYFAST,
        gateway_reference='PF-FEE-1',
        amount=Decimal('162.00'),
        currency='ZAR',
        fx_rate_to_zar=Decimal('1.000000'),
        fx_source='transaction_currency',
        provider_fee_amount=Decimal('3.72'),
        provider_fee_currency='ZAR',
        status=PaymentTransaction.Status.SUCCESS,
    )
    entries = record_payment_capture_entry(tx, booking=booking, user=student_user)

    assert len(entries) == 3
    fee = next(row for row in entries if row.account == LedgerAccount.EXPENSE_GATEWAY_FEES)
    assert fee.amount == fee.amount_zar == Decimal('3.72')
    assert fee.fx_source == 'transaction_currency'
    assert sum(row.amount for row in entries if row.entry_type == 'debit') == Decimal('162.00')
    assert sum(row.amount for row in entries if row.entry_type == 'credit') == Decimal('162.00')
    assert sum(row.amount_zar for row in entries if row.entry_type == 'debit') == Decimal('162.00')
    assert sum(row.amount_zar for row in entries if row.entry_type == 'credit') == Decimal('162.00')


@pytest.mark.django_db
def test_journal_cannot_hide_imbalance_across_currencies():
    with pytest.raises(UnbalancedJournalEntryError):
        record_journal_entries(
            entries=[
                {'account': LedgerAccount.ASSET_GATEWAY_PAYPAL, 'entry_type': 'debit',
                 'amount': Decimal('10.00'), 'currency': 'USD'},
                {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'credit',
                 'amount': Decimal('10.00'), 'currency': 'EUR'},
            ],
            event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
            description='mixed-currency imbalance',
        )


@pytest.mark.django_db
def test_inconclusive_reconciliation_stays_initialized_and_is_durable(teacher_user, student_user):
    tx = PaymentTransaction.objects.create(
        booking=_booking(teacher_user, student_user),
        gateway=PaymentTransaction.Gateway.PAYFAST,
        gateway_reference='INIT-UNRESOLVED',
        amount=Decimal('162.00'),
        currency='ZAR',
    )
    result = reconcile_initialized_transaction(
        tx, lookup=lambda _: ReconciliationResult('unresolved', 'provider unavailable'))
    tx.refresh_from_db()

    assert result.state == 'unresolved'
    assert tx.status == PaymentTransaction.Status.INITIALIZED
    assert tx.reconciliation_attempts == 1 and tx.last_reconciled_at is not None
    assert GatewayAnomaly.objects.filter(
        payment_transaction=tx, reason='reconciliation_unresolved', resolved=False).exists()


@pytest.mark.django_db
def test_reconciliation_marks_failed_only_on_authoritative_provider_result(teacher_user, student_user):
    tx = PaymentTransaction.objects.create(
        booking=_booking(teacher_user, student_user),
        gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference='CAP-DECLINED',
        amount=Decimal('9.00'),
        currency='USD',
    )
    reconcile_initialized_transaction(
        tx, lookup=lambda _: ReconciliationResult('failed', 'PayPal reports DECLINED'))
    tx.refresh_from_db()
    assert tx.status == PaymentTransaction.Status.FAILED


@pytest.mark.django_db
def test_broker_dispatch_failure_creates_retryable_state(monkeypatch, teacher_user, student_user):
    booking = _booking(teacher_user, student_user)

    def unavailable(*args, **kwargs):
        raise RuntimeError('broker unavailable')

    monkeypatch.setattr('apps.integrations.tasks.dispatch_booking_fulfillment.delay', unavailable)
    dispatch_fulfillment(str(booking.id))

    state = FulfillmentDispatch.objects.get(booking=booking)
    assert state.status == FulfillmentDispatch.Status.RETRYABLE
    assert state.attempts == 1
    assert state.next_retry_at is not None
    assert 'broker unavailable' in state.last_error


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_direct_ledger_update_and_delete():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL trigger integration test')
    entries = record_journal_entries(
        entries=[
            {'account': LedgerAccount.ASSET_GATEWAY_PAYPAL, 'entry_type': 'debit',
             'amount': Decimal('9.00'), 'currency': 'USD'},
            {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'credit',
             'amount': Decimal('9.00'), 'currency': 'USD'},
        ],
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description='database immutability trigger',
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('UPDATE payments_ledgerentry SET amount = 1 WHERE id = %s', [str(entries[0].id)])
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('DELETE FROM payments_ledgerentry WHERE id = %s', [str(entries[0].id)])
