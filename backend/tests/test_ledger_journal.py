import pytest
import uuid
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.bookings.models import Booking, AttendanceAudit
from apps.payments.models import PaymentTransaction, CreditBundle, LedgerEntry, LedgerAccount, LedgerImmutabilityError
from apps.payments.services.ledger_service import (
    record_journal_entries,
    record_payment_capture_entry,
    record_escrow_clearance_entry,
    record_payout_batch_entry,
    record_dispute_settlement_entry,
    record_compensation_entry,
    record_def501_quarantine_entry,
    get_general_ledger_trial_balance,
    get_ledger_telemetry,
    UnbalancedJournalEntryError,
    DEFAULT_FX_USD_TO_ZAR,
)
from apps.payments.services.webhook_handler import process_payment_webhook
from apps.payments.services.funding import ensure_gateway_funding
from apps.payments.services import refunds
from apps.payments.models import RefundRequest
from apps.payments.tasks import release_cleared_escrow_task
from apps.admin_api.models import DisputeCase, PayoutBatch


def fund_booking(booking, amount=Decimal('9.00'), *, currency='USD', status=PaymentTransaction.Status.SUCCESS):
    tx = PaymentTransaction.objects.create(
        booking=booking, gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f'FUND-{booking.id}-{uuid.uuid4().hex[:6]}', amount=amount,
        currency=currency, status=status)
    ensure_gateway_funding(tx, booking)
    return tx


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        username="student_ledger",
        email="student_ledger@test.com",
        password="password123",
        role=User.Role.STUDENT,
        country="JP",
        timezone="Asia/Tokyo"
    )


@pytest.fixture
def teacher_user(db):
    user = User.objects.create_user(
        username="teacher_ledger",
        email="teacher_ledger@test.com",
        password="password123",
        role=User.Role.TEACHER,
        country="ZA",
        timezone="Africa/Johannesburg"
    )
    profile = TeacherProfile.objects.create(
        user=user,
        headline="Senior English Tutor",
        price_per_25min_usd=Decimal('9.00'),
        is_verified=True,
        is_active=True
    )
    return profile


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin_ledger",
        email="admin_ledger@test.com",
        password="password123",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True
    )


@pytest.mark.django_db
def test_zero_sum_invariant_enforcement():
    """
    Asserts that unbalanced journal entries raise UnbalancedJournalEntryError
    and atomic rollback prevents any dangling LedgerEntry records.
    """
    initial_count = LedgerEntry.objects.count()
    batch_id = uuid.uuid4()

    unbalanced_entries = [
        {
            'account': LedgerAccount.ASSET_GATEWAY_PAYPAL,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': Decimal('10.00'),
            'currency': 'USD'
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': Decimal('8.00'),  # Mismatch: 10 != 8
            'currency': 'USD'
        }
    ]

    with pytest.raises(UnbalancedJournalEntryError):
        record_journal_entries(
            entries=unbalanced_entries,
            event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
            description="Test unbalanced batch",
            journal_batch_id=batch_id
        )

    # Invariant: Zero records persisted
    assert LedgerEntry.objects.count() == initial_count


