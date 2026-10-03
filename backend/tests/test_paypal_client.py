"""Task 10.2 slice A: PayPal Orders v2 client (create / capture / get) and capture classification."""
from decimal import Decimal

import pytest
import requests

from apps.payments.gateways import paypal
from apps.payments.gateways.paypal import (
    CaptureOutcome, PayPalDeclined, PayPalError, PayPalRejected, capture_order, classify_capture, create_order,
    extract_capture, get_order,
)


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload if payload is not None else {}

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
        return Resp(200, {'access_token': f"tok{state['tokens']}", 'expires_in': 3600})

    def fake_request(method, url, **kw):
        state['calls'].append({'method': method, 'url': url, **kw})
        item = state['queue'].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(paypal.requests, 'post', fake_post)
    monkeypatch.setattr(paypal.requests, 'request', fake_request)
    return state


def _err(status, name, issue=None):
    details = [{'issue': issue}] if issue else []
    return Resp(status, {'name': name, 'details': details})


def _create(**over):
    args = dict(reference='R', amount=Decimal('9'), currency='USD', description='d', request_id='x')
    args.update(over)
    return create_order(**args)


# --- create_order ---------------------------------------------------------------------------------------------

def test_create_order_body_shape_eur(pp):
    pp['queue'].append(Resp(201, {'id': 'ORD-1', 'status': 'CREATED'}))
    out = _create(reference='REF-1', amount=Decimal('8.5'), currency='eur', description='Lesson', request_id='rid-1')
    assert out == {'id': 'ORD-1', 'status': 'CREATED'}
    call = pp['calls'][0]
    assert call['method'] == 'POST' and call['url'].endswith('/v2/checkout/orders')
    body = call['json']
    assert body['intent'] == 'CAPTURE'
    assert len(body['purchase_units']) == 1
    unit = body['purchase_units'][0]
    assert unit['custom_id'] == 'REF-1' and unit['reference_id'] == 'REF-1'
    assert unit['amount'] == {'currency_code': 'EUR', 'value': '8.50'}
    assert unit['description'] == 'Lesson'
    assert 'payment_source' not in body


def test_create_order_jpy_has_no_decimals(pp):
    pp['queue'].append(Resp(201, {'id': 'ORD-2'}))
    _create(amount=Decimal('1350'), currency='JPY')
    assert pp['calls'][0]['json']['purchase_units'][0]['amount'] == {'currency_code': 'JPY', 'value': '1350'}


def test_create_order_jpy_rounds_to_whole_yen_and_value_is_str(pp):
    pp['queue'].append(Resp(201, {'id': 'ORD-3'}))
    _create(amount=Decimal('1350.5'), currency='JPY')
    value = pp['calls'][0]['json']['purchase_units'][0]['amount']['value']
    assert value == '1351' and isinstance(value, str)


def test_create_order_sends_request_id_and_auth_headers(pp):
    pp['queue'].append(Resp(201, {'id': 'ORD-1'}))
    _create(request_id='rid-xyz')
    headers = pp['calls'][0]['headers']
    assert headers['PayPal-Request-Id'] == 'rid-xyz'
    assert headers['Authorization'].startswith('Bearer ')
    assert headers['Content-Type'] == 'application/json'


def test_create_order_immediate_payment_setting(pp, settings):
    settings.PAYPAL_REQUIRE_IMMEDIATE_PAYMENT = True
    pp['queue'].append(Resp(201, {'id': 'ORD-1'}))
    _create()
    ctx = pp['calls'][0]['json']['payment_source']['paypal']['experience_context']
    assert ctx['payment_method_preference'] == 'IMMEDIATE_PAYMENT_REQUIRED'


def test_create_order_default_has_no_payment_source(pp, settings):
    settings.PAYPAL_REQUIRE_IMMEDIATE_PAYMENT = False
    pp['queue'].append(Resp(201, {'id': 'ORD-1'}))
    _create()
    assert 'payment_source' not in pp['calls'][0]['json']


def test_create_order_unsupported_currency_raises_before_http(pp):
    with pytest.raises(ValueError):
        _create(currency='XXX')
    assert pp['calls'] == []


def test_create_order_4xx_is_rejected_with_name_and_issue(pp):
    pp['queue'].append(_err(422, 'UNPROCESSABLE_ENTITY', 'CURRENCY_NOT_SUPPORTED'))
    with pytest.raises(PayPalRejected) as exc:
        _create()
    assert exc.value.name == 'UNPROCESSABLE_ENTITY' and exc.value.issue == 'CURRENCY_NOT_SUPPORTED'
    assert isinstance(exc.value, PayPalError)


def test_create_order_5xx_is_plain_paypal_error(pp):
    pp['queue'].append(Resp(503, {}))
    with pytest.raises(PayPalError) as exc:
        _create()
    assert not isinstance(exc.value, PayPalRejected)


def test_create_order_network_error(pp):
    pp['queue'].append(requests.ConnectionError('down'))
    with pytest.raises(PayPalError) as exc:
        _create()
    assert not isinstance(exc.value, PayPalRejected)


def test_create_order_401_refreshes_token_and_retries(pp):
    pp['queue'].extend([Resp(401, {}), Resp(201, {'id': 'ORD-9'})])
    out = _create(request_id='keep-me')
    assert out['id'] == 'ORD-9'
    assert len(pp['calls']) == 2
    assert pp['calls'][0]['headers']['Authorization'] != pp['calls'][1]['headers']['Authorization']
    assert pp['calls'][1]['headers']['PayPal-Request-Id'] == 'keep-me'
    assert pp['calls'][1]['json'] == pp['calls'][0]['json']


