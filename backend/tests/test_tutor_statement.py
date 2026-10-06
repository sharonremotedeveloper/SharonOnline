"""Slice P2: the tutor statement CSV (ledger 2020 in ZAR with a running balance)."""
import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

import factories as f
from apps.common import clock
from apps.payments.models import LedgerAccount, LedgerEntry
from apps.payments.services import statements
from apps.payments.services.ledger_service import record_journal_entries

pytestmark = pytest.mark.django_db
URL = '/api/v1/payments/wallet/tutor/statement/'


def earn(tutor, amount, *, booking=None):
    return record_journal_entries(
        entries=[{'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'debit', 'amount': Decimal(amount)},
                 {'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE, 'entry_type': 'credit', 'amount': Decimal(amount)}],
        event_type=LedgerEntry.EventType.ESCROW_CLEARED, description='x', user=tutor.user, currency='ZAR',
        fx_rate_to_zar=Decimal('1'), fx_source='transaction_currency', booking=booking)


def pay_out(tutor, amount):
    from apps.admin_api.models import PayoutBatch
    from apps.payments.services.ledger_service import record_payout_batch_entry
    batch = PayoutBatch.objects.create(batch_reference='PB-TEST-1')
    return record_payout_batch_entry(batch, Decimal(amount), user=tutor.user)


def rows_of(response):
    return list(csv.reader(io.StringIO(response.content.decode('utf-8'))))


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_earnings_payouts_and_the_running_balance():
    tutor = f.make_teacher_profile()
    earn(tutor, '300.00', booking=f.make_booking(teacher=tutor, status='completed'))
    earn(tutor, '150.50')
    pay_out(tutor, '400.00')
    table = rows_of(client_for(tutor.user).get(URL))
    assert table[0] == statements.HEADER and table[1][1:] == ['Opening balance', '', '', '', '0.00']
    body = table[2:]
    # Rows created inside one clock tick have no defined order (ERR-193): assert the order-independent facts.
    assert sorted((r[1], r[3], r[4]) for r in body) == sorted([
        ('Lesson earnings', '300.00', '0.00'), ('Lesson earnings', '150.50', '0.00'),
        ('Payout to your bank account', '0.00', '400.00')])
    assert body[-1][5] == '50.50'
    assert {r[2] for r in body if r[1].startswith('Lesson')} >= {next(r[2] for r in body if r[2].startswith('BK-'))}
    assert 'PB-TEST-1' in {r[2] for r in body}


def test_a_date_range_carries_the_balance_in_and_out():
    tutor = f.make_teacher_profile()
    earn(tutor, '100.00')
    earn(tutor, '60.00')
    today = clock.now().date()
    after = rows_of(client_for(tutor.user).get(URL, {'from': (today + timedelta(days=1)).isoformat()}))
    assert after[1][5] == '160.00' and len(after) == 2                  # everything is before the range: opening only
    before = rows_of(client_for(tutor.user).get(URL, {'to': (today - timedelta(days=1)).isoformat()}))
    assert before[1][5] == '0.00' and len(before) == 2                  # nothing yet: opening 0, no rows
    inside = rows_of(client_for(tutor.user).get(URL, {'from': today.isoformat(), 'to': today.isoformat()}))
    # Two rows in one 15 ms clock tick have no defined order (ERR-193), so assert what is order-independent.
    assert sorted(r[3] for r in inside[2:]) == ['100.00', '60.00'] and inside[-1][5] == '160.00'


def test_a_tutor_only_sees_their_own_rows():
    mine, other = f.make_teacher_profile(), f.make_teacher_profile()
    earn(other, '999.00')
    table = rows_of(client_for(mine.user).get(URL))
    assert len(table) == 2 and table[1][5] == '0.00'


def test_bad_dates_are_a_400_and_nontutors_are_refused(student_user):
    tutor = f.make_teacher_profile()
    assert client_for(tutor.user).get(URL, {'from': 'yesterday'}).status_code == 400
    assert client_for(student_user).get(URL).status_code == 403
    assert APIClient().get(URL).status_code == 401


def test_response_is_a_private_download():
    tutor = f.make_teacher_profile()
    response = client_for(tutor.user).get(URL)
    assert response['Content-Type'].startswith('text/csv') and 'no-store' in response['Cache-Control']
    assert 'attachment' in response['Content-Disposition'] and date.today().year > 2000
