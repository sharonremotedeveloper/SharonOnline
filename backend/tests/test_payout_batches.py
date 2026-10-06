"""
Slices P1a-c (ADR-0003): payout batches. The properties that protect money:

  * a tutor is in at most one open batch (the database says so),
  * the person who made a batch can neither approve nor process it,
  * bank details are re-compared before approval and export, and only the CSV export ever decrypts them,
  * marking a batch processed posts one balanced DR 2020 / CR 1030 journal per tutor, exactly once.
"""
import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from rest_framework.test import APIClient

import factories as f
from apps.admin_api.models import PayoutAttempt, PayoutBatch, PayoutBatchLine, PayoutExportAudit
from apps.common import clock
from apps.payments.models import LedgerAccount, LedgerEntry, TutorPayoutAccount
from apps.payments.services import payout_batches as svc
from apps.payments.services.ledger_service import record_journal_entries
from apps.payments.services.payout_crypto import encrypt_payout_payload
from apps.payments.services.payable import payable_balance_zar

pytestmark = pytest.mark.django_db

PASSWORD = 'password123'
BATCHES = '/api/v1/admin/payouts/batches/'


@pytest.fixture(autouse=True)
def payout_keys(settings, frozen_clock):
    settings.PAYOUT_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
    settings.PAYOUT_DATA_ACTIVE_KEY = 'v1'
    settings.PAYOUT_MIN_ZAR = Decimal('100')
    settings.PAYOUT_BANK_CHANGE_HOLD_HOURS = 72
    frozen_clock.set(clock.now() + timedelta(days=30))        # every account below is "set up" long before the batch
    return settings


def bank_account(user, *, holder='Test Tutor', number='1234567890', bank='Capitec Bank', branch='470010', age_hours=24 * 30):
    payload = {'account_holder_name': holder, 'account_number': number, 'bank_name': bank, 'branch_code': branch,
               'account_type': 'savings'}
    ciphertext, version = encrypt_payout_payload(payload)
    account, _ = TutorPayoutAccount.objects.update_or_create(tutor=user, defaults={
        'encrypted_payload': ciphertext, 'key_version': version, 'account_last_four': number[-4:]})
    TutorPayoutAccount.objects.filter(pk=account.pk).update(updated_at=clock.now() - timedelta(hours=age_hours))
    account.refresh_from_db()
    return account