@pytest.mark.django_db
def test_payment_capture_ledger_journal(student_user, teacher_user):
    """
    Tests student checkout double-entry journal capture and SARB ZAR calculation.
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now + timedelta(days=1),
        end_time_utc=now + timedelta(days=1, minutes=25),
        status=Booking.Status.PENDING_PAYMENT
    )
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f"PAYPAL-TX-{uuid.uuid4().hex[:8]}",
        amount=Decimal('9.00'),
        currency='USD',
        status=PaymentTransaction.Status.SUCCESS
    )

    entries = record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)
    assert len(entries) == 2

    debit_entry = [e for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT][0]
    credit_entry = [e for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT][0]

    assert debit_entry.account == LedgerAccount.ASSET_GATEWAY_PAYPAL
    assert debit_entry.amount == Decimal('9.00')
    assert debit_entry.amount_zar == Decimal('168.75')  # 9.00 * 18.75

    assert credit_entry.account == LedgerAccount.LIABILITY_STUDENT_ESCROW
    assert credit_entry.amount == Decimal('9.00')
    assert credit_entry.amount_zar == Decimal('168.75')


@pytest.mark.django_db
def test_escrow_clearance_double_entry_split(student_user, teacher_user):
    """
    Tests 24h dual-verified escrow clearance fee split:
    DR Liability: Student Escrow ($9.00)
    CR Liability: Tutor Payable (80% = $7.20 / R135.00)
    CR Revenue: Platform Commission (20% = $1.80 / R33.75)
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(days=2),
        end_time_utc=now - timedelta(days=2, minutes=-25),
        status=Booking.Status.COMPLETED
    )
    fund_booking(booking)

    entries = record_escrow_clearance_entry(booking=booking, amount_usd=Decimal('9.00'))
    assert len(entries) == 3

    dr_entries = [e for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT]
    cr_entries = [e for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT]

    assert len(dr_entries) == 1
    assert len(cr_entries) == 2

    assert dr_entries[0].account == LedgerAccount.LIABILITY_STUDENT_ESCROW
    assert dr_entries[0].amount == Decimal('9.00')

    tutor_cr = [e for e in cr_entries if e.account == LedgerAccount.LIABILITY_TUTOR_PAYABLE][0]
    platform_cr = [e for e in cr_entries if e.account == LedgerAccount.REVENUE_PLATFORM_COMMISSION][0]

    assert tutor_cr.amount == Decimal('7.20')
    assert tutor_cr.amount_zar == Decimal('129.60')  # 7.20 * persisted 18.00 capture FX

    assert platform_cr.amount == Decimal('1.80')
    assert platform_cr.amount_zar == Decimal('32.40')  # 1.80 * persisted 18.00 capture FX

    # Sum DR == Sum CR
    assert dr_entries[0].amount == tutor_cr.amount + platform_cr.amount


@pytest.mark.django_db
def test_payout_batch_execution_ledger(admin_user):
    """
    Tests ACB South African bank batch payout disbursement:
    DR Liability: Tutor Payables (R5,520.00)
    CR Asset: Operating Bank Cash (R5,520.00)
    """
    batch = PayoutBatch.objects.create(
        batch_reference=f"ACB-BATCH-{uuid.uuid4().hex[:6].upper()}",
        total_payout_zar=Decimal('5520.00'),
        recipients_count=3,
        status=PayoutBatch.Status.PROCESSED,
        executed_by=admin_user
    )

    entries = record_payout_batch_entry(payout_batch=batch, amount_zar=batch.total_payout_zar, user=admin_user)
    assert len(entries) == 2

    debit = [e for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT][0]
    credit = [e for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT][0]

    assert debit.account == LedgerAccount.LIABILITY_TUTOR_PAYABLE
    assert debit.amount == Decimal('5520.00')
    assert debit.currency == 'ZAR'
    assert debit.amount_zar == Decimal('5520.00')

    assert credit.account == LedgerAccount.ASSET_OPERATING_BANK
    assert credit.amount == Decimal('5520.00')
    assert credit.currency == 'ZAR'
    assert credit.amount_zar == Decimal('5520.00')