def test_create_order_persistent_401_is_transport_error(pp):
    pp['queue'].extend([Resp(401, {}), Resp(401, {})])
    with pytest.raises(PayPalError) as exc:
        _create()
    assert not isinstance(exc.value, PayPalRejected)


# --- capture_order / get_order -------------------------------------------------------------------------------

def test_capture_order_posts_with_request_id(pp):
    pp['queue'].append(Resp(201, {'id': 'ORD-1', 'status': 'COMPLETED'}))
    out = capture_order('ORD-1', request_id='cap-rid')
    assert out['status'] == 'COMPLETED'
    call = pp['calls'][0]
    assert call['method'] == 'POST' and call['url'].endswith('/v2/checkout/orders/ORD-1/capture')
    assert call['headers']['PayPal-Request-Id'] == 'cap-rid'


def test_capture_order_already_captured_returns_fetched_order(pp):
    order = {'id': 'ORD-1', 'status': 'COMPLETED'}
    pp['queue'].extend([_err(422, 'UNPROCESSABLE_ENTITY', 'ORDER_ALREADY_CAPTURED'), Resp(200, order)])
    assert capture_order('ORD-1', request_id='r') == order
    assert pp['calls'][1]['method'] == 'GET' and pp['calls'][1]['url'].endswith('/v2/checkout/orders/ORD-1')


def test_capture_order_declined(pp):
    pp['queue'].append(_err(422, 'UNPROCESSABLE_ENTITY', 'INSTRUMENT_DECLINED'))
    with pytest.raises(PayPalDeclined) as exc:
        capture_order('ORD-1', request_id='r')
    assert isinstance(exc.value, PayPalRejected) and exc.value.issue == 'INSTRUMENT_DECLINED'


def test_capture_order_other_4xx_is_rejected_not_declined(pp):
    pp['queue'].append(_err(422, 'UNPROCESSABLE_ENTITY', 'ORDER_NOT_APPROVED'))
    with pytest.raises(PayPalRejected) as exc:
        capture_order('ORD-1', request_id='r')
    assert not isinstance(exc.value, PayPalDeclined)


def test_capture_order_network_error(pp):
    pp['queue'].append(requests.Timeout('slow'))
    with pytest.raises(PayPalError):
        capture_order('ORD-1', request_id='r')


def test_get_order(pp):
    pp['queue'].append(Resp(200, {'id': 'ORD-1', 'status': 'APPROVED'}))
    assert get_order('ORD-1')['status'] == 'APPROVED'
    assert pp['calls'][0]['method'] == 'GET'


def test_get_order_5xx(pp):
    pp['queue'].append(Resp(500, {}))
    with pytest.raises(PayPalError):
        get_order('ORD-1')


def test_existing_get_capture_still_works(pp):
    pp['queue'].append(Resp(200, {'id': 'CAP-1'}))
    assert paypal.get_capture('CAP-1') == {'id': 'CAP-1'}


# --- extract_capture / classify_capture ----------------------------------------------------------------------

def _order(capture):
    return {'purchase_units': [{'payments': {'captures': [capture]}}]}


def test_extract_capture_returns_first_capture():
    cap = {'id': 'C1', 'status': 'COMPLETED'}
    assert extract_capture(_order(cap)) is cap


@pytest.mark.parametrize('order', [{}, {'purchase_units': []}, {'purchase_units': [{}]},
                                   {'purchase_units': [{'payments': {}}]},
                                   {'purchase_units': [{'payments': {'captures': []}}]}, None])
def test_extract_capture_missing_is_none(order):
    assert extract_capture(order) is None


def test_classify_completed():
    assert classify_capture({'status': 'COMPLETED'}) == CaptureOutcome('completed', '', False, False)


@pytest.mark.parametrize('reason', ['RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION', 'INTERNATIONAL_WITHDRAWAL'])
def test_classify_pending_merchant_side(reason):
    out = classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}})
    assert out == CaptureOutcome('pending', reason, True, False)


@pytest.mark.parametrize('reason', ['PENDING_REVIEW', 'TRANSACTION_APPROVED_AWAITING_FUNDING'])
def test_classify_pending_review_is_risk_based(reason):
    out = classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}})
    assert out == CaptureOutcome('pending', reason, False, True)


@pytest.mark.parametrize('reason', ['ECHECK', 'VERIFICATION_REQUIRED', 'OTHER', 'MULTI_CURRENCY', 'UNILATERAL'])
def test_classify_pending_other_reasons_no_flags(reason):
    out = classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}})
    assert out == CaptureOutcome('pending', reason, False, False)


def test_classify_pending_without_reason():
    assert classify_capture({'status': 'PENDING'}) == CaptureOutcome('pending', '', False, False)


def test_classify_declined_and_failed():
    assert classify_capture({'status': 'DECLINED'}).state == 'declined'
    assert classify_capture({'status': 'FAILED'}).state == 'failed'


@pytest.mark.parametrize('status', ['SOMETHING_NEW', '', None, 'completed ', 'PARTIALLY_REFUNDED', 'REFUNDED'])
def test_classify_unknown_status_is_pending_never_completed(status):
    out = classify_capture({'status': status, 'status_details': {'reason': 'WEIRD'}})
    assert out.state == 'pending' and out.reason == 'WEIRD'
    assert not out.merchant_side and not out.risk_based


def test_classify_none_capture_is_pending():
    assert classify_capture(None).state == 'pending'
