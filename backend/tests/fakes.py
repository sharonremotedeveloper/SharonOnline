"""
Shared provider fakes (Q0). Each one answers at the HTTP / SDK boundary, so the real integration code (request building,
status handling, error mapping) runs in the test; only the provider is fake. Use the pytest fixtures in conftest.py:

    def test_x(fake_resend, fake_zoom, fake_google, fake_r2): ...

* FakeResend  - POST https://api.resend.com/emails. `.sent` (payloads), `.fail_with(status)`, `.fail_with_network_error()`.
* FakeZoom    - S2S OAuth token + create / get / list / patch / delete meeting. Meeting state is tri-state
                `started | not_started | error` (`.set_status(id, state)`): Zoom reports `started` / `waiting`, `error`
                answers HTTP 500. `.fail_next(op, status)` for create/get/list/delete/update/token,
                `.rate_limit_next(op, retry_after)` (429 + Retry-After), `.timeout_next(op, created=False)` (a
                ReadTimeout; `created=True` builds the meeting first, like a response lost on the way back),
                `.rotate_token()` (Zoom revokes the current token: the next API call answers 401). Every GET of a meeting
                returns a NEW `start_url` (`zak=fake-zak-<n>`), so tests can prove a host link was fetched fresh.
                `.sleeps` records the client's back-off waits (installed in place of `time.sleep`).
* FakeGoogle  - Calendar v3 events insert / patch / put / delete (410 once deleted), freeBusy, and the OAuth token
                endpoint (`.revoke()` -> `invalid_grant`). `.add_busy(start, end)`, `.fail_next(op, status)`.
* FakeR2      - a boto3 S3 client stub: put/head/get (Range, IfMatch)/copy (CopySourceIfMatch)/delete/presign, with real
                botocore ClientError codes (404 / NoSuchKey / PreconditionFailed).

Every fake HTTP call must pass `timeout=` (the same rule the guard enforces in apps/) and an unexpected URL is an
AssertionError, never a silent 200.
"""
import base64
import hashlib
import io
import itertools
import json as jsonlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import requests
from botocore.exceptions import ClientError

ZOOM_STATES = ('started', 'not_started', 'error')


# ------------------------------------------------------------------ HTTP plumbing
class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else (jsonlib.dumps(json_data) if json_data is not None else '')
        self.content = self.text.encode()
        self.headers = headers or {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._json is None:
            raise ValueError('response has no JSON body')
        return jsonlib.loads(jsonlib.dumps(self._json))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} error', response=self)


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    json: object = None
    data: object = None
    params: object = None


class FakeRequestsModule:
    """Stands in for the `requests` module inside ONE integration module: verbs go to the fake, the rest is real requests."""

    def __init__(self, handler):
        self._handler = handler

    def __getattr__(self, name):
        return getattr(requests, name)

    def request(self, method, url, **kwargs):
        assert 'timeout' in kwargs, f'{method} {url} without timeout= (the HTTP-timeout guard forbids it)'
        return self._handler(RecordedRequest(method.upper(), url, dict(kwargs.get('headers') or {}), kwargs.get('json'),
                                             kwargs.get('data'), kwargs.get('params')))

    def get(self, url, **kw):
        return self.request('GET', url, **kw)

    def post(self, url, **kw):
        return self.request('POST', url, **kw)

    def put(self, url, **kw):
        return self.request('PUT', url, **kw)

    def patch(self, url, **kw):
        return self.request('PATCH', url, **kw)

    def delete(self, url, **kw):
        return self.request('DELETE', url, **kw)


class _FailureQueue:
    def __init__(self):
        self._next = {}

    def fail_next(self, op, status, body=None):
        self._next.setdefault(op, []).append((status, body))

    def pop(self, op):
        queue = self._next.get(op)
        return queue.pop(0) if queue else None


def _unexpected(req):
    raise AssertionError(f'unexpected request to the fake: {req.method} {req.url}')


