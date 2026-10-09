"""
Shared provider fakes (Q0). Each one answers at the HTTP / SDK boundary, so the real integration code (request building,
status handling, error mapping) runs in the test; only the provider is fake. Use the pytest fixtures in conftest.py:

    def test_x(fake_resend, fake_daily, fake_google, fake_r2): ...

* FakeResend  - POST https://api.resend.com/emails. `.sent` (payloads), `.fail_with(status)`, `.fail_with_network_error()`.
* FakeDaily   - rooms (get / create / update / delete), meeting tokens and the presence roster (`.set_presence(room, [user ids])`).
                `.fail_next(op, status)` for room_get / room_create / room_delete / token / presence.
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
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from botocore.exceptions import ClientError


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


# ------------------------------------------------------------------ Daily.co
class FakeDaily(_FailureQueue):
    """Daily.co REST: rooms (get / create / delete), meeting tokens and the room presence roster.

    `.rooms` maps room name -> room JSON; `.set_presence(room, [user ids])` is who is in the room right now (the roster
    carries `userId`, the id the token was issued with). `.fail_next(op, status)` for room_get / room_create / room_delete /
    token / presence; `.created` lists room names in creation order, `.updated` those whose open window moved (proves a retry never builds a second room).
    """
    API = 'https://api.daily.co/v1'

    def __init__(self):
        super().__init__()
        self.rooms = {}
        self.created = []
        self.updated = []
        self.requests = []
        self.tokens = []
        self._presence = {}
        self._token_ids = itertools.count(1)

    def set_presence(self, room_name, user_ids):
        self._presence[room_name] = [{'id': f'session-{i}', 'userId': str(u), 'userName': f'user {u}'}
                                     for i, u in enumerate(user_ids, 1)]

    def _failed(self, op):
        failure = self.pop(op)
        if failure is None:
            return None
        status, body = failure
        return FakeResponse(status, body or {'error': 'fake-daily-error', 'info': f'fake Daily {op} failure'})

    def handle(self, req):
        self.requests.append(req)
        path = req.url[len(self.API):] if req.url.startswith(self.API) else _unexpected(req)
        if req.method == 'POST' and path == '/rooms':
            return self._failed('room_create') or self._create_room(req.json or {})
        if req.method == 'POST' and path == '/meeting-tokens':
            return self._failed('token') or self._token(req.json or {})
        match = re.fullmatch(r'/rooms/([^/]+)(/presence)?', path)
        if not match:
            _unexpected(req)
        name, presence = match.group(1), bool(match.group(2))
        if req.method == 'GET' and presence:
            return self._failed('presence') or self._presence_response(name)
        if req.method == 'GET':
            return self._failed('room_get') or self._get_room(name)
        if req.method == 'POST' and not presence:
            return self._failed('room_update') or self._update_room(name, req.json or {})
        if req.method == 'DELETE' and not presence:
            return self._failed('room_delete') or self._delete_room(name)
        _unexpected(req)

    def _create_room(self, body):
        name = body['name']
        if name in self.rooms:
            return FakeResponse(409, {'error': 'invalid-request-error', 'info': 'room already exists'})
        room = {'name': name, 'url': f'https://fake.daily.co/{name}', 'privacy': body.get('privacy', 'public'),
                'config': body.get('properties', {})}
        self.rooms[name] = room
        self.created.append(name)
        return FakeResponse(200, room)

    def _update_room(self, name, body):
        if name not in self.rooms:
            return FakeResponse(404, {'error': 'not-found'})
        self.rooms[name]['config'].update(body.get('properties', {}))
        self.updated.append(name)
        return FakeResponse(200, self.rooms[name])

    def _get_room(self, name):
        if name not in self.rooms:
            return FakeResponse(404, {'error': 'not-found', 'info': f'room {name} not found'})
        return FakeResponse(200, self.rooms[name])

    def _delete_room(self, name):
        if self.rooms.pop(name, None) is None:
            return FakeResponse(404, {'error': 'not-found'})
        self._presence.pop(name, None)
        return FakeResponse(200, {'deleted': True, 'name': name})

    def _presence_response(self, name):
        if name not in self.rooms:
            return FakeResponse(404, {'error': 'not-found'})
        roster = self._presence.get(name, [])
        return FakeResponse(200, {'total_count': len(roster), 'data': roster})

    def _token(self, body):
        self.tokens.append(body.get('properties', {}))
        return FakeResponse(200, {'token': f'fake-daily-token-{next(self._token_ids)}'})

    def install(self, monkeypatch):
        from django.conf import settings
        monkeypatch.setattr(settings, 'DAILY_API_KEY', 'fake-daily-live-key', raising=False)
        monkeypatch.setattr(settings, 'DAILY_DOMAIN', 'fake.daily.co', raising=False)
        monkeypatch.setattr(settings, 'DAILY_SIMULATE_WITHOUT_CREDENTIALS', False, raising=False)
        monkeypatch.setattr('apps.integrations.services.daily.requests', FakeRequestsModule(self.handle))
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
        self.external = []          # events the tutor made themselves (not created through our insert)
        self.page_size = 250
        self.access_token = 'fake-google-access-token'
        self.revoked = False
        self._ids = itertools.count(1)

    def revoke(self):
        self.revoked = True

    def add_busy(self, start: datetime, end: datetime, calendar='primary'):
        self.busy.append({'calendar': calendar, 'start': start.isoformat(), 'end': end.isoformat()})

    def add_external_event(self, start: datetime = None, end: datetime = None, *, transparent=False, status='confirmed',
                           all_day=None, summary='Dentist'):
        """A calendar entry the tutor made themselves. `all_day=(date, date)` gives a date-only (all-day) event."""
        event = {'id': f'ext{len(self.external) + 1}', 'status': status, 'summary': summary,
                 'transparency': 'transparent' if transparent else 'opaque'}
        if all_day:
            event['start'], event['end'] = {'date': all_day[0].isoformat()}, {'date': all_day[1].isoformat()}
        else:
            event['start'], event['end'] = {'dateTime': start.isoformat()}, {'dateTime': end.isoformat()}
        self.external.append(event)
        return event

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
        if re.fullmatch(r'/calendars/([^/]+)/events', path) and req.method == 'GET':
            return self.pop_response('list') or self._list(req.params or {})
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

    @staticmethod
    def _bounds(event):
        def point(side):
            if 'dateTime' in side:
                return datetime.fromisoformat(side['dateTime'])
            return datetime.fromisoformat(side['date']).replace(tzinfo=timezone.utc)
        return point(event['start']), point(event['end'])

    def _list(self, params):
        """events.list: events overlapping [timeMin, timeMax), `page_size` per page, pageToken = next offset."""
        lo, hi = datetime.fromisoformat(params['timeMin']), datetime.fromisoformat(params['timeMax'])
        inside = [e for e in [*self.events.values(), *self.external]
                  if self._bounds(e)[0] < hi and self._bounds(e)[1] > lo]
        offset = int(params.get('pageToken') or 0)
        page = inside[offset:offset + self.page_size]
        body = {'kind': 'calendar#events', 'items': page}
        if offset + self.page_size < len(inside):
            body['nextPageToken'] = str(offset + self.page_size)
        return FakeResponse(200, body)

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
