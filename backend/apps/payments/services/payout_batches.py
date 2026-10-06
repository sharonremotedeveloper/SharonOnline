"""
Payout batches (slices P1a-c, docs/adr/ADR-0003-payout-batches.md).

    create_batch -> approve_batch -> export_batch -> mark_processed        (cancel_batch before export; return_line after)

Rules that protect the money, each with a test in tests/test_payout_batches.py:
  * a tutor is in at most one open batch (partial unique constraint on PayoutBatchLine.is_open),
  * the batch's creator may not approve or process it (maker-checker, not a setting),
  * the bank account is re-compared with the one the line was built from at approve and export,
  * the ledger balance is re-checked at approve and again at processing,
  * processing is one atomic transaction that posts DR 2020 / CR 1030 once per tutor and is a no-op when repeated.
"""
import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction

from apps.admin_api.models import PayoutAttempt, PayoutBatch, PayoutBatchLine, PayoutExportAudit
from apps.common import clock
from apps.payments.serializers import masked_payout_account
from apps.payments.services.ledger_service import record_payout_batch_entry, record_payout_return_entry
from apps.payments.services.payable import available_balance_zar, payable_balance_zar
from apps.payments.services.payout_crypto import PayoutDataError
from apps.payments.services.payout_export import build_csv
from apps.teachers.models import TeacherProfile
from apps.users.models import User

Line, Batch = PayoutBatchLine.Status, PayoutBatch.Status
OPEN_BEFORE_EXPORT = (Line.PENDING, Line.APPROVED)


class PayoutError(Exception):
    """A refused payout action. `code` is stable (the API returns it); `lines` lists the lines that caused it."""

    def __init__(self, code: str, message: str, *, lines=()):
        super().__init__(message)
        self.code, self.message, self.lines = code, message, list(lines)


def _fingerprint(account) -> str:
    return hashlib.sha256(account.encrypted_payload.encode('ascii')).hexdigest()


def _lock_batch(batch_id) -> PayoutBatch:
    try:
        return PayoutBatch.objects.select_for_update().get(pk=batch_id)
    except PayoutBatch.DoesNotExist:
        raise PayoutError('not_found', 'No such payout batch.') from None


def _lock_tutor(user_id) -> User:
    """Serialises everything that spends one tutor's balance (batch building, approval, processing)."""
    return User.objects.select_for_update().get(pk=user_id)


def _require_other_person(batch: PayoutBatch, actor, action: str):
    if batch.created_by_id is not None and batch.created_by_id == actor.pk:
        raise PayoutError('maker_checker_violation', f'The person who created a payout batch cannot {action} it.')


def _attempt(line, actor, status, message=''):
    PayoutAttempt.objects.create(line=line, initiated_by=actor, status=status, error_message=message[:255])


def _skip(line, actor, reason: str):
    line.status, line.is_open, line.skip_reason = Line.SKIPPED, False, reason
    line.save(update_fields=['status', 'is_open', 'skip_reason'])
    _attempt(line, actor, PayoutAttempt.Status.FAILED, reason)


def _refresh_totals(batch: PayoutBatch):
    live = batch.lines.exclude(status__in=(Line.SKIPPED, Line.CANCELLED))
    batch.recipients_count = live.count()
    batch.total_payout_zar = sum((line.amount_zar for line in live), Decimal('0.00'))


# ------------------------------------------------------------------ create
def _bank_problem(account, now) -> str:
    """Why this tutor cannot be paid in this run, or '' when they can."""
    try:
        masked_payout_account(account)
    except (PayoutDataError, ImproperlyConfigured):
        return 'bank_details_unreadable'
    if now - account.updated_at < timedelta(hours=settings.PAYOUT_BANK_CHANGE_HOLD_HOURS):
        return 'bank_details_changed_recently'
    return ''