# ------------------------------------------------------------------ Resend
class FakeResend:
    URL = 'https://api.resend.com/emails'

    def __init__(self):
        self.requests = []
        self.sent = []
        self._fail = []
        self._ids = itertools.count(1)

    def fail_with(self, status, times=1, body=None):
        self._fail.extend([(status, body or {'name': 'fake_error', 'message': f'HTTP {status}'})] * times)

    def fail_with_network_error(self, times=1):
        self._fail.extend([('network', None)] * times)

    def handle(self, req):
        if not (req.method == 'POST' and req.url == self.URL):
            _unexpected(req)
        self.requests.append(req)
        if self._fail:
            status, body = self._fail.pop(0)
            if status == 'network':
                raise requests.ConnectionError('fake Resend unreachable')
            return FakeResponse(status, body)
        self.sent.append(req.json)
        return FakeResponse(200, {'id': f'fake-email-{next(self._ids)}'})

    def install(self, monkeypatch):
        # Since N1c the only module that talks to Resend is apps.integrations.services.email; it reads settings, not env.
        from django.conf import settings
        monkeypatch.setattr(settings, 'RESEND_API_KEY', 're_test_fake_key', raising=False)
        monkeypatch.setattr(settings, 'EMAIL_BACKEND_MODE', 'resend', raising=False)
        monkeypatch.setattr('apps.integrations.services.email.requests', FakeRequestsModule(self.handle))
        return self