def owed(tutor, amount, *, with_account=True, **account_kwargs):
    """A tutor with `amount` ZAR cleared on ledger 2020 (and a bank account unless told otherwise)."""
    record_journal_entries(
        entries=[{'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'debit', 'amount': Decimal(amount)},
                 {'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE, 'entry_type': 'credit', 'amount': Decimal(amount)}],
        event_type=LedgerEntry.EventType.ESCROW_CLEARED, description='test earnings', user=tutor.user, currency='ZAR',
        fx_rate_to_zar=Decimal('1'), fx_source='transaction_currency')
    if with_account:
        bank_account(tutor.user, **account_kwargs)
    return tutor


def tutor(**fields):
    return f.make_teacher_profile(**fields)


@pytest.fixture
def maker(db):
    return f.make_admin()


@pytest.fixture
def checker(db):
    return f.make_admin()


def full_run(maker, checker, *, batch=None):
    batch = batch or svc.create_batch(actor=maker)[0]
    svc.approve_batch(batch.id, actor=checker)
    svc.export_batch(batch.id, actor=checker)
    return svc.mark_processed(batch.id, actor=checker)


# ------------------------------------------------------------------ P1a: building a batch
class TestCreateBatch:
    def test_pays_each_tutors_cleared_balance_and_totals_the_batch(self, maker):
        one, two = owed(tutor(), '250.50'), owed(tutor(), '400.00')
        batch, carried = svc.create_batch(actor=maker)
        assert batch.status == 'pending' and batch.created_by == maker and carried == 0
        assert {line.teacher_id: line.amount_zar for line in batch.lines.all()} == {one.id: Decimal('250.50'), two.id: Decimal('400.00')}
        assert (batch.total_payout_zar, batch.recipients_count) == (Decimal('650.50'), 2)
        assert all(line.is_open and line.status == 'pending' for line in batch.lines.all())

    def test_a_suspended_tutor_is_still_paid_what_they_earned(self, maker):
        gone = owed(tutor(status='suspended'), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        assert batch.lines.get().teacher_id == gone.id

    def test_a_balance_under_the_minimum_carries_over_and_is_not_a_line(self, maker):
        owed(tutor(), '99.99')
        paid = owed(tutor(), '100.00')
        batch, carried = svc.create_batch(actor=maker)
        assert [line.teacher_id for line in batch.lines.all()] == [paid.id] and carried == 1

    def test_no_bank_account_no_balance_and_nothing_owed_make_no_line(self, maker):
        owed(tutor(), '500.00', with_account=False)
        tutor()
        with pytest.raises(svc.PayoutError) as err:
            svc.create_batch(actor=maker)
        assert err.value.code == 'nothing_to_pay'
        assert PayoutBatch.objects.count() == 0

    def test_an_unreadable_bank_account_is_a_visible_skipped_line_not_a_silent_drop(self, maker, settings):
        broken = owed(tutor(), '500.00')
        good = owed(tutor(), '200.00')
        TutorPayoutAccount.objects.filter(tutor=broken.user).update(key_version='retired-key')
        batch, _ = svc.create_batch(actor=maker)
        skipped = batch.lines.get(teacher=broken)
        assert (skipped.status, skipped.skip_reason, skipped.is_open) == ('skipped', 'bank_details_unreadable', False)
        assert batch.lines.get(teacher=good).status == 'pending'
        assert (batch.total_payout_zar, batch.recipients_count) == (Decimal('200.00'), 1)

    def test_recently_changed_bank_details_hold_the_payout(self, maker):
        fresh = owed(tutor(), '500.00', age_hours=71)
        settled = owed(tutor(), '500.00', age_hours=73)
        batch, _ = svc.create_batch(actor=maker)
        assert (batch.lines.get(teacher=fresh).status, batch.lines.get(teacher=fresh).skip_reason) == (
            'skipped', 'bank_details_changed_recently')
        assert batch.lines.get(teacher=settled).status == 'pending'


# ------------------------------------------------------------------ P1a: no double pay
class TestNoDoublePay:
    def test_a_tutor_already_in_an_open_batch_is_not_put_in_another(self, maker):
        t = owed(tutor(), '300.00')
        first, _ = svc.create_batch(actor=maker)
        owed(t, '400.00', with_account=False)                 # more earnings arrive while the first batch is open
        with pytest.raises(svc.PayoutError) as err:
            svc.create_batch(actor=maker)
        assert err.value.code == 'nothing_to_pay'
        assert PayoutBatchLine.objects.filter(teacher=t, is_open=True).count() == 1

    def test_the_database_refuses_a_second_open_line_for_one_tutor(self, maker):
        t = owed(tutor(), '300.00')
        svc.create_batch(actor=maker)
        other = PayoutBatch.objects.create(batch_reference='PB-OTHER', created_by=maker)
        with pytest.raises(IntegrityError), transaction.atomic():
            PayoutBatchLine.objects.create(batch=other, teacher=t, amount_zar=Decimal('1.00'), is_open=True)

    def test_closed_lines_do_not_count_so_a_tutor_is_paid_again_next_run(self, maker, checker):
        t = owed(tutor(), '300.00')
        full_run(maker, checker)
        owed(t, '150.00', with_account=False)
        second, _ = svc.create_batch(actor=maker)
        assert second.lines.get().amount_zar == Decimal('150.00')

    def test_cancelling_releases_the_tutors_money_for_the_next_batch(self, maker):
        t = owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.cancel_batch(batch.id, actor=maker, reason='wrong cut-off')
        batch.refresh_from_db()
        assert batch.status == 'cancelled' and not batch.lines.filter(is_open=True).exists()
        assert svc.create_batch(actor=maker)[0].lines.get().teacher_id == t.id


# ------------------------------------------------------------------ P1a: state machine and maker-checker
class TestStateMachineAndMakerChecker:
    def test_the_creator_cannot_approve_their_own_batch(self, maker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        with pytest.raises(svc.PayoutError) as err:
            svc.approve_batch(batch.id, actor=maker)
        assert err.value.code == 'maker_checker_violation'
        batch.refresh_from_db()
        assert batch.status == 'pending'

    def test_the_creator_cannot_mark_it_processed_even_if_someone_else_approved(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=maker)
        with pytest.raises(svc.PayoutError) as err:
            svc.mark_processed(batch.id, actor=maker)
        assert err.value.code == 'maker_checker_violation'
        assert not LedgerEntry.objects.filter(event_type='payout_executed').exists()

    def test_steps_must_happen_in_order(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        for step in (lambda: svc.export_batch(batch.id, actor=checker), lambda: svc.mark_processed(batch.id, actor=checker)):
            with pytest.raises(svc.PayoutError) as err:
                step()
            assert err.value.code == 'invalid_state'
        svc.approve_batch(batch.id, actor=checker)
        with pytest.raises(svc.PayoutError) as err:
            svc.approve_batch(batch.id, actor=checker)
        assert err.value.code == 'invalid_state'
        with pytest.raises(svc.PayoutError) as err:
            svc.mark_processed(batch.id, actor=checker)             # approved but never exported
        assert err.value.code == 'invalid_state'

    def test_a_batch_can_be_cancelled_only_before_it_is_exported(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=checker)
        with pytest.raises(svc.PayoutError) as err:
            svc.cancel_batch(batch.id, actor=maker, reason='too late')
        assert err.value.code == 'invalid_state'

    def test_statuses_and_actors_are_recorded(self, maker, checker):
        owed(tutor(), '300.00')
        batch = full_run(maker, checker)
        assert (batch.status, batch.created_by, batch.approved_by, batch.exported_by, batch.executed_by) == (
            'processed', maker, checker, checker, checker)
        assert batch.approved_at and batch.exported_at and batch.executed_at


# ------------------------------------------------------------------ P1a: re-checks before money is committed
class TestRechecks:
    def test_approve_skips_a_line_whose_balance_was_reversed_since(self, maker, checker):
        t = owed(tutor(), '300.00')
        keep = owed(tutor(), '200.00')
        batch, _ = svc.create_batch(actor=maker)
        record_journal_entries(
            entries=[{'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE, 'entry_type': 'debit', 'amount': Decimal('250.00')},
                     {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'credit', 'amount': Decimal('250.00')}],
            event_type=LedgerEntry.EventType.DISPUTE_RESOLVED, description='clawback', user=t.user, currency='ZAR',
            fx_rate_to_zar=Decimal('1'), fx_source='transaction_currency')
        batch = svc.approve_batch(batch.id, actor=checker)
        line = batch.lines.get(teacher=t)
        assert (line.status, line.skip_reason, line.is_open) == ('skipped', 'balance_insufficient', False)
        assert batch.lines.get(teacher=keep).status == 'approved'
        assert (batch.total_payout_zar, batch.recipients_count) == (Decimal('200.00'), 1)
        assert PayoutAttempt.objects.filter(line=line, status='failed').exists()

    def test_approve_skips_a_line_whose_bank_details_changed_after_the_batch_was_made(self, maker, checker):
        t = owed(tutor(), '300.00')
        owed(tutor(), '200.00')
        batch, _ = svc.create_batch(actor=maker)
        bank_account(t.user, number='999988887777')
        batch = svc.approve_batch(batch.id, actor=checker)
        assert batch.lines.get(teacher=t).skip_reason == 'bank_details_changed'
        assert batch.recipients_count == 1

    def test_export_rechecks_bank_details_too_and_never_exports_a_changed_account(self, maker, checker):
        t = owed(tutor(), '300.00')
        owed(tutor(), '200.00', number='5555666677')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        bank_account(t.user, number='111122223333')
        _batch, content, _rows = svc.export_batch(batch.id, actor=checker)
        assert '111122223333' not in content and '1234567890' not in content and '5555666677' in content
        assert batch.lines.get(teacher=t).skip_reason == 'bank_details_changed'

    def test_approving_when_nothing_payable_remains_is_refused(self, maker, checker):
        t = owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        bank_account(t.user, number='111122223333')
        with pytest.raises(svc.PayoutError) as err:
            svc.approve_batch(batch.id, actor=checker)
        assert err.value.code == 'no_payable_lines'
        batch.refresh_from_db()
        assert batch.status == 'pending' and batch.lines.get().status == 'skipped'

    def test_mark_processed_refuses_when_a_balance_no_longer_covers_its_line_and_posts_nothing(self, maker, checker):
        t = owed(tutor(), '300.00')
        owed(tutor(), '200.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=checker)
        record_journal_entries(
            entries=[{'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE, 'entry_type': 'debit', 'amount': Decimal('250.00')},
                     {'account': LedgerAccount.LIABILITY_STUDENT_ESCROW, 'entry_type': 'credit', 'amount': Decimal('250.00')}],
            event_type=LedgerEntry.EventType.DISPUTE_RESOLVED, description='clawback', user=t.user, currency='ZAR',
            fx_rate_to_zar=Decimal('1'), fx_source='transaction_currency')
        with pytest.raises(svc.PayoutError) as err:
            svc.mark_processed(batch.id, actor=checker)
        assert err.value.code == 'balance_changed'
        assert not LedgerEntry.objects.filter(event_type='payout_executed').exists()
        batch.refresh_from_db()
        assert batch.status == 'exported'


# ------------------------------------------------------------------ P1b: the bank file
class TestExport:
    def test_csv_has_one_row_per_paid_line_with_bank_details_and_exact_amounts(self, maker, checker):
        owed(tutor(), '250.50', holder='Thandi Dlamini', number='1234567890', bank='Capitec Bank', branch='470010')
        owed(tutor(), '400.00', holder='Pieter Botha', number='9876543210', bank='Nedbank', branch='198765')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        _b, content, rows = svc.export_batch(batch.id, actor=checker)
        parsed = list(csv.DictReader(io.StringIO(content)))
        assert rows == 2 and len(parsed) == 2
        by_name = {row['Beneficiary Name']: row for row in parsed}
        thandi = by_name['Thandi Dlamini']
        assert (thandi['Account Number'], thandi['Branch Code'], thandi['Amount (ZAR)'], thandi['Bank']) == (
            '1234567890', '470010', '250.50', 'Capitec Bank')
        assert by_name['Pieter Botha']['Branch Code'] == '198765'
        assert batch.batch_reference in thandi['Own Reference']

    def test_cells_that_could_run_as_spreadsheet_formulas_are_defused(self, maker, checker):
        owed(tutor(), '300.00', holder="=HYPERLINK(\"http://evil.example\",\"x\")")
        owed(tutor(), '300.00', holder='+1+1')
        owed(tutor(), '300.00', holder='-2+3')
        owed(tutor(), '300.00', holder='@SUM(A1)')
        owed(tutor(), '300.00', holder=' =padded')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        _b, content, _rows = svc.export_batch(batch.id, actor=checker)
        names = [row['Beneficiary Name'] for row in csv.DictReader(io.StringIO(content))]
        assert len(names) == 5 and all(name.startswith("'") for name in names), names

    def test_every_download_is_audited_with_a_hash_of_what_was_handed_out(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=maker)                       # a re-download is allowed, and audited again
        audits = PayoutExportAudit.objects.filter(batch=batch).order_by('created_at')
        assert [a.actor_id for a in audits] == [checker.id, maker.id] and all(a.row_count == 1 for a in audits)
        import hashlib
        _b, content, _r = svc.export_batch(batch.id, actor=checker)
        assert PayoutExportAudit.objects.filter(batch=batch).latest('created_at').content_sha256 == hashlib.sha256(
            content.encode('utf-8')).hexdigest()

    def test_export_marks_the_batch_and_lines_exported_and_needs_an_approved_batch(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        with pytest.raises(svc.PayoutError) as err:
            svc.export_batch(batch.id, actor=checker)
        assert err.value.code == 'invalid_state'
        assert not PayoutExportAudit.objects.exists()
        svc.approve_batch(batch.id, actor=checker)
        batch, _content, _rows = svc.export_batch(batch.id, actor=checker)
        assert batch.status == 'exported' and batch.lines.get().status == 'exported'

    def test_only_the_export_module_decrypts_bank_details(self):
        """Guard (ADR-0003 point 4): decrypting a payout payload is allowed in exactly these modules; the list may only shrink."""
        from pathlib import Path
        apps = Path(__file__).resolve().parent.parent / 'apps'
        importers = {str(p.relative_to(apps)).replace('\\', '/') for p in apps.rglob('*.py')
                     if 'decrypt_payout_payload' in p.read_text(encoding='utf-8')}
        assert importers <= {'payments/services/payout_crypto.py', 'payments/serializers.py',
                             'payments/services/payout_export.py'}, importers


# ------------------------------------------------------------------ P1c: the ledger
class TestSettlement:
    def test_processing_posts_one_balanced_journal_per_tutor_and_pays_the_balance_down(self, maker, checker):
        one, two = owed(tutor(), '250.50'), owed(tutor(), '400.00')
        batch = full_run(maker, checker)
        entries = LedgerEntry.objects.filter(payout_batch=batch)
        assert entries.count() == 4 and entries.filter(event_type='payout_executed').count() == 4
        for t, amount in ((one, '250.50'), (two, '400.00')):
            mine = entries.filter(user=t.user)
            debit, credit = mine.get(entry_type='debit'), mine.get(entry_type='credit')
            assert (debit.account, credit.account) == (LedgerAccount.LIABILITY_TUTOR_PAYABLE, LedgerAccount.ASSET_OPERATING_BANK)
            assert debit.amount == credit.amount == Decimal(amount) and debit.currency == credit.currency == 'ZAR'
            assert debit.journal_batch_id == credit.journal_batch_id
            assert payable_balance_zar(t.user) == Decimal('0.00')
        totals = entries.aggregate(d=Sum('amount_zar', filter=Q(entry_type='debit')), c=Sum('amount_zar', filter=Q(entry_type='credit')))
        assert totals['d'] == totals['c'] == Decimal('650.50')
        assert all(line.status == 'paid' and not line.is_open and line.paid_at for line in batch.lines.all())
        assert PayoutAttempt.objects.filter(status='succeeded').count() == 2

    def test_marking_it_processed_twice_posts_nothing_the_second_time(self, maker, checker):
        owed(tutor(), '300.00')
        batch = full_run(maker, checker)
        count = LedgerEntry.objects.count()
        again = svc.mark_processed(batch.id, actor=maker)             # even by the maker: a no-op returns before any check
        assert again.status == 'processed' and LedgerEntry.objects.count() == count

    def test_the_database_backstops_a_replayed_posting(self, maker, checker):
        t = owed(tutor(), '300.00')
        batch = full_run(maker, checker)
        from apps.payments.services.ledger_service import record_payout_batch_entry
        with pytest.raises(IntegrityError), transaction.atomic():
            record_payout_batch_entry(batch, Decimal('300.00'), user=t.user)

    def test_one_bad_line_rolls_back_every_journal_in_the_batch(self, maker, checker, monkeypatch):
        owed(tutor(), '300.00')
        owed(tutor(), '200.00')
        batch, _ = svc.create_batch(actor=maker)
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=checker)
        real = svc.record_payout_batch_entry
        calls = []

        def second_one_fails(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('ledger down')
            return real(*args, **kwargs)

        monkeypatch.setattr(svc, 'record_payout_batch_entry', second_one_fails)
        with pytest.raises(RuntimeError):
            svc.mark_processed(batch.id, actor=checker)
        assert not LedgerEntry.objects.filter(payout_batch=batch).exists()
        batch.refresh_from_db()
        assert batch.status == 'exported' and not batch.lines.filter(status='paid').exists()

    def test_a_skipped_tutor_is_not_paid_and_keeps_their_balance(self, maker, checker):
        t = owed(tutor(), '300.00')
        other = owed(tutor(), '200.00')
        batch, _ = svc.create_batch(actor=maker)
        bank_account(t.user, number='111122223333')
        svc.approve_batch(batch.id, actor=checker)
        svc.export_batch(batch.id, actor=checker)
        svc.mark_processed(batch.id, actor=checker)
        assert payable_balance_zar(t.user) == Decimal('300.00') and payable_balance_zar(other.user) == Decimal('0.00')

    def test_a_bank_return_reverses_the_payout_and_frees_the_tutor_for_the_next_run(self, maker, checker):
        t = owed(tutor(), '300.00')
        batch = full_run(maker, checker)
        line = batch.lines.get()
        svc.return_line(line.id, actor=checker, reason='account closed')
        line.refresh_from_db()
        assert (line.status, line.is_open, line.return_reason) == ('returned', False, 'account closed')
        reversal = LedgerEntry.objects.filter(payout_batch=batch, event_type='payout_returned')
        assert reversal.get(entry_type='debit').account == LedgerAccount.ASSET_OPERATING_BANK
        assert reversal.get(entry_type='credit').account == LedgerAccount.LIABILITY_TUTOR_PAYABLE
        assert payable_balance_zar(t.user) == Decimal('300.00')
        assert PayoutAttempt.objects.filter(line=line, status='returned').exists()
        with pytest.raises(svc.PayoutError) as err:
            svc.return_line(line.id, actor=checker, reason='again')
        assert err.value.code == 'invalid_state'

    def test_a_line_that_was_never_paid_cannot_be_returned(self, maker, checker):
        owed(tutor(), '300.00')
        batch, _ = svc.create_batch(actor=maker)
        with pytest.raises(svc.PayoutError) as err:
            svc.return_line(batch.lines.get().id, actor=checker, reason='nope')
        assert err.value.code == 'invalid_state'

    def test_the_wallet_shows_the_payout(self, maker, checker):
        from apps.payments.services.tutor_wallet import tutor_wallet_payload
        t = owed(tutor(), '300.00')
        full_run(maker, checker)
        wallet = tutor_wallet_payload(t.user)
        assert wallet['cleared_balance_zar'] == Decimal('0.00')
        assert [row['status'] for row in wallet['transactions']] == ['paid_out']


# ------------------------------------------------------------------ the API
def admin_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TestApi:
    def test_the_whole_flow_over_http(self, maker, checker):
        t = owed(tutor(), '300.00')
        created = admin_client(maker).post(BATCHES, {}, format='json')
        assert created.status_code == 201, created.content
        body = created.json()
        batch_id = body['id']
        assert body['status'] == 'pending' and body['total_payout_zar'] == '300.00' and body['carried_over_count'] == 0
        assert body['lines'][0]['teacher_id'] == str(t.id) and body['lines'][0]['amount_zar'] == '300.00'
        assert '1234567890' not in created.content.decode()                 # bank numbers never travel in the JSON

        assert admin_client(maker).post(f'{BATCHES}{batch_id}/approve/').status_code == 403
        assert admin_client(checker).post(f'{BATCHES}{batch_id}/approve/').json()['status'] == 'approved'

        assert admin_client(checker).post(f'{BATCHES}{batch_id}/export/', {'password': 'wrong'}, format='json').status_code == 403
        assert not PayoutExportAudit.objects.exists()
        exported = admin_client(checker).post(f'{BATCHES}{batch_id}/export/', {'password': PASSWORD}, format='json')
        assert exported.status_code == 200 and exported['Content-Type'].startswith('text/csv')
        assert 'no-store' in exported['Cache-Control'] and 'attachment' in exported['Content-Disposition']
        assert b'1234567890' in exported.content
        assert PayoutExportAudit.objects.count() == 1

        assert admin_client(maker).post(f'{BATCHES}{batch_id}/mark-processed/').status_code == 403
        processed = admin_client(checker).post(f'{BATCHES}{batch_id}/mark-processed/')
        assert processed.status_code == 200 and processed.json()['status'] == 'processed'
        assert admin_client(checker).get(f'{BATCHES}{batch_id}/').json()['lines'][0]['status'] == 'paid'
        assert [b['id'] for b in admin_client(checker).get(BATCHES).json()] == [batch_id]

    def test_errors_map_to_codes(self, maker, checker):
        assert admin_client(maker).post(BATCHES, {}, format='json').json()['code'] == 'nothing_to_pay'
        assert admin_client(maker).post(f'{BATCHES}{"00000000-0000-0000-0000-000000000000"}/approve/').status_code == 404
        owed(tutor(), '300.00')
        batch_id = admin_client(maker).post(BATCHES, {}, format='json').json()['id']
        assert admin_client(checker).post(f'{BATCHES}{batch_id}/mark-processed/').json()['code'] == 'invalid_state'
        assert admin_client(maker).post(f'{BATCHES}{batch_id}/approve/').json()['code'] == 'maker_checker_violation'

    def test_cancel_and_return_endpoints(self, maker, checker):
        owed(tutor(), '300.00')
        batch_id = admin_client(maker).post(BATCHES, {}, format='json').json()['id']
        cancelled = admin_client(maker).post(f'{BATCHES}{batch_id}/cancel/', {'reason': 'wrong cut-off'}, format='json')
        assert cancelled.json()['status'] == 'cancelled'
        owed_batch = full_run(maker, checker, batch=svc.create_batch(actor=maker)[0])
        line_id = owed_batch.lines.get().id
        returned = admin_client(checker).post(f'/api/v1/admin/payouts/batch-lines/{line_id}/return/',
                                              {'reason': 'account closed'}, format='json')
        assert returned.status_code == 200 and returned.json()['status'] == 'returned'

    def test_only_platform_admins_may_use_it(self, student_user, teacher_user, maker):
        batch = PayoutBatch.objects.create(batch_reference='PB-X', created_by=maker)
        for user in (student_user, teacher_user.user):
            client = admin_client(user)
            assert client.get(BATCHES).status_code == 403
            assert client.post(BATCHES, {}, format='json').status_code == 403
            for action in ('approve', 'export', 'mark-processed', 'cancel'):
                assert client.post(f'{BATCHES}{batch.id}/{action}/', {}, format='json').status_code == 403
        assert APIClient().get(BATCHES).status_code == 401

    def test_the_legacy_execute_endpoint_stays_disabled(self, maker):
        assert admin_client(maker).post('/api/v1/admin/payouts/execute-batch/').status_code == 503