@transaction.atomic
def create_batch(*, actor, now=None):
    """
    A pending batch for every tutor who has a bank account, is owed at least PAYOUT_MIN_ZAR and is not already in an open batch.
    Not filtered by tutor status: a suspended or removed tutor is paid what they earned. Returns (batch, carried_over_count).
    """
    now = now or clock.now()
    minimum = Decimal(str(settings.PAYOUT_MIN_ZAR))
    decisions, carried = [], 0
    candidates = TeacherProfile.objects.filter(user__payout_account__isnull=False).select_related('user', 'user__payout_account')
    for teacher in candidates.order_by('id'):
        _lock_tutor(teacher.user_id)
        if PayoutBatchLine.objects.filter(teacher=teacher, is_open=True).exists():
            continue                                    # their money is already committed to another open batch
        owed = available_balance_zar(teacher.user)
        if owed <= 0:
            continue
        if owed < minimum:
            carried += 1
            continue
        account = teacher.user.payout_account
        decisions.append((teacher, owed, account, _bank_problem(account, now)))
    if not decisions:
        raise PayoutError('nothing_to_pay', 'No tutor is owed a payable balance that is not already in an open batch.')

    batch = PayoutBatch.objects.create(
        batch_reference=f'PB-{now:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}', created_by=actor)
    for teacher, owed, account, problem in decisions:
        PayoutBatchLine.objects.create(
            batch=batch, teacher=teacher, amount_zar=owed, account_fingerprint=_fingerprint(account),
            account_last_four=account.account_last_four,
            status=Line.SKIPPED if problem else Line.PENDING, is_open=not problem, skip_reason=problem)
    _refresh_totals(batch)
    batch.save(update_fields=['recipients_count', 'total_payout_zar'])
    return batch, carried


# ------------------------------------------------------------------ re-checks (approve, export)
def _recheck(batch: PayoutBatch, actor, statuses, *, with_balance: bool) -> list:
    """Skip (visibly, with a reason) every open line whose bank account changed or whose balance no longer covers it."""
    remaining = []
    for line in batch.lines.select_related('teacher__user').filter(status__in=statuses, is_open=True):
        _lock_tutor(line.teacher.user_id)
        account = getattr(line.teacher.user, 'payout_account', None)
        if account is None or _fingerprint(account) != line.account_fingerprint:
            _skip(line, actor, 'bank_details_changed')
        elif with_balance and payable_balance_zar(line.teacher.user) < line.amount_zar:
            _skip(line, actor, 'balance_insufficient')
        else:
            remaining.append(line)
    _refresh_totals(batch)
    batch.save(update_fields=['recipients_count', 'total_payout_zar'])
    return remaining


def approve_batch(batch_id, *, actor, now=None) -> PayoutBatch:
    now = now or clock.now()
    with transaction.atomic():
        batch = _lock_batch(batch_id)
        if batch.status != Batch.PENDING:
            raise PayoutError('invalid_state', f'A {batch.status} batch cannot be approved.')
        _require_other_person(batch, actor, 'approve')
        remaining = _recheck(batch, actor, (Line.PENDING,), with_balance=True)
        if remaining:
            for line in remaining:
                line.status = Line.APPROVED
                line.save(update_fields=['status'])
            batch.status, batch.approved_by, batch.approved_at = Batch.APPROVED, actor, now
            batch.save(update_fields=['status', 'approved_by', 'approved_at'])
            return batch
    # Committed above: the skipped lines stay visible even though there is nothing left to approve.
    raise PayoutError('no_payable_lines', 'Every line failed its re-check; nothing is left to approve. Cancel this batch.')


def export_batch(batch_id, *, actor, now=None):
    """Re-check the accounts, build the bank CSV and audit the download. Returns (batch, csv_text, row_count)."""
    now = now or clock.now()
    with transaction.atomic():
        batch = _lock_batch(batch_id)
        if batch.status not in (Batch.APPROVED, Batch.EXPORTED):
            raise PayoutError('invalid_state', f'A {batch.status} batch cannot be exported.')
        remaining = _recheck(batch, actor, (Line.APPROVED, Line.EXPORTED), with_balance=False)
        if remaining:
            content = build_csv(batch, remaining)
            for line in remaining:
                if line.status != Line.EXPORTED:
                    line.status = Line.EXPORTED
                    line.save(update_fields=['status'])
            if batch.status != Batch.EXPORTED:
                batch.status, batch.exported_by, batch.exported_at = Batch.EXPORTED, actor, now
                batch.save(update_fields=['status', 'exported_by', 'exported_at'])
            PayoutExportAudit.objects.create(batch=batch, actor=actor, row_count=len(remaining),
                                             content_sha256=hashlib.sha256(content.encode('utf-8')).hexdigest())
            return batch, content, len(remaining)
    raise PayoutError('no_payable_lines', 'Every line failed its re-check; there is nothing to export. Cancel this batch.')