# ------------------------------------------------------------------ Zoom
class FakeZoom(_FailureQueue):
    TOKEN_URL = 'https://zoom.us/oauth/token'
    API = 'https://api.zoom.us/v2'

    def __init__(self):
        super().__init__()
        self.requests = []
        self.meetings = {}
        self.created = []
        self.token_requests = 0
        self.access_token = 'fake-zoom-access-token'
        self.expires_in = 3599
        self.sleeps = []
        self._tokens = itertools.count(2)
        self._zaks = itertools.count(1)
        self._ids = itertools.count(81000000001)
        self._special = {}

    def rotate_token(self):
        """Zoom revokes the token it issued last: the client's cached token now answers 401 until it fetches a new one."""
        self.access_token = f'fake-zoom-access-token-{next(self._tokens)}'

    def rate_limit_next(self, op, retry_after=None, times=1):
        headers = {} if retry_after is None else {'Retry-After': str(retry_after)}
        self._special.setdefault(op, []).extend([('429', headers)] * times)

    def timeout_next(self, op, created=False, times=1):
        self._special.setdefault(op, []).extend([('timeout', created)] * times)

    def _pop_special(self, op):
        queue = self._special.get(op)
        return queue.pop(0) if queue else None

    def set_status(self, meeting_id, state):
        if state not in ZOOM_STATES:
            raise ValueError(f'Zoom fake state must be one of {ZOOM_STATES}, not {state!r}')
        self.meetings.setdefault(str(meeting_id), {'id': int(meeting_id) if str(meeting_id).isdigit() else meeting_id})
        self.meetings[str(meeting_id)]['state'] = state

    def _failure(self, op):
        failure = self.pop(op)
        if failure:
            status, body = failure
            return FakeResponse(status, body or {'code': status, 'message': f'fake Zoom {op} failure'})
        return None

    def _special_response(self, op, build=None):
        special = self._pop_special(op)
        if special is None:
            return None
        kind, arg = special
        if kind == '429':
            return FakeResponse(429, {'code': 429, 'message': 'You have reached the maximum per-second rate limit.'},
                                headers=arg)
        if arg and build is not None:          # timeout AFTER Zoom did the work: the response is lost on the way back
            build()
        raise requests.ReadTimeout(f'fake Zoom {op} timed out')

    def handle(self, req):
        self.requests.append(req)
        if req.url.startswith(self.TOKEN_URL):
            self.token_requests += 1
            return (self._special_response('token') or self._failure('token')
                    or FakeResponse(200, {'access_token': self.access_token, 'token_type': 'bearer',
                                          'expires_in': self.expires_in}))
        if req.headers.get('Authorization') != f'Bearer {self.access_token}':
            return FakeResponse(401, {'code': 124, 'message': 'Invalid access token.'})
        path = urlparse(req.url).path.removeprefix('/v2')
        created = re.fullmatch(r'/users/([^/]+)/meetings', path)
        if created and req.method == 'POST':
            host, body = created.group(1), req.json or {}
            return (self._special_response('create', lambda: self._create(host, body))
                    or self._failure('create') or self._create(host, body))
        if created and req.method == 'GET':
            return self._special_response('list') or self._failure('list') or self._list(created.group(1), req.params or {})
        one = re.fullmatch(r'/meetings/([^/]+)', path)
        if not one:
            _unexpected(req)
        meeting_id = one.group(1)
        op = {'GET': 'get', 'DELETE': 'delete', 'PATCH': 'update'}.get(req.method)
        if op is None:
            _unexpected(req)
        failure = self._special_response(op) or self._failure(op)
        if failure:
            return failure
        meeting = self.meetings.get(meeting_id)
        if meeting is None:
            return FakeResponse(404, {'code': 3001, 'message': 'Meeting does not exist.'})
        if op == 'delete':
            del self.meetings[meeting_id]
            return FakeResponse(204)
        if op == 'update':
            meeting.update(req.json or {})
            return FakeResponse(204)
        if meeting.get('state') == 'error':
            return FakeResponse(500, {'code': 500, 'message': 'fake Zoom internal error'})
        return FakeResponse(200, {**meeting, 'status': 'started' if meeting.get('state') == 'started' else 'waiting',
                                  'start_url': f'https://zoom.us/s/{meeting_id}?zak=fake-zak-{next(self._zaks)}'})

    def _create(self, host, body):
        meeting_id = next(self._ids)
        meeting = {'id': meeting_id, 'host_id': host, 'topic': body.get('topic'), 'start_time': body.get('start_time'),
                   'duration': body.get('duration'), 'agenda': body.get('agenda', ''), 'settings': body.get('settings', {}),
                   'state': 'not_started', 'join_url': f'https://zoom.us/j/{meeting_id}?pwd=fake',
                   'start_url': f'https://zoom.us/s/{meeting_id}?zak=fake-zak-0', 'password': 'fake123'}
        self.meetings[str(meeting_id)] = meeting
        self.created.append(body)
        return FakeResponse(201, meeting)

    def _list(self, host, params):
        """`GET /users/{host}/meetings` (upcoming): summaries only (no start_url / password), paged by `page_size`."""
        mine = [m for m in self.meetings.values() if m.get('host_id') == host]
        size = int(params.get('page_size') or 30)
        start = int(params.get('next_page_token') or 0)
        page = mine[start:start + size]
        token = str(start + size) if start + size < len(mine) else ''
        return FakeResponse(200, {'page_size': size, 'total_records': len(mine), 'next_page_token': token,
                                  'meetings': [{'id': m['id'], 'topic': m.get('topic'), 'start_time': m.get('start_time'),
                                                'agenda': m.get('agenda', ''), 'join_url': m['join_url']} for m in page]})

    def install(self, monkeypatch):
        """Credentials come from Django settings since Z1 (no environment reads in app code); back-off waits are recorded,
        never slept."""
        from django.conf import settings
        for name in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET'):
            monkeypatch.setattr(settings, name, f'fake-{name.lower()}', raising=False)
        monkeypatch.setattr('apps.integrations.zoom.requests', FakeRequestsModule(self.handle))
        monkeypatch.setattr('apps.integrations.zoom._sleep', self.sleeps.append)
        monkeypatch.setattr('apps.integrations.zoom_auth._sleep', self.sleeps.append)
        return self


