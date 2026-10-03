"""Task 10.1 slice B: the ledger has no default exchange rate. Every journal carries the rate it was captured at."""
import inspect
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import Booking
from apps.payments import models as payment_models
from apps.payments.models import LedgerAccount, LedgerEntry, PaymentTransaction
from apps.payments.services import ledger_service
from apps.payments.services.funding import ensure_gateway_funding, persist_capture_snapshot
from apps.payments.services.ledger_service import (
    MissingLedgerFx, record_compensation_entry, record_def501_quarantine_entry, record_journal_entries,
    record_payment_capture_entry, record_unallocated_payment_entry,
)
from apps.payments.services.pricing import usd_to_zar_rate

pytestmark = pytest.mark.django_db

DR, CR = LedgerEntry.EntryType.DEBIT, LedgerEntry.EntryType.CREDIT


def _lines(currency='USD', amount='10.00'):
    return [
        {'account': LedgerAccount.ASSET_GATEWAY_PAYPAL, 'entry_type': DR, 'amount': Decimal(amount), 'currency': currency},
        {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': CR, 'amount': Decimal(amount), 'currency': currency},
    ]


def _post(**fx):
    return record_journal_entries(entries=_lines(), event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
                                  description='fx test', **fx)


@pytest.fixture
def booking(student_user, teacher_user):
    now = timezone.now()
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, status=Booking.Status.PENDING_PAYMENT,
        start_time_utc=now + timedelta(days=1), end_time_utc=now + timedelta(days=1, minutes=25))


def _tx(booking, *, amount='9.00', currency='USD', **extra):
    return PaymentTransaction.objects.create(
        booking=booking, gateway=PaymentTransaction.Gateway.PAYPAL, gateway_reference=f'FX-{uuid.uuid4().hex[:8]}',
        amount=Decimal(amount), currency=currency, status=PaymentTransaction.Status.SUCCESS, **extra)


# ---- the engine -------------------------------------------------------------------------------------------------

def test_no_fx_raises_and_posts_nothing():
    with pytest.raises(MissingLedgerFx):
        _post()
    assert LedgerEntry.objects.count() == 0


@pytest.mark.parametrize('fx', [
    {'fx_rate_to_zar': Decimal('18'), 'fx_source': None},
    {'fx_rate_to_zar': Decimal('18'), 'fx_source': ''},
    {'fx_rate_to_zar': None, 'fx_source': 'price_catalog'},
    {'fx_rate_to_zar': Decimal('0'), 'fx_source': 'price_catalog'},
    {'fx_rate_to_zar': Decimal('-1'), 'fx_source': 'price_catalog'},
])
def test_partial_or_nonsense_fx_raises(fx):
    with pytest.raises(MissingLedgerFx):
        _post(**fx)
    assert LedgerEntry.objects.count() == 0


def test_missing_ledger_fx_is_a_value_error():
    assert issubclass(MissingLedgerFx, ValueError)


def test_supplied_rate_is_stored_and_used_for_the_zar_valuation():
    rate = Decimal('17.250000')
    entries = _post(fx_rate_to_zar=rate, fx_source='capture_test')
    assert {e.fx_rate_to_zar for e in entries} == {rate}
    assert {e.fx_source for e in entries} == {'capture_test'}
    assert {e.amount_zar for e in entries} == {Decimal('172.50')}


def test_zar_journal_takes_one_and_transaction_currency():
    entries = record_journal_entries(
        entries=_lines('ZAR', '162.00'), event_type=LedgerEntry.EventType.PAYMENT_CAPTURED, description='zar',
        currency='ZAR', fx_rate_to_zar=Decimal('1'), fx_source='transaction_currency')
    assert {(e.fx_rate_to_zar, e.amount_zar) for e in entries} == {(Decimal('1'), Decimal('162.00'))}


def test_new_rows_can_never_use_the_legacy_default_source():
    with pytest.raises(MissingLedgerFx):
        _post(fx_rate_to_zar=Decimal('18.75'), fx_source='legacy_default')
    assert LedgerEntry.objects.count() == 0


def test_the_model_refuses_a_new_legacy_default_row_but_keeps_the_choice_for_history():
    entry = LedgerEntry(journal_batch_id=uuid.uuid4(), account=LedgerAccount.ASSET_GATEWAY_PAYPAL, entry_type=DR,
                        amount=Decimal('1.00'), currency='USD', fx_rate_to_zar=Decimal('18.75'),
                        fx_source='legacy_default', amount_zar=Decimal('18.75'),
                        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED, description='x')
    with pytest.raises(MissingLedgerFx):
        entry.save()
    assert LedgerEntry.objects.count() == 0