@pytest.mark.django_db
def test_dispute_tribunal_50_50_platform_absorbed(admin_user, student_user, teacher_user):
    """
    Tests 50/50 dispute split where platform absorbs the cost:
    - Escrow clears to tutor & platform take rate
    - Platform absorbs student credit restitution via EXPENSE_DISPUTE_SETTLEMENT
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=3),
        end_time_utc=now - timedelta(hours=2, minutes=35),
        status=Booking.Status.DISPUTED
    )
    fund_booking(booking)
    dispute = DisputeCase.objects.create(
        booking=booking,
        student=student_user,
        teacher=teacher_user,
        student_statement="Audio failure during call",
        teacher_statement="Waited online",
        status=DisputeCase.Status.OPEN
    )

    entries = record_dispute_settlement_entry(dispute_case=dispute, resolution='split_50_50')
    assert len(entries) == 5

    total_dr = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
    total_cr = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT)

    assert total_dr == Decimal('18.00')  # $9 escrow + $9 platform expense
    assert total_cr == Decimal('18.00')  # $7.20 tutor + $1.80 commission + $9.00 student refund

    expense_entry = [e for e in entries if e.account == LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT][0]
    assert expense_entry.amount == Decimal('9.00')


@pytest.mark.django_db
def test_def501_late_payment_quarantine_journal(student_user, teacher_user):
    """
    Tests DEF-501 late payment quarantine and restitution journal entries.
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=1),
        end_time_utc=now - timedelta(minutes=35),
        status=Booking.Status.PENDING_PAYMENT
    )
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f"LATE-PAYPAL-{uuid.uuid4().hex[:8]}",
        amount=Decimal('9.00'),
        currency='USD',
        status=PaymentTransaction.Status.SUCCESS
    )

    entries = record_def501_quarantine_entry(payment_transaction=tx, booking=booking, user=student_user)
    assert len(entries) == 4

    total_dr = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
    total_cr = sum(e.amount for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT)
    assert total_dr == total_cr == Decimal('18.00')


@pytest.mark.django_db
def test_trial_balance_zero_sum_audit(student_user, teacher_user, admin_user):
    """
    Generates a realistic lifecycle sequence:
    1. 5 Student checkouts ($45.00)
    2. 3 Escrow clearances ($27.00)
    3. 1 SA EFT Payout batch ($1500.00 ZAR)
    4. 1 Eskom Outage refund ($9.00)
    5. 1 Tutor No-Show compensation ($9.00)
    Verifies that the General Ledger Trial Balance has exactly 0 variance.
    """
    now = timezone.now()

    # 1. 5 Checkouts
    for i in range(5):
        b = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(days=i + 1),
            end_time_utc=now + timedelta(days=i + 1, minutes=25),
            status=Booking.Status.CONFIRMED
        )
        tx = PaymentTransaction.objects.create(
            booking=b,
            gateway=PaymentTransaction.Gateway.PAYPAL,
            gateway_reference=f"TX-AUDIT-{i}-{uuid.uuid4().hex[:6]}",
            amount=Decimal('9.00'),
            currency='USD',
            status=PaymentTransaction.Status.SUCCESS
        )
        record_payment_capture_entry(payment_transaction=tx, booking=b, user=student_user)

    # 2. 3 Escrow clearances
    for i in range(3):
        b = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now - timedelta(days=i + 2),
            end_time_utc=now - timedelta(days=i + 2, minutes=-25),
            status=Booking.Status.COMPLETED
        )
        fund_booking(b)
        record_escrow_clearance_entry(booking=b, amount_usd=Decimal('9.00'))

    # 3. 1 Payout batch
    batch = PayoutBatch.objects.create(
        batch_reference="ACB-AUDIT-001",
        total_payout_zar=Decimal('1500.00'),
        recipients_count=2,
        status=PayoutBatch.Status.PROCESSED,
        executed_by=admin_user
    )
    record_payout_batch_entry(payout_batch=batch, amount_zar=Decimal('1500.00'), user=admin_user)

    # 4. 1 Eskom outage refund
    b_outage = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=5),
        end_time_utc=now - timedelta(hours=4, minutes=35),
        status=Booking.Status.INTERRUPTED_POWER
    )
    fund_booking(b_outage)
    refunds.request_refund(b_outage, RefundRequest.Reason.OUTAGE, event_type=LedgerEntry.EventType.OUTAGE_REFUND)

    # 5. 1 Tutor No-Show compensation
    record_compensation_entry(user=student_user, booking=b_outage, amount_usd=Decimal('9.00'), reason="No show audit test")

    # Run Trial Balance Audit
    trial_balance = get_general_ledger_trial_balance()
    assert trial_balance['is_balanced'] is True
    assert trial_balance['variance_zar'] == '0.00'
    assert Decimal(trial_balance['grand_debit_zar']) > 0
    assert trial_balance['grand_debit_zar'] == trial_balance['grand_credit_zar']