# ------------------------------------------------------------------ Google Calendar
class FakeGoogle(_FailureQueue):
    CALENDAR = 'https://www.googleapis.com/calendar/v3'
    TOKEN_URL = 'https://oauth2.googleapis.com/token'

    def __init__(self):
        super().__init__()
        self.requests = []
        self.events = {}
        self.deleted = set()
        self.busy = []
        self.access_token = 'fake-google-access-token'
        self.revoked = False
        self._ids = itertools.count(1)

    def revoke(self):
        self.revoked = True

    def add_busy(self, start: datetime, end: datetime, calendar='primary'):
        self.busy.append({'calendar': calendar, 'start': start.isoformat(), 'end': end.isoformat()})

    def handle(self, req):
        self.requests.append(req)
        if req.url.startswith(self.TOKEN_URL):
            return self._token()
        if req.headers.get('Authorization') != f'Bearer {self.access_token}':
            return FakeResponse(401, {'error': {'code': 401, 'message': 'Invalid Credentials'}})
        if not req.url.startswith(self.CALENDAR):
            _unexpected(req)
        path = urlparse(req.url).path.removeprefix('/calendar/v3')
        if path == '/freeBusy' and req.method == 'POST':
            return self.pop_response('freebusy') or self._freebusy(req.json or {})
        if re.fullmatch(r'/calendars/([^/]+)/events', path) and req.method == 'POST':
            return self.pop_response('insert') or self._insert(req.json or {})
        one = re.fullmatch(r'/calendars/([^/]+)/events/([^/]+)', path)
        op = {'PATCH': 'update', 'PUT': 'update', 'DELETE': 'delete', 'GET': 'get'}.get(req.method)
        if not one or op is None:
            _unexpected(req)
        return self.pop_response(op) or self._event(op, one.group(2), req)

    def _token(self):
        failure = self.pop('token')
        if failure:
            return FakeResponse(*failure)
        if self.revoked:
            return FakeResponse(400, {'error': 'invalid_grant', 'error_description': 'Token has been expired or revoked.'})
        return FakeResponse(200, {'access_token': self.access_token, 'expires_in': 3599, 'token_type': 'Bearer',
                                  'scope': 'https://www.googleapis.com/auth/calendar.events'})

    def _event(self, op, event_id, req):
        if event_id not in self.events:
            return FakeResponse(410 if event_id in self.deleted else 404, {'error': {'code': 404, 'message': 'Not Found'}})
        if op == 'delete':
            del self.events[event_id]
            self.deleted.add(event_id)
            return FakeResponse(204)
        if op == 'update':
            if req.method == 'PUT':
                self.events[event_id] = {'id': event_id, **(req.json or {})}
            else:
                self.events[event_id].update(req.json or {})
        return FakeResponse(200, self.events[event_id])

    def pop_response(self, op):
        failure = self.pop(op)
        return FakeResponse(failure[0], failure[1] or {'error': {'code': failure[0], 'message': f'fake {op} failure'}}) \
            if failure else None

    def _insert(self, body):
        event_id = body.get('id') or f'fakeevt{next(self._ids)}'
        if event_id in self.events:
            return FakeResponse(409, {'error': {'code': 409, 'message': 'The requested identifier already exists.'}})
        self.events[event_id] = {**body, 'id': event_id}
        return FakeResponse(200, self.events[event_id])

    def _freebusy(self, body):
        calendars = {}
        for item in body.get('items', [{'id': 'primary'}]):
            calendars[item['id']] = {'busy': [{'start': b['start'], 'end': b['end']} for b in self.busy
                                              if b['calendar'] == item['id']
                                              and b['end'] > body.get('timeMin', '') and b['start'] < body.get('timeMax', '~')]}
        return FakeResponse(200, {'kind': 'calendar#freeBusy', 'calendars': calendars})

    def install(self, monkeypatch):
        monkeypatch.setattr('apps.integrations.google_calendar.requests', FakeRequestsModule(self.handle))
        return self


