"""Task 10.7 slice R-A: refund gateway adapters (PayPal create_refund/lookup, PayFast stub, router) on mocked HTTP."""
import logging
from decimal import Decimal

import pytest
import requests

from apps.payments.gateways import paypal
from apps.payments.gateways.paypal import classify_refund, create_refund
from apps.payments.services.refund_gateways import (
    ManualSandboxRefundGateway, PayFastRefundGateway, PayPalRefundGateway, RefundOrder, RefundResult, RoutingRefundGateway,
)

SECRET_TOKEN = 'SECRET-ACCESS-TOKEN-123'
EXC_TEXT = 'boom-private-exception-text-987'


class Resp:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self.payload = payload if payload is not None else {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}')

    def json(self):
        return self.payload


@pytest.fixture
def pp(monkeypatch):
    state = {'calls': [], 'queue': [], 'tokens': 0}

    def fake_post(url, **kw):
        state['tokens'] += 1
        tok = SECRET_TOKEN if state['tokens'] == 1 else f"{SECRET_TOKEN}-{state['tokens']}"
        return Resp(200, {'access_token': tok, 'expires_in': 3600})

    def fake_request(method, url, **kw):
        state['calls'].append({'method': method, 'url': url, **kw})
        item = state['queue'].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(paypal.requests, 'post', fake_post)
    monkeypatch.setattr(paypal.requests, 'request', fake_request)
    return state


def _err(status, name, issue=None, headers=None):
    details = [{'issue': issue}] if issue else []
    return Resp(status, {'name': name, 'details': details}, headers)


def _order(**over):
    base = dict(refund_id='11111111-2222-3333-4444-555555555555', request_id='refund-11111111-2222-3333-4444-555555555555',
                gateway='paypal', capture_ref='CAP12345678', provider_refund_id='', amount=Decimal('8.50'), currency='EUR',
                invoice_id='11111111-2222-3333-4444-555555555555', note='Refund from Sharon Online')
    base.update(over)
    return RefundOrder(**base)


@pytest.fixture
def gw():
    return PayPalRefundGateway()


# --- create_refund: request shape ------------------------------------------------------------------------------

def _create(**over):
    args = dict(capture_id='CAP12345678', amount=Decimal('8.5'), currency='EUR', note='n', invoice_id='inv-1', request_id='rid-1')
    args.update(over)
    return create_refund(**args)


def test_create_refund_request_shape_eur(pp):
    pp['queue'].append(Resp(201, {'id': 'RF1', 'status': 'COMPLETED'}))
    out = _create(note='Refund from Sharon Online')
    assert out == {'id': 'RF1', 'status': 'COMPLETED'}
    call = pp['calls'][0]
    assert call['method'] == 'POST'
    assert call['url'].endswith('/v2/payments/captures/CAP12345678/refund')
    assert call['headers']['PayPal-Request-Id'] == 'rid-1'
    assert call['json'] == {'amount': {'value': '8.50', 'currency_code': 'EUR'}, 'note_to_payer': 'Refund from Sharon Online',
                            'invoice_id': 'inv-1'}


def test_create_refund_jpy_has_no_decimals(pp):
    pp['queue'].append(Resp(201, {'id': 'RF1', 'status': 'COMPLETED'}))
    _create(amount=Decimal('1350'), currency='jpy')
    assert pp['calls'][0]['json']['amount'] == {'value': '1350', 'currency_code': 'JPY'}


def test_create_refund_usd_two_decimals(pp):
    pp['queue'].append(Resp(201, {'id': 'RF1', 'status': 'COMPLETED'}))
    _create(amount=Decimal('9'), currency='USD')
    assert pp['calls'][0]['json']['amount'] == {'value': '9.00', 'currency_code': 'USD'}


def test_create_refund_omits_empty_invoice_id_and_note(pp):
    pp['queue'].append(Resp(201, {'id': 'RF1', 'status': 'COMPLETED'}))
    _create(invoice_id='', note='')
    body = pp['calls'][0]['json']
    assert 'invoice_id' not in body and 'note_to_payer' not in body


def test_create_refund_url_uses_the_capture_id_verbatim_and_safe(pp):
    pp['queue'].append(Resp(201, {'id': 'RF1', 'status': 'COMPLETED'}))
    _create(capture_id='AB-cd_12345')
    assert pp['calls'][0]['url'].endswith('/v2/payments/captures/AB-cd_12345/refund')