# ------------------------------------------------------------------ settle
def mark_processed(batch_id, *, actor, now=None) -> PayoutBatch:
    """The bank run is done: post DR 2020 / CR 1030 for every exported line, all or nothing. Repeating it changes nothing."""
    now = now or clock.now()
    with transaction.atomic():
        batch = _lock_batch(batch_id)
        if batch.status == Batch.PROCESSED:
            return batch
        if batch.status != Batch.EXPORTED:
            raise PayoutError('invalid_state', f'A {batch.status} batch cannot be marked processed.')
        _require_other_person(batch, actor, 'process')
        lines = list(batch.lines.select_related('teacher__user').filter(status=Line.EXPORTED, is_open=True))
        short = []
        for line in lines:
            _lock_tutor(line.teacher.user_id)
            if payable_balance_zar(line.teacher.user) < line.amount_zar:
                short.append(str(line.id))
        if short:
            raise PayoutError('balance_changed', 'A tutor balance no longer covers its line; nothing was posted.', lines=short)
        for line in lines:
            record_payout_batch_entry(batch, line.amount_zar, user=line.teacher.user,
                                      description=f'EFT payout {batch.batch_reference} to {line.teacher.user.username}')
            line.status, line.is_open, line.paid_at = Line.PAID, False, now
            line.save(update_fields=['status', 'is_open', 'paid_at'])
            _attempt(line, actor, PayoutAttempt.Status.SUCCEEDED)
        batch.status, batch.executed_by, batch.executed_at = Batch.PROCESSED, actor, now
        batch.save(update_fields=['status', 'executed_by', 'executed_at'])
        return batch


def cancel_batch(batch_id, *, actor, reason: str, now=None) -> PayoutBatch:
    now = now or clock.now()
    with transaction.atomic():
        batch = _lock_batch(batch_id)
        if batch.status not in (Batch.PENDING, Batch.APPROVED):
            raise PayoutError('invalid_state', f'A {batch.status} batch can no longer be cancelled.')
        batch.lines.filter(status__in=OPEN_BEFORE_EXPORT).update(status=Line.CANCELLED, is_open=False)
        batch.status, batch.cancelled_at, batch.cancel_reason = Batch.CANCELLED, now, reason[:255]
        _refresh_totals(batch)
        batch.save(update_fields=['status', 'cancelled_at', 'cancel_reason', 'recipients_count', 'total_payout_zar'])
        return batch


def return_line(line_id, *, actor, reason: str, now=None) -> PayoutBatchLine:
    """The bank sent a paid line back: reverse the payout in the ledger so the tutor is owed the money again."""
    now = now or clock.now()
    with transaction.atomic():
        line = PayoutBatchLine.objects.select_related('batch', 'teacher__user').filter(pk=line_id).first()
        if line is None:
            raise PayoutError('not_found', 'No such payout line.')
        batch = _lock_batch(line.batch_id)
        line = PayoutBatchLine.objects.select_for_update(of=('self',)).select_related('teacher__user').get(pk=line_id)
        if line.status != Line.PAID:
            raise PayoutError('invalid_state', f'A {line.status} line cannot be returned.')
        record_payout_return_entry(batch, line.amount_zar, user=line.teacher.user,
                                   description=f'EFT returned by the bank ({reason[:80]}), batch {batch.batch_reference}')
        line.status, line.returned_at, line.return_reason = Line.RETURNED, now, reason[:255]
        line.save(update_fields=['status', 'returned_at', 'return_reason'])
        _attempt(line, actor, PayoutAttempt.Status.RETURNED, reason)
        return line
