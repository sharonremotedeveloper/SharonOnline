"""
Task 10.7 final Architect review conditions (docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md 'Final review'):
Postgres-safe row locks on nullable foreign keys, a PayPal-safe invoice id after an epoch bump, the stale-submitted alert from
a failing poll, the production boot warning for Routing without PayPal credentials, and tests never reaching a real gateway.
"""
import json
import logging
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from apps.payments.models import GatewayAnomaly, RefundRequest
from apps.payments.services import refunds
from apps.payments.services.refund_gateways import RefundResult
from config.settings.guard import validate_production_settings
from payment_helpers import captured

DAY = timedelta(days=1)


# ---------- 1. Postgres: FOR UPDATE cannot lock the nullable side of an outer join ----------

# Superseded by the whole-tree AST guard (Q0): tests/guards/test_guard_select_for_update.py, which keeps PaymentTransaction at
# zero tolerance (test_payment_transaction_locks_are_never_allowlisted) and also catches multi-line chains and either order.


# ---------- 2. invoice id after an epoch bump ----------

def _refund(teacher_user, student_user, minute=900):
    booking = captured(teacher_user, student_user, minute, gateway='paypal', amount='9.00', currency='USD', ref='CAP-FINAL-1')
    return refunds.request_refund(booking, RefundRequest.Reason.STUDENT_CANCEL).refund


def test_invoice_id_is_the_refund_id_at_epoch_zero_and_suffixed_after_a_bump(teacher_user, student_user, settings):
    settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0
    r = _refund(teacher_user, student_user)
    claim = next(refunds.claim_due_refunds(limit=1))
    assert claim.order.invoice_id == str(r.pk)
    RefundRequest.objects.filter(pk=r.pk).update(claim_token='', claimed_until=None, next_attempt_at=None, request_epoch=2)
    claim = next(refunds.claim_due_refunds(limit=1))
    assert claim.order.invoice_id == f'{r.pk}-r2'
    assert len(claim.order.invoice_id) <= 127            # PayPal's invoice_id limit


# ---------- 3. a refund PayPal accepted but never finishes keeps alerting even when polls only fail ----------

def test_a_stale_submitted_refund_alerts_even_when_every_poll_is_transient(teacher_user, student_user, settings, monkeypatch):
    settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0

    class Gw:
        def refund(self, order):
            return RefundResult('submitted', reference='RF-STUCK-1')

        def lookup(self, order):
            return RefundResult('transient', detail='PayPal is down')

    monkeypatch.setattr(refunds, 'import_string', lambda path: Gw)
    settings.REFUND_GATEWAY_BACKEND = 'x.Gw'
    r = _refund(teacher_user, student_user, minute=960)
    refunds.process_pending_refunds()
    assert RefundRequest.objects.get(pk=r.pk).status == RefundRequest.Status.SUBMITTED
    later = timezone.now() + 15 * DAY
    monkeypatch.setattr(refunds, '_now', lambda: later)
    refunds.process_pending_refunds()
    assert GatewayAnomaly.objects.filter(reason='refund_submitted_stale', reference=str(r.pk), resolved=False).exists()


def test_a_young_submitted_refund_with_failing_polls_does_not_alert(teacher_user, student_user, settings, monkeypatch):
    settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0

    class Gw:
        def refund(self, order):
            return RefundResult('submitted', reference='RF-YOUNG-1')

        def lookup(self, order):
            return RefundResult('transient', detail='PayPal is down')

    monkeypatch.setattr(refunds, 'import_string', lambda path: Gw)
    settings.REFUND_GATEWAY_BACKEND = 'x.Gw'
    _refund(teacher_user, student_user, minute=1020)
    refunds.process_pending_refunds()
    later = timezone.now() + 2 * DAY
    monkeypatch.setattr(refunds, '_now', lambda: later)
    refunds.process_pending_refunds()
    assert not GatewayAnomaly.objects.filter(reason='refund_submitted_stale').exists()


# ---------- 4. tests never reach a real gateway by accident ----------

def test_the_test_environment_pins_the_manual_refund_backend(settings):
    assert settings.REFUND_GATEWAY_BACKEND.rsplit('.', 1)[-1] == 'ManualSandboxRefundGateway'


# ---------- 5. production on Routing with blank PayPal credentials is loud, not silent ----------

GOOD = {
    'DJANGO_SECRET_KEY': 'x' * 60, 'DJANGO_ALLOWED_HOSTS': 'api.sharonesl.com', 'CORS_ALLOWED_ORIGINS': 'https://sharonesl.com',
    'CSRF_TRUSTED_ORIGINS': 'https://sharonesl.com,https://api.sharonesl.com', 'ZOOM_WEBHOOK_SECRET_TOKEN': 'zoom-secret',
    'ESKOMSEPUSH_API_KEY': 'eskom-provider-key', 'THROTTLE_NUM_PROXIES': '1', 'FRONTEND_BASE_URL': 'https://sharonesl.com',
    'RESEND_API_KEY': 're_live_abcdefghijklmnop', 'PAYOUT_DATA_KEYS': json.dumps({'v1': Fernet.generate_key().decode()}),
    'PAYOUT_DATA_ACTIVE_KEY': 'v1', 'REFUND_GATEWAY_BACKEND': 'apps.payments.services.refund_gateways.RoutingRefundGateway',
    'ZOOM_ACCOUNT_ID': 'zoom-account', 'ZOOM_CLIENT_ID': 'zoom-client', 'ZOOM_CLIENT_SECRET': 'zoom-secret-value',  # Z1
}


def test_routing_backend_without_paypal_credentials_warns_at_boot(caplog):
    with caplog.at_level(logging.WARNING, logger='config.settings.guard'):
        validate_production_settings(dict(GOOD))
    assert any('PayPal refunds will wait for a person' in r.getMessage() for r in caplog.records)


def test_routing_backend_with_paypal_credentials_does_not_warn(caplog):
    env = dict(GOOD, PAYPAL_CLIENT_ID='cid', PAYPAL_CLIENT_SECRET='sec', PAYPAL_WEBHOOK_ID='wh')
    with caplog.at_level(logging.WARNING, logger='config.settings.guard'):
        validate_production_settings(env)
    assert not any('PayPal refunds will wait for a person' in r.getMessage() for r in caplog.records)