@pytest.mark.parametrize('bad', ['abc/def12', 'abc%2Fdef12', 'abc.def12', 'INIT-abc123','INIT-', '', 'abcd', 'a' * 65, 'cap/../x', 'cap?x=1&y', 'cap id1', 'cap\n1234', None, 12345])
def test_create_refund_rejects_bad_capture_ids_before_any_http(pp, bad):
    with pytest.raises(ValueError):
        _create(capture_id=bad)
    assert pp['calls'] == [] and pp['tokens'] == 0


@pytest.mark.parametrize('amount,currency', [(Decimal('0'), 'USD'), (Decimal('-1'), 'USD'), (Decimal('8.505'), 'EUR'),
                                             (Decimal('1350.5'), 'JPY'), (Decimal('5'), 'XXX')])
def test_create_refund_rejects_bad_amounts_before_any_http(pp, amount, currency):
    with pytest.raises(ValueError):
        _create(amount=amount, currency=currency)
    assert pp['calls'] == [] and pp['tokens'] == 0


def test_create_refund_401_refreshes_token_and_keeps_request_id(pp):
    pp['queue'].extend([Resp(401, {}), Resp(201, {'id': 'RF1', 'status': 'COMPLETED'})])
    out = _create(request_id='keep-me')
    assert out['id'] == 'RF1'
    assert len(pp['calls']) == 2
    assert pp['calls'][0]['headers']['Authorization'] != pp['calls'][1]['headers']['Authorization']
    assert pp['calls'][1]['headers']['PayPal-Request-Id'] == 'keep-me'
    assert pp['calls'][1]['json'] == pp['calls'][0]['json']


# --- classify_refund (pure) -------------------------------------------------------------------------------------

@pytest.mark.parametrize('status,state', [('COMPLETED', 'completed'), ('PENDING', 'pending'), ('FAILED', 'rejected'),
                                          ('CANCELLED', 'rejected'), ('DENIED', 'rejected'), ('WHATEVER', 'unknown'),
                                          (None, 'unknown'), ('completed', 'unknown')])
def test_classify_refund_states(status, state):
    assert classify_refund({'id': 'RF1', 'status': status}).state == state


def test_classify_refund_tolerates_garbage_and_reads_reason():
    assert classify_refund(None).state == 'unknown'
    assert classify_refund([1]).state == 'unknown'
    assert classify_refund({'status': 'PENDING', 'status_details': {'reason': 'ECHECK'}}).reason == 'ECHECK'
    assert classify_refund({'status': 'PENDING', 'status_details': 'x'}).reason == ''


# --- adapter: status mapping ------------------------------------------------------------------------------------

def test_refund_completed(pp, gw):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'}))
    res = gw.refund(_order())
    assert res.state == 'completed' and res.reference == 'RFABC12345' and not res.provider_level


def test_refund_request_uses_order_fields(pp, gw):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'}))
    order = _order(amount=Decimal('1350'), currency='JPY', capture_ref='CAPJPY12345', request_id='refund-x-r2')
    gw.refund(order)
    call = pp['calls'][0]
    assert call['url'].endswith('/v2/payments/captures/CAPJPY12345/refund')
    assert call['headers']['PayPal-Request-Id'] == 'refund-x-r2'
    assert call['json']['amount'] == {'value': '1350', 'currency_code': 'JPY'}
    assert call['json']['invoice_id'] == order.invoice_id and call['json']['note_to_payer'] == order.note


def test_refund_empty_invoice_id_is_omitted(pp, gw):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'}))
    gw.refund(_order(invoice_id=''))
    assert 'invoice_id' not in pp['calls'][0]['json']


def test_refund_pending_is_submitted_and_keeps_refund_id(pp, gw):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': 'PENDING', 'status_details': {'reason': 'ECHECK'}}))
    res = gw.refund(_order())
    assert res.state == 'submitted' and res.reference == 'RFABC12345'


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED', 'DENIED'])
def test_refund_failed_cancelled_denied_are_rejected(pp, gw, status):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': status}))
    res = gw.refund(_order())
    assert res.state == 'rejected' and res.reference == 'RFABC12345'