@pytest.mark.django_db
def test_end_to_end_webhook_to_escrow_task_journal_flow(student_user, teacher_user):
    """
    Full end-to-end pipeline test:
    1. process_payment_webhook confirms future booking and creates journal entry
    2. Lesson completes in the past and AttendanceAudit satisfies >= 20m attendance gate
    3. release_cleared_escrow_task runs and clears escrow into tutor payable + platform fee
    """
    now = timezone.now()
    slot_utc = now + timedelta(hours=2)
    slot_end = slot_utc + timedelta(minutes=25)

    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=slot_utc,
        end_time_utc=slot_end,
        status=Booking.Status.PENDING_PAYMENT
    )

    tx_id = f"PAYPAL-E2E-{uuid.uuid4().hex[:6]}"
    result = process_payment_webhook(
        booking_id=str(booking.id),
        gateway='paypal',
        transaction_id=tx_id,
        amount=9.0,
        currency='USD',
        status='success',
        raw_payload={"e2e": "test"}
    )
    assert result['status'] == 'success'

    # Verify payment capture journal entries
    tx = PaymentTransaction.objects.get(gateway_reference=tx_id)
    payment_entries = LedgerEntry.objects.filter(payment_transaction=tx, event_type=LedgerEntry.EventType.PAYMENT_CAPTURED)
    assert payment_entries.count() == 2

    # Advance time: Lesson was completed 25 hours ago
    past_end = now - timedelta(hours=25)
    booking.refresh_from_db()
    booking.start_time_utc = past_end - timedelta(minutes=25)
    booking.end_time_utc = past_end
    booking.status = Booking.Status.COMPLETED
    booking.save(update_fields=['start_time_utc', 'end_time_utc', 'status'])

    # Simulate lesson attendance
    AttendanceAudit.objects.create(
        booking=booking,
        participant_email=teacher_user.user.email,
        total_minutes=25
    )

    # Run escrow clearance task
    task_res = release_cleared_escrow_task()
    assert task_res['cleared_count'] == 1

    # Verify escrow clearance journal entries
    clearance_entries = LedgerEntry.objects.filter(booking=booking, event_type=LedgerEntry.EventType.ESCROW_CLEARED)
    assert clearance_entries.count() == 3

    # Total batch integrity
    trial = get_general_ledger_trial_balance()
    assert trial['is_balanced'] is True
    assert trial['variance_zar'] == '0.00'


@pytest.mark.django_db
def test_ledger_entry_immutability_enforcement():
    """
    Asserts that LedgerEntry instances and querysets are append-only.
    Direct modification or deletion of posted journal entries must raise ValidationError.
    """
    entries = record_journal_entries(
        entries=[
            {
                'account': LedgerAccount.ASSET_GATEWAY_PAYPAL,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': Decimal('15.00'),
                'currency': 'USD'
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': Decimal('15.00'),
                'currency': 'USD'
            }
        ],
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description="Immutability audit batch"
    )
    entry = entries[0]
    entry_id = entry.id

    # 1. Direct save() modification must raise ValidationError
    entry.amount = Decimal('999.00')
    with pytest.raises(ValidationError, match="strictly immutable and cannot be updated"):
        entry.save()

    # Verify amount was NOT mutated in the database
    refreshed = LedgerEntry.objects.get(id=entry_id)
    assert refreshed.amount == Decimal('15.00')

    # 2. Direct delete() must raise ValidationError
    with pytest.raises(ValidationError, match="strictly immutable and cannot be deleted"):
        entry.delete()

    # 3. QuerySet bulk update() must raise ValidationError
    with pytest.raises(ValidationError, match="strictly immutable and cannot be updated"):
        LedgerEntry.objects.filter(id=entry_id).update(amount=Decimal('0.00'))

    # 4. QuerySet bulk delete() must raise ValidationError
    with pytest.raises(ValidationError, match="strictly immutable and cannot be deleted"):
        LedgerEntry.objects.filter(id=entry_id).delete()

    # Ensure record remains unchanged and intact
    assert LedgerEntry.objects.filter(id=entry_id).exists()