# ------------------------------------------------------------------ R2 (boto3 S3 client stub)
class _Body(io.BytesIO):
    """botocore StreamingBody look-alike."""

    def close(self):
        pass


def _client_error(code, status, operation, message=''):
    return ClientError({'Error': {'Code': code, 'Message': message or code},
                        'ResponseMetadata': {'HTTPStatusCode': status}}, operation)


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.presigned = []

    def _get(self, bucket, key, operation, if_match=None):
        obj = self.objects.get((bucket, key))
        if obj is None:
            code = '404' if operation == 'HeadObject' else 'NoSuchKey'
            raise _client_error(code, 404, operation, 'Not Found')
        if if_match is not None and if_match != obj['etag']:
            raise _client_error('PreconditionFailed', 412, operation, 'At least one of the pre-conditions failed')
        return obj

    def put_object(self, Bucket, Key, Body=b'', ContentType='binary/octet-stream', **kw):
        body = Body if isinstance(Body, bytes) else Body.read()
        etag = '"' + hashlib.md5(body, usedforsecurity=False).hexdigest() + '"'
        self.objects[(Bucket, Key)] = {'body': body, 'etag': etag, 'content_type': ContentType}
        self.calls.append(('put_object', Bucket, Key))
        return {'ETag': etag}

    def head_object(self, Bucket, Key, IfMatch=None, **kw):
        self.calls.append(('head_object', Bucket, Key))
        obj = self._get(Bucket, Key, 'HeadObject', IfMatch)
        return {'ETag': obj['etag'], 'ContentLength': len(obj['body']), 'ContentType': obj['content_type']}

    def get_object(self, Bucket, Key, Range=None, IfMatch=None, **kw):
        self.calls.append(('get_object', Bucket, Key, Range))
        obj = self._get(Bucket, Key, 'GetObject', IfMatch)
        body, extra = obj['body'], {}
        if Range:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', Range)
            if not match:
                raise _client_error('InvalidRange', 416, 'GetObject')
            first = int(match.group(1))
            last = int(match.group(2)) if match.group(2) else len(body) - 1
            extra['ContentRange'] = f'bytes {first}-{min(last, len(body) - 1)}/{len(body)}'
            body = body[first:last + 1]
        return {'Body': _Body(body), 'ETag': obj['etag'], 'ContentLength': len(body),
                'ContentType': obj['content_type'], **extra}

    def copy_object(self, Bucket, Key, CopySource, CopySourceIfMatch=None, **kw):
        if isinstance(CopySource, str):
            src_bucket, src_key = CopySource.lstrip('/').split('/', 1)
        else:
            src_bucket, src_key = CopySource['Bucket'], CopySource['Key']
        self.calls.append(('copy_object', f'{src_bucket}/{src_key}', f'{Bucket}/{Key}'))
        obj = self._get(src_bucket, src_key, 'CopyObject', CopySourceIfMatch)
        self.objects[(Bucket, Key)] = dict(obj)
        return {'CopyObjectResult': {'ETag': obj['etag']}}

    def delete_object(self, Bucket, Key, **kw):
        self.calls.append(('delete_object', Bucket, Key))
        self.objects.pop((Bucket, Key), None)
        return {'ResponseMetadata': {'HTTPStatusCode': 204}}

    def generate_presigned_url(self, ClientMethod, Params=None, ExpiresIn=3600, **kw):
        params = Params or {}
        self.presigned.append({'ClientMethod': ClientMethod, 'Params': params, 'ExpiresIn': ExpiresIn})
        signature = base64.urlsafe_b64encode(f'{ClientMethod}:{params}'.encode()).decode()[:16]
        return (f"https://fake-r2.test/{params.get('Bucket')}/{params.get('Key')}"
                f"?X-Amz-Expires={ExpiresIn}&X-Amz-Signature={signature}")

    def install(self, monkeypatch):
        monkeypatch.setattr('apps.common.r2_client.get_r2_client', lambda: self)
        return self