@pytest.mark.parametrize('payload', [{'id': 'RFABC12345', 'status': 'SOMETHING_NEW'}, {'id': 'RFABC12345'}, {}, {'status': None}])
def test_refund_unknown_status_is_transient_never_completed(pp, gw, payload):
    pp['queue'].append(Resp(201, payload))
    res = gw.refund(_order())
    assert res.state == 'transient' and not res.provider_level


def test_refund_non_json_success_body_is_transient(pp, gw):
    class Bad(Resp):
        def json(self):
            raise ValueError('not json')
    pp['queue'].append(Bad(200))
    assert gw.refund(_order()).state == 'transient'


def test_refund_completed_without_a_refund_id_is_not_trusted(pp, gw):
    pp['queue'].append(Resp(201, {'status': 'COMPLETED'}))
    assert gw.refund(_order()).state == 'transient'


# --- adapter: error mapping -------------------------------------------------------------------------------------

@pytest.mark.parametrize('status,name,issue', [
    (422, 'UNPROCESSABLE_ENTITY', 'CAPTURE_FULLY_REFUNDED'),
    (422, 'UNPROCESSABLE_ENTITY', 'REFUND_TIME_LIMIT_EXCEEDED'),
    (422, 'UNPROCESSABLE_ENTITY', 'INSTRUMENT_DECLINED'),
    (422, 'UNPROCESSABLE_ENTITY', 'REFUND_AMOUNT_EXCEEDED'),
    (422, 'UNPROCESSABLE_ENTITY', 'CAPTURE_NOT_COMPLETED'),
    (400, 'INVALID_REQUEST', 'INVALID_PARAMETER_VALUE'),
    (404, 'NOT_FOUND_OTHER', 'SOMETHING_ELSE'),
])
def test_business_errors_are_rejected_with_paypals_code(pp, gw, status, name, issue):
    pp['queue'].append(_err(status, name, issue))
    res = gw.refund(_order())
    assert res.state == 'rejected' and res.code == issue and res.http_status == status and not res.provider_level


def test_capture_fully_refunded_code_is_kept_exactly(pp, gw):
    pp['queue'].append(_err(422, 'UNPROCESSABLE_ENTITY', 'CAPTURE_FULLY_REFUNDED'))
    assert gw.refund(_order()).code == 'CAPTURE_FULLY_REFUNDED'


def test_business_error_without_issue_uses_the_error_name(pp, gw):
    pp['queue'].append(_err(400, 'INVALID_REQUEST'))
    res = gw.refund(_order())
    assert res.state == 'rejected' and res.code == 'INVALID_REQUEST'


def test_rejected_detail_never_carries_the_provider_body(pp, gw):
    pp['queue'].append(Resp(422, {'name': 'X', 'message': 'PRIVATE-PAYER-EMAIL a@b.c', 'details': [{'issue': 'INSTRUMENT_DECLINED'}]}))
    res = gw.refund(_order())
    assert 'PRIVATE' not in res.detail and 'a@b.c' not in res.detail


@pytest.mark.parametrize('name,issue', [('NOT_AUTHORIZED', None), ('PERMISSION_DENIED', None), ('X', 'PERMISSION_DENIED'), ('Y', 'OTHER')])
def test_403_is_provider_level_transient(pp, gw, name, issue):
    pp['queue'].append(_err(403, name, issue))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.provider_level is True and res.http_status == 403


def test_401_after_the_single_refresh_is_provider_level_transient(pp, gw):
    pp['queue'].extend([Resp(401, {}), Resp(401, {})])
    res = gw.refund(_order())
    assert res.state == 'transient' and res.provider_level is True and res.http_status == 401
    assert len(pp['calls']) == 2 and pp['tokens'] == 2