@pytest.mark.django_db
def test_ledger_edge_cases_negative_and_zero_amounts():
    """
    Asserts that zero, negative amounts or empty lists are rejected before journal creation.
    """
    # Empty entries list
    with pytest.raises(ValueError, match="Cannot record empty journal entries list"):
        record_journal_entries(
            entries=[],
            event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
            description="Empty batch"
        )

    # Zero amount
    with pytest.raises(ValueError, match="must be positive"):
        record_journal_entries(
            entries=[
                {
                    'account': LedgerAccount.ASSET_GATEWAY_PAYPAL,
                    'entry_type': LedgerEntry.EntryType.DEBIT,
                    'amount': Decimal('0.00'),
                    'currency': 'USD'
                },
                {
                    'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                    'entry_type': LedgerEntry.EntryType.CREDIT,
                    'amount': Decimal('0.00'),
                    'currency': 'USD'
                }
            ],
            event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
            description="Zero amount batch"
        )

    # Negative amount
    with pytest.raises(ValueError, match="must be positive"):
        record_journal_entries(
            entries=[
                {
                    'account': LedgerAccount.ASSET_GATEWAY_PAYPAL,
                    'entry_type': LedgerEntry.EntryType.DEBIT,
                    'amount': Decimal('-5.00'),
                    'currency': 'USD'
                },
                {
                    'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                    'entry_type': LedgerEntry.EntryType.CREDIT,
                    'amount': Decimal('-5.00'),
                    'currency': 'USD'
                }
            ],
            event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
            description="Negative amount batch"
        )