# ---- no default anywhere ----------------------------------------------------------------------------------------

def test_the_default_constant_is_gone():
    assert not hasattr(ledger_service, 'DEFAULT_FX_USD_TO_ZAR')


def test_the_model_has_no_fx_default():
    for name in ('fx_rate_to_zar', 'fx_source'):
        assert not LedgerEntry._meta.get_field(name).has_default(), name


def test_no_ledger_function_defaults_the_rate_to_a_number():
    for name, fn in inspect.getmembers(ledger_service, inspect.isfunction):
        if fn.__module__ != ledger_service.__name__:
            continue
        for pname in ('fx_rate_to_zar', 'fx_source'):
            param = inspect.signature(fn).parameters.get(pname)
            if param is not None:
                assert param.default in (inspect.Parameter.empty, None), f'{name}({pname}) has default {param.default!r}'


# ---- wrappers take the captured snapshot or refuse --------------------------------------------------------------

def test_capture_without_a_snapshot_raises(booking, student_user):
    tx = _tx(booking)
    with pytest.raises(MissingLedgerFx):
        record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)
    assert LedgerEntry.objects.count() == 0


def test_capture_uses_the_transaction_snapshot_not_a_constant(booking, student_user):
    tx = _tx(booking, fx_rate_to_zar=Decimal('17.000000'), fx_source='capture_test')
    entries = record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)
    assert {e.fx_rate_to_zar for e in entries} == {Decimal('17.000000')}
    assert {e.fx_source for e in entries} == {'capture_test'}
    assert {e.amount_zar for e in entries} == {Decimal('153.00')}


def test_capture_with_the_catalog_rate_is_valued_at_that_rate(booking, student_user):
    tx = _tx(booking)
    rate, source = persist_capture_snapshot(tx)
    assert rate == usd_to_zar_rate()
    entries = record_payment_capture_entry(payment_transaction=tx, booking=booking, user=student_user)
    assert {e.amount_zar for e in entries} == {(Decimal('9.00') * rate).quantize(Decimal('0.01'))}
    assert {e.fx_source for e in entries} == {source}


@pytest.mark.parametrize('post', [record_def501_quarantine_entry, record_unallocated_payment_entry])
def test_quarantine_and_unallocated_without_a_snapshot_raise(booking, student_user, post):
    tx = _tx(booking)
    with pytest.raises(MissingLedgerFx):
        post(payment_transaction=tx, booking=booking, user=student_user)
    assert LedgerEntry.objects.count() == 0


@pytest.mark.parametrize('post', [record_def501_quarantine_entry, record_unallocated_payment_entry])
def test_quarantine_and_unallocated_use_the_snapshot(booking, student_user, post):
    tx = _tx(booking, fx_rate_to_zar=Decimal('16.500000'), fx_source='capture_test')
    entries = post(payment_transaction=tx, booking=booking, user=student_user)
    assert {e.fx_rate_to_zar for e in entries} == {Decimal('16.500000')}
    assert {e.fx_source for e in entries} == {'capture_test'}


def test_explicit_compensation_amount_needs_an_explicit_rate(student_user):
    with pytest.raises(MissingLedgerFx):
        record_compensation_entry(user=student_user, amount_usd=Decimal('9.00'), reason='x')
    assert LedgerEntry.objects.count() == 0
    entries = record_compensation_entry(user=student_user, amount_usd=Decimal('9.00'), reason='x',
                                        fx_rate_to_zar=usd_to_zar_rate(), fx_source='price_catalog')
    assert {e.fx_source for e in entries} == {'price_catalog'}


def test_funded_compensation_takes_the_rate_from_the_booking_funding(booking, student_user):
    tx = _tx(booking, fx_rate_to_zar=Decimal('17.000000'), fx_source='capture_test')
    funding = ensure_gateway_funding(tx, booking)
    entries = record_compensation_entry(user=student_user, booking=booking, reason='funded')
    assert {e.fx_rate_to_zar for e in entries} == {funding.fx_rate_to_zar} == {Decimal('17.000000')}


# ---- every flow still posts balanced entries with a recorded source ---------------------------------------------

def test_no_flow_leaves_a_legacy_default_row():
    assert not LedgerEntry.objects.filter(fx_source='legacy_default').exists()
    assert payment_models.LedgerEntry._meta.get_field('fx_source').has_default() is False