def test_401_then_success_after_refresh_completes_with_same_request_id(pp, gw):
    pp['queue'].extend([Resp(401, {}), Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'})])
    res = gw.refund(_order(request_id='rid-stable'))
    assert res.state == 'completed'
    assert [c['headers']['PayPal-Request-Id'] for c in pp['calls']] == ['rid-stable', 'rid-stable']


@pytest.mark.parametrize('name, issue', [('RESOURCE_NOT_FOUND', 'INVALID_RESOURCE_ID'), ('INVALID_RESOURCE_ID', None), ('RESOURCE_NOT_FOUND', None)])
def test_404_on_the_send_path_is_an_ordinary_per_row_transient_with_its_code_kept(pp, gw, name, issue):
    """QA M1: one bad capture must burn that row's own attempts (and reach `exhausted`), not hide behind the provider-level flag
    forever. The per-gateway breaker still trips when several refunds in a sweep see it (the sandbox/live mismatch signal)."""
    pp['queue'].append(_err(404, name, issue))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.provider_level is False and res.http_status == 404
    assert res.code == (issue or name)


def test_404_on_the_lookup_path_keeps_the_provider_level_behaviour(pp, gw):
    pp['queue'].append(_err(404, 'RESOURCE_NOT_FOUND', 'INVALID_RESOURCE_ID'))
    res = gw.lookup(_order(provider_refund_id='RFABC12345'))
    assert res.state == 'transient' and res.provider_level is True and res.http_status == 404 and res.code == 'INVALID_RESOURCE_ID'


def test_a_404_that_does_not_name_the_resource_is_still_a_business_rejection(pp, gw):
    pp['queue'].append(_err(404, 'NOT_FOUND_OTHER', 'SOMETHING_ELSE'))
    res = gw.refund(_order())
    assert res.state == 'rejected' and res.http_status == 404 and not res.provider_level


@pytest.mark.parametrize('status', [408, 409, 500, 502, 503, 504])
def test_retryable_statuses_are_transient_not_provider_level(pp, gw, status):
    pp['queue'].append(_err(status, 'ANY'))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.http_status == status and not res.provider_level


@pytest.mark.parametrize('status', [405, 415])
def test_unexpected_4xx_is_a_provider_level_transient_not_a_verdict_on_the_refund(pp, gw, status):
    pp['queue'].append(_err(status, 'METHOD_NOT_ALLOWED'))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.provider_level is True and res.http_status == status


def test_429_honours_retry_after(pp, gw):
    pp['queue'].append(_err(429, 'RATE_LIMIT_REACHED', headers={'Retry-After': '120'}))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.retry_after_s == 120 and res.http_status == 429


@pytest.mark.parametrize('header', [None, '', 'soon', '-5', 'Wed, 21 Oct 2026 07:28:00 GMT'])
def test_429_with_unusable_retry_after_is_none(pp, gw, header):
    pp['queue'].append(_err(429, 'RATE_LIMIT_REACHED', headers={'Retry-After': header} if header is not None else {}))
    res = gw.refund(_order())
    assert res.state == 'transient' and res.retry_after_s is None


def test_retry_after_is_capped(pp, gw):
    pp['queue'].append(_err(503, 'X', headers={'Retry-After': '99999999'}))
    assert gw.refund(_order()).retry_after_s == 86400


@pytest.mark.parametrize('exc', [requests.Timeout(EXC_TEXT), requests.ConnectionError(EXC_TEXT)])
def test_transport_errors_are_transient(pp, gw, exc):
    pp['queue'].append(exc)
    res = gw.refund(_order())
    assert res.state == 'transient' and not res.provider_level and EXC_TEXT not in res.detail


def test_token_failure_is_transient(pp, gw, monkeypatch):
    def broken(url, **kw):
        raise requests.ConnectionError(EXC_TEXT)
    monkeypatch.setattr(paypal.requests, 'post', broken)
    res = gw.refund(_order())
    assert res.state == 'transient' and EXC_TEXT not in res.detail


@pytest.mark.parametrize('cap', ['INIT-abc12345', 'bad id', '../x', ''])
def test_malformed_capture_ref_is_rejected_before_any_http(pp, gw, cap):
    res = gw.refund(_order(capture_ref=cap))
    assert res.state == 'rejected' and res.code == 'INVALID_REFUND_REQUEST'
    assert pp['calls'] == [] and pp['tokens'] == 0


def test_unquantised_amount_is_rejected_not_rounded(pp, gw):
    res = gw.refund(_order(amount=Decimal('1350.5'), currency='JPY'))
    assert res.state == 'rejected' and pp['calls'] == []


# --- adapter: lookup --------------------------------------------------------------------------------------------

def test_lookup_uses_the_provider_refund_id(pp, gw):
    pp['queue'].append(Resp(200, {'id': 'RFABC12345', 'status': 'COMPLETED'}))
    res = gw.lookup(_order(provider_refund_id='RFABC12345'))
    call = pp['calls'][0]
    assert call['method'] == 'GET' and call['url'].endswith('/v2/payments/refunds/RFABC12345')
    assert res.state == 'completed' and res.reference == 'RFABC12345'


def test_lookup_pending_stays_submitted(pp, gw):
    pp['queue'].append(Resp(200, {'id': 'RFABC12345', 'status': 'PENDING'}))
    assert gw.lookup(_order(provider_refund_id='RFABC12345')).state == 'submitted'


@pytest.mark.parametrize('status', ['FAILED', 'CANCELLED'])
def test_lookup_failed_or_cancelled_is_rejected(pp, gw, status):
    pp['queue'].append(Resp(200, {'id': 'RFABC12345', 'status': status}))
    assert gw.lookup(_order(provider_refund_id='RFABC12345')).state == 'rejected'


def test_lookup_unknown_status_is_transient(pp, gw):
    pp['queue'].append(Resp(200, {'id': 'RFABC12345', 'status': 'NEW_THING'}))
    assert gw.lookup(_order(provider_refund_id='RFABC12345')).state == 'transient'


def test_lookup_completed_without_id_in_body_falls_back_to_the_known_id(pp, gw):
    pp['queue'].append(Resp(200, {'status': 'COMPLETED'}))
    res = gw.lookup(_order(provider_refund_id='RFABC12345'))
    assert res.state == 'completed' and res.reference == 'RFABC12345'


@pytest.mark.parametrize('resp,state,provider_level', [
    (Resp(503, {}), 'transient', False),
    (Resp(429, {}, {'Retry-After': '30'}), 'transient', False),
    (Resp(403, {'name': 'NOT_AUTHORIZED'}), 'transient', True),
    (Resp(404, {'name': 'RESOURCE_NOT_FOUND', 'details': [{'issue': 'INVALID_RESOURCE_ID'}]}), 'transient', True),
])
def test_lookup_error_mapping(pp, gw, resp, state, provider_level):
    pp['queue'].append(resp)
    res = gw.lookup(_order(provider_refund_id='RFABC12345'))
    assert res.state == state and res.provider_level is provider_level


def test_lookup_without_a_refund_id_is_manual_and_makes_no_call(pp, gw):
    res = gw.lookup(_order(provider_refund_id=''))
    assert res.state == 'manual' and 'no provider refund id' in res.detail and pp['calls'] == []


def test_lookup_malformed_refund_id_makes_no_call(pp, gw):
    res = gw.lookup(_order(provider_refund_id='../x'))
    assert res.state == 'manual' and pp['calls'] == []


# --- PayFast stub -----------------------------------------------------------------------------------------------

def test_payfast_gateway_is_manual_for_refund_and_lookup(pp):
    g = PayFastRefundGateway()
    for res in (g.refund(_order(gateway='payfast', currency='ZAR')), g.lookup(_order(gateway='payfast', provider_refund_id='x'))):
        assert res == RefundResult('manual', detail='PayFast refunds are not enabled')
    assert pp['calls'] == []


# --- router -----------------------------------------------------------------------------------------------------

@pytest.fixture
def creds(settings):
    settings.PAYPAL_CLIENT_ID = 'cid'
    settings.PAYPAL_CLIENT_SECRET = 'csecret'
    settings.PAYFAST_REFUNDS_ENABLED = False
    return settings


def test_router_sends_paypal_orders_to_paypal(pp, creds):
    pp['queue'].append(Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'}))
    res = RoutingRefundGateway().refund(_order())
    assert res.state == 'completed' and len(pp['calls']) == 1


def test_router_lookup_goes_to_paypal(pp, creds):
    pp['queue'].append(Resp(200, {'id': 'RFABC12345', 'status': 'PENDING'}))
    assert RoutingRefundGateway().lookup(_order(provider_refund_id='RFABC12345')).state == 'submitted'


@pytest.mark.parametrize('cid,secret', [('', ''), ('cid', ''), ('', 'sec')])
def test_router_paypal_without_credentials_is_manual_and_offline(pp, settings, cid, secret):
    settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET = cid, secret
    r = RoutingRefundGateway()
    assert r.refund(_order()).state == 'manual'
    assert r.lookup(_order(provider_refund_id='RFABC12345')).state == 'manual'
    assert pp['calls'] == [] and pp['tokens'] == 0


def test_router_payfast_disabled_is_manual(pp, creds):
    r = RoutingRefundGateway()
    assert r.refund(_order(gateway='payfast', currency='ZAR')).state == 'manual'
    assert r.lookup(_order(gateway='payfast', provider_refund_id='x')).state == 'manual'
    assert pp['calls'] == []


def test_router_payfast_enabled_still_manual_while_the_api_is_unverified(pp, creds):
    creds.PAYFAST_REFUNDS_ENABLED = True
    res = RoutingRefundGateway().refund(_order(gateway='payfast', currency='ZAR'))
    assert res.state == 'manual' and pp['calls'] == []


def test_router_payfast_setting_missing_counts_as_disabled(pp, creds):
    del creds.PAYFAST_REFUNDS_ENABLED
    assert RoutingRefundGateway().refund(_order(gateway='payfast', currency='ZAR')).state == 'manual'


def test_router_unknown_gateway_is_manual(pp, creds):
    res = RoutingRefundGateway().refund(_order(gateway='stripe'))
    assert res.state == 'manual' and pp['calls'] == []


def test_router_converts_unexpected_exceptions_to_transient(creds, monkeypatch):
    def boom(self, order):
        raise RuntimeError(EXC_TEXT)
    monkeypatch.setattr(PayPalRefundGateway, 'refund', boom)
    monkeypatch.setattr(PayPalRefundGateway, 'lookup', boom)
    r = RoutingRefundGateway()
    for res in (r.refund(_order()), r.lookup(_order(provider_refund_id='RFABC12345'))):
        assert res.state == 'transient' and res.detail == 'RuntimeError' and res.provider_level is False
        assert EXC_TEXT not in repr(res)


def test_router_never_raises_even_when_settings_access_fails(monkeypatch, creds):
    import apps.payments.services.refund_gateways as mod

    def boom(*a, **k):
        raise KeyError(EXC_TEXT)
    monkeypatch.setattr(mod.RoutingRefundGateway, '_select', boom)
    res = RoutingRefundGateway().refund(_order())
    assert res.state == 'transient' and res.detail == 'KeyError'


def test_router_wraps_the_real_adapter_for_a_bug_inside_it(pp, creds, monkeypatch):
    monkeypatch.setattr(paypal, 'create_refund', lambda **kw: (_ for _ in ()).throw(TypeError(EXC_TEXT)))
    res = RoutingRefundGateway().refund(_order())
    assert res.state == 'transient' and res.detail == 'TypeError'


# --- logging hygiene --------------------------------------------------------------------------------------------

def test_no_log_record_leaks_tokens_headers_or_exception_text(pp, creds, caplog):
    caplog.set_level(logging.DEBUG)
    r = RoutingRefundGateway()
    pp['queue'].extend([
        requests.ConnectionError(EXC_TEXT),
        _err(422, 'UNPROCESSABLE_ENTITY', 'INSTRUMENT_DECLINED'),
        Resp(401, {}), Resp(401, {}),
        Resp(201, {'id': 'RFABC12345', 'status': 'COMPLETED'}),
        requests.Timeout(EXC_TEXT),
    ])
    r.refund(_order())
    r.refund(_order())
    r.refund(_order())
    r.refund(_order())
    r.lookup(_order(provider_refund_id='RFABC12345'))
    text = '\n'.join(f'{rec.getMessage()} {rec.exc_text or ""} {rec.args!r}' for rec in caplog.records)
    assert SECRET_TOKEN not in text and 'Bearer' not in text and 'Authorization' not in text
    assert EXC_TEXT not in text and 'csecret' not in text
    assert all(rec.exc_info is None for rec in caplog.records)


def test_router_logs_only_the_exception_type_name(creds, monkeypatch, caplog):
    def boom(self, order):
        raise RuntimeError(EXC_TEXT)
    monkeypatch.setattr(PayPalRefundGateway, 'refund', boom)
    caplog.set_level(logging.DEBUG)
    RoutingRefundGateway().refund(_order())
    text = '\n'.join(rec.getMessage() for rec in caplog.records)
    assert 'RuntimeError' in text and EXC_TEXT not in text
    assert all(rec.exc_info is None for rec in caplog.records)


def test_manual_sandbox_gateway_contract_unchanged():
    assert ManualSandboxRefundGateway().refund(_order()).state == 'manual'