@pytest.mark.django_db
def test_ledger_dispute_resolutions_full_refund_and_release_tutor(student_user, teacher_user):
    """
    Verifies double-entry journal balance for FULL_REFUND_STUDENT and RELEASE_TUTOR.
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=2),
        end_time_utc=now - timedelta(hours=1, minutes=35),
        status=Booking.Status.DISPUTED
    )
    fund_booking(booking)
    dispute = DisputeCase.objects.create(
        booking=booking,
        student=student_user,
        teacher=teacher_user,
        student_statement="Audio issue",
        status=DisputeCase.Status.OPEN
    )

    # 1. FULL_REFUND_STUDENT goes through the refund service (gateway refund payable), never the dispute settlement helper
    with pytest.raises(ValueError):
        record_dispute_settlement_entry(dispute_case=dispute, resolution='full_refund_student')
    refunds.request_refund(booking, RefundRequest.Reason.DISPUTE, event_type=LedgerEntry.EventType.DISPUTE_RESOLVED, dispute_case=dispute)
    refund_entries = list(LedgerEntry.objects.filter(dispute_case=dispute))
    assert len(refund_entries) == 2
    assert {e.account for e in refund_entries} == {LedgerAccount.LIABILITY_STUDENT_ESCROW, LedgerAccount.LIABILITY_REFUNDS_PAYABLE}
    dr = sum(e.amount for e in refund_entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
    cr = sum(e.amount for e in refund_entries if e.entry_type == LedgerEntry.EntryType.CREDIT)
    assert dr == cr == Decimal('9.00')

    # 2. RELEASE_TUTOR
    release_entries = record_dispute_settlement_entry(dispute_case=dispute, resolution='release_tutor')
    assert len(release_entries) == 3
    dr_rel = sum(e.amount for e in release_entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
    cr_rel = sum(e.amount for e in release_entries if e.entry_type == LedgerEntry.EntryType.CREDIT)
    assert dr_rel == cr_rel == Decimal('9.00')

    tutor_cr = [e for e in release_entries if e.account == LedgerAccount.LIABILITY_TUTOR_PAYABLE][0]
    platform_cr = [e for e in release_entries if e.account == LedgerAccount.REVENUE_PLATFORM_COMMISSION][0]
    assert tutor_cr.amount == Decimal('7.20')
    assert platform_cr.amount == Decimal('1.80')


@pytest.mark.django_db
def test_ledger_sarb_zar_rounding_balancing_guarantee():
    """
    Asserts that even under unusual multi-digit fractional exchange rates,
    total SARB ZAR debits always mathematically equal total SARB ZAR credits.
    """
    custom_fx = Decimal('18.3333')
    entries = record_journal_entries(
        entries=[
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': Decimal('7.33'),
                'currency': 'USD'
            },
            {
                'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': Decimal('5.86'),
                'currency': 'USD'
            },
            {
                'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': Decimal('1.47'),
                'currency': 'USD'
            }
        ],
        event_type=LedgerEntry.EventType.ESCROW_CLEARED,
        description="Fractional rate rounding test",
        fx_rate_to_zar=custom_fx
    )

    zar_debits = sum(e.amount_zar for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT)
    zar_credits = sum(e.amount_zar for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT)
    assert zar_debits == zar_credits


@pytest.mark.django_db
def test_student_refund_journal_entries_gateway_and_wallet(student_user, teacher_user):
    """
    A refund is two ledger steps through the refund service:
    - decision: DR Escrow Liability -> CR Gateway Refunds Payable
    - then EITHER the gateway pays it (DR Refunds Payable -> CR Gateway Cash) OR the student converts it
      (DR Refunds Payable -> CR Student Wallet Credits)
    """
    now = timezone.now()

    def paid_booking(reference, hours):
        booking = Booking.objects.create(
            teacher=teacher_user, student=student_user, status=Booking.Status.CONFIRMED,
            start_time_utc=now + timedelta(days=1, hours=hours), end_time_utc=now + timedelta(days=1, hours=hours, minutes=25))
        tx = PaymentTransaction.objects.create(
            booking=booking, gateway=PaymentTransaction.Gateway.PAYPAL, gateway_reference=f"{reference}-{uuid.uuid4().hex[:8]}",
            amount=Decimal('9.00'), currency='USD', status=PaymentTransaction.Status.SUCCESS)
        ensure_gateway_funding(tx, booking)
        return booking

    def legs(entries):
        dr = [e for e in entries if e.entry_type == LedgerEntry.EntryType.DEBIT]
        cr = [e for e in entries if e.entry_type == LedgerEntry.EntryType.CREDIT]
        assert len(dr) == len(cr) == 1 and dr[0].amount == cr[0].amount == Decimal('9.00')
        return dr[0].account, cr[0].account

    # 1. the gateway pays it
    b1 = paid_booking('REFUND-GW', 0)
    r1 = refunds.request_refund(b1, RefundRequest.Reason.STUDENT_CANCEL).refund
    assert legs(list(LedgerEntry.objects.filter(booking=b1, event_type=LedgerEntry.EventType.REFUND_ISSUED))) == (
        LedgerAccount.LIABILITY_STUDENT_ESCROW, LedgerAccount.LIABILITY_REFUNDS_PAYABLE)
    refunds.mark_processed(r1.pk, 'GW-REF-1')
    assert legs(list(LedgerEntry.objects.filter(booking=b1, event_type=LedgerEntry.EventType.GATEWAY_REFUND_PAID))) == (
        LedgerAccount.LIABILITY_REFUNDS_PAYABLE, LedgerAccount.ASSET_GATEWAY_PAYPAL)

    # 2. the student converts it to wallet credit instead
    b2 = paid_booking('REFUND-WALLET', 3)
    r2 = refunds.request_refund(b2, RefundRequest.Reason.STUDENT_CANCEL).refund
    refunds.convert_to_wallet(r2.pk)
    converted = [e for e in LedgerEntry.objects.filter(booking=b2, event_type=LedgerEntry.EventType.REFUND_ISSUED)
                 if e.account == LedgerAccount.LIABILITY_STUDENT_WALLET or
                 (e.account == LedgerAccount.LIABILITY_REFUNDS_PAYABLE and e.entry_type == LedgerEntry.EntryType.DEBIT)]
    assert legs(converted) == (LedgerAccount.LIABILITY_REFUNDS_PAYABLE, LedgerAccount.LIABILITY_STUDENT_WALLET)


@pytest.mark.django_db
def test_ledger_immutability_custom_exception():
    """
    Asserts LedgerImmutabilityError is raised specifically on mutate attempts.
    """
    entries = record_journal_entries(
        entries=[
            {
                'account': LedgerAccount.ASSET_GATEWAY_PAYPAL,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': Decimal('9.00'),
                'currency': 'USD'
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': Decimal('9.00'),
                'currency': 'USD'
            }
        ],
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description="Immutability check"
    )
    entry = entries[0]
    entry_id = entry.id

    entry.amount = Decimal('100.00')
    with pytest.raises(LedgerImmutabilityError):
        entry.save()

    with pytest.raises(LedgerImmutabilityError):
        entry.delete()

    with pytest.raises(LedgerImmutabilityError):
        LedgerEntry.objects.filter(id=entry_id).update(amount=Decimal('50.00'))

    with pytest.raises(LedgerImmutabilityError):
        LedgerEntry.objects.filter(id=entry_id).delete()


@pytest.mark.django_db
def test_ledger_telemetry_live_balance_calculation(student_user, teacher_user):
    """
    Verifies get_ledger_telemetry correctly calculates live balances across all accounts:
    - Gateway cash
    - Escrow liabilities
    - Tutor payables
    - Student wallet liabilities
    - Net platform revenue
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(days=2),
        end_time_utc=now - timedelta(days=2, minutes=-25),
        status=Booking.Status.COMPLETED
    )
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f"TEL-TX-{uuid.uuid4().hex[:8]}",
        amount=Decimal('9.00'),
        currency='USD',
        status=PaymentTransaction.Status.SUCCESS
    )
    ensure_gateway_funding(tx, booking)

    # 1. Capture payment ($9)
    record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)

    # 2. Clear escrow ($7.20 tutor / $1.80 platform)
    record_escrow_clearance_entry(booking=booking, amount_usd=Decimal('9.00'))

    # 3. Telemetry inspection
    telemetry = get_ledger_telemetry()
    assert telemetry['trial_balance']['is_balanced'] is True
    assert telemetry['summary']['is_balanced'] is True

    balances = telemetry['live_balances']
    assert balances['gateway_cash_paypal_usd'] == '9.00'
    assert balances['tutor_payable_usd'] == '7.20'
    assert balances['gross_commission_usd'] == '1.80'
    assert balances['net_revenue_usd'] == '1.80'
    assert balances['escrow_liability_usd'] == '0.00'


@pytest.mark.django_db
def test_admin_finance_ledger_api_endpoint(admin_user, student_user, teacher_user):
    """
    Tests GET /api/v1/admin/finance/ledger/ returns live gateway balances,
    pending escrow, tutor liabilities, net revenue, and individual escrow items.
    """
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now + timedelta(hours=5),
        end_time_utc=now + timedelta(hours=5, minutes=25),
        status=Booking.Status.CONFIRMED
    )
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYPAL,
        gateway_reference=f"ADM-TX-{uuid.uuid4().hex[:8]}",
        amount=Decimal('9.00'),
        currency='USD',
        status=PaymentTransaction.Status.SUCCESS
    )
    record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)

    client = APIClient()
    client.force_authenticate(user=admin_user)

    res = client.get('/api/v1/admin/finance/ledger/')
    assert res.status_code == 200
    data = res.json()

    assert 'live_balances' in data
    assert 'summary' in data
    assert 'trial_balance' in data
    assert 'items' in data

    balances = data['live_balances']
    assert 'gateway_cash_paypal_usd' in balances
    assert 'escrow_liability_usd' in balances
    assert 'tutor_payable_usd' in balances
    assert 'net_revenue_usd' in balances
    assert balances['escrow_liability_usd'] == '9.00'

    # Test view=items returns flat array
    res_items = client.get('/api/v1/admin/finance/ledger/?view=items')
    assert res_items.status_code == 200
    items_data = res_items.json()
    assert isinstance(items_data, list)
    assert len(items_data) >= 1



