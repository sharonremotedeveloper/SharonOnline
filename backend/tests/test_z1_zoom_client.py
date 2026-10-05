"""
Slice Z1 (PRP 12.1a, docs/PHASE_11_12_EXECUTION_PLAN.md section 3.3): Zoom client hardening.

* credentials from Django settings only, refused at production boot when missing (and by scripts/check_deploy.py)
* S2S OAuth token cache per account id (TTL expires_in - 60 s, single-flight, failures never cached, 401 -> refresh once)
* retries only for 429 (capped Retry-After) and 5xx (jittered back-off), bounded; other 4xx and timeouts are final
* create_meeting is never retried after an ambiguous outcome without first searching for the booking's meeting
* auto_recording "none" explicit; no `return ""` left in zoom.py

Everything runs against tests/fakes.py::FakeZoom (no network).
"""
import importlib.util
import inspect
import logging
from pathlib import Path

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from apps.integrations import zoom as zoom_module
from apps.integrations.zoom import ZoomError, zoom_client
from config.settings.guard import validate_production_settings
from test_settings_guard import GOOD

BOOKING_ID = '3f1c2b9a-0000-4000-8000-00000000abcd'
START = '2026-11-01T10:00:00Z'
SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'check_deploy.py'


def zoom_auth():
    from apps.integrations import zoom_auth as module
    return module


def gets(fake, path_part):
    return [r for r in fake.requests if r.method == 'GET' and path_part in r.url]


def posts(fake):
    return [r for r in fake.requests if r.method == 'POST' and '/meetings' in r.url]


# ====================================================================== settings + boot guard
class TestCredentialsFromSettings:
    def test_the_client_reads_django_settings(self, settings):
        settings.ZOOM_ACCOUNT_ID, settings.ZOOM_CLIENT_ID, settings.ZOOM_CLIENT_SECRET = 'acc', 'cid', 'sec'
        assert (zoom_client.account_id, zoom_client.client_id, zoom_client.client_secret) == ('acc', 'cid', 'sec')
        assert zoom_client.credentials_configured()
        settings.ZOOM_CLIENT_SECRET = ''
        assert not zoom_client.credentials_configured()

    def test_no_environment_reads_in_the_zoom_modules(self):
        for module in (zoom_module, zoom_auth()):
            source = inspect.getsource(module)
            assert 'os.environ' not in source and 'getenv' not in source, module.__name__

    def test_base_settings_define_the_credentials(self):
        from config.settings import base
        for name in ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET', 'ZOOM_HOST_USER_ID',
                     'ZOOM_HTTP_TIMEOUT_SECONDS', 'ZOOM_HTTP_MAX_ATTEMPTS', 'ZOOM_RETRY_AFTER_CAP_SECONDS'):
            assert hasattr(base, name), name


def _good_with_zoom(**overrides):
    env = dict(GOOD, ZOOM_ACCOUNT_ID='acc', ZOOM_CLIENT_ID='cid', ZOOM_CLIENT_SECRET='sec')
    env.update(overrides)
    return env


class TestProductionGuard:
    def test_production_boots_with_zoom_credentials(self):
        validate_production_settings(_good_with_zoom())

    @pytest.mark.parametrize('name', ['ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET'])
    @pytest.mark.parametrize('value', ['', '   '])
    def test_production_refuses_a_missing_credential(self, name, value):
        with pytest.raises(ImproperlyConfigured, match=name):
            validate_production_settings(_good_with_zoom(**{name: value}))

    def test_the_deploy_check_and_the_boot_guard_name_the_same_settings(self):
        from config.settings import guard
        spec = importlib.util.spec_from_file_location('check_deploy_z1', SCRIPT)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        assert tuple(script.ZOOM_CREDENTIALS) == tuple(guard.ZOOM_CREDENTIAL_SETTINGS)


# ====================================================================== token cache (F0 condition C3)
class TestTokenCache:
    def test_one_token_request_serves_many_calls(self, fake_zoom):
        meeting = zoom_client.create_meeting('Lesson', START)
        zoom_client.get_meeting_status(meeting['meeting_id'])
        zoom_client.delete_meeting(meeting['meeting_id'])
        assert fake_zoom.token_requests == 1

    def test_the_cache_is_keyed_by_account(self, fake_zoom, settings):
        zoom_client.get_access_token()
        settings.ZOOM_ACCOUNT_ID = 'another-account'
        zoom_client.get_access_token()
        assert fake_zoom.token_requests == 2
        assert zoom_auth().token_cache_key('fake-zoom_account_id') != zoom_auth().token_cache_key('another-account')

    def test_ttl_is_expires_in_minus_sixty_seconds(self, fake_zoom, monkeypatch):
        recorded = []
        real_set = cache.set

        def spy_set(key, value, timeout=None, **kw):
            recorded.append((key, timeout))
            return real_set(key, value, timeout, **kw)

        monkeypatch.setattr(zoom_auth().cache, 'set', spy_set)
        fake_zoom.expires_in = 3599
        zoom_client.get_access_token()
        assert (zoom_auth().token_cache_key('fake-zoom_account_id'), 3539) in recorded

    @pytest.mark.parametrize('expires_in', [60, 30, 0, None, 'soon'])
    def test_a_token_too_short_lived_is_used_once_but_never_cached(self, fake_zoom, expires_in):
        fake_zoom.expires_in = expires_in
        assert zoom_client.get_access_token() == fake_zoom.access_token
        zoom_client.get_access_token()
        assert fake_zoom.token_requests == 2

    def test_a_failure_is_never_cached(self, fake_zoom):
        fake_zoom.fail_next('token', 400)
        with pytest.raises(ZoomError):
            zoom_client.get_access_token()
        assert cache.get(zoom_auth().token_cache_key('fake-zoom_account_id')) is None
        assert zoom_client.get_access_token() == fake_zoom.access_token
        assert fake_zoom.token_requests == 2

    def test_a_401_invalidates_the_token_and_retries_once(self, fake_zoom):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.rotate_token()                                   # Zoom revoked the cached token
        assert zoom_client.get_meeting_status(meeting['meeting_id'])['status'] == 'waiting'
        assert fake_zoom.token_requests == 2
        assert cache.get(zoom_auth().token_cache_key('fake-zoom_account_id')) == fake_zoom.access_token

    def test_a_refused_token_leaves_the_cache_even_when_the_refresh_fails(self, fake_zoom):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.rotate_token()
        fake_zoom.fail_next('token', 400)
        with pytest.raises(ZoomError):
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert cache.get(zoom_auth().token_cache_key('fake-zoom_account_id')) is None   # other workers will not reuse it

    def test_a_second_401_is_final(self, fake_zoom):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.fail_next('get', 401)
        fake_zoom.fail_next('get', 401)
        with pytest.raises(ZoomError, match='401'):
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(gets(fake_zoom, '/meetings/')) == 2 and fake_zoom.token_requests == 2

    def test_invalidation_keeps_a_newer_token(self, fake_zoom):
        key = zoom_auth().token_cache_key('fake-zoom_account_id')
        cache.set(key, 'newer-token', 600)
        zoom_auth().invalidate_token('fake-zoom_account_id', 'older-token')
        assert cache.get(key) == 'newer-token'
        zoom_auth().invalidate_token('fake-zoom_account_id', 'newer-token')
        assert cache.get(key) is None

    def test_single_flight_waiter_takes_the_token_another_worker_fetched(self, fake_zoom, monkeypatch):
        key = zoom_auth().token_cache_key('fake-zoom_account_id')
        cache.add(zoom_auth().lock_key(key), 'other-worker', 15)       # another worker is fetching right now

        def other_worker_finishes(seconds):
            fake_zoom.sleeps.append(seconds)
            cache.set(key, 'token-from-the-other-worker', 600)

        monkeypatch.setattr('apps.integrations.zoom_auth._sleep', other_worker_finishes)
        assert zoom_client.get_access_token() == 'token-from-the-other-worker'
        assert fake_zoom.token_requests == 0

    def test_a_waiter_falls_back_to_fetching_itself(self, fake_zoom, settings):
        key = zoom_auth().token_cache_key('fake-zoom_account_id')
        cache.add(zoom_auth().lock_key(key), 'stuck-worker', 15)
        assert zoom_client.get_access_token() == fake_zoom.access_token
        assert fake_zoom.token_requests == 1
        assert 0 < len(fake_zoom.sleeps) and sum(fake_zoom.sleeps) <= settings.ZOOM_TOKEN_WAIT_SECONDS + 0.001

    def test_the_fetch_lock_is_released_after_success_and_failure(self, fake_zoom):
        key = zoom_auth().token_cache_key('fake-zoom_account_id')
        zoom_client.get_access_token()
        assert cache.get(zoom_auth().lock_key(key)) is None
        cache.delete(key)
        fake_zoom.fail_next('token', 400)
        with pytest.raises(ZoomError):
            zoom_client.get_access_token()
        assert cache.get(zoom_auth().lock_key(key)) is None

    def test_a_lock_taken_over_by_another_worker_is_not_released_by_us(self):
        key = 'zoom:lock-ownership-test'
        token = zoom_auth().acquire_lock(key)
        assert token
        cache.set(zoom_auth().lock_key(key), 'someone-else', 15)          # our lock expired, another worker owns it now
        zoom_auth().release_lock(key, token)
        assert cache.get(zoom_auth().lock_key(key)) == 'someone-else'

    def test_without_credentials_the_token_call_raises_instead_of_returning_empty(self, settings):
        settings.ZOOM_ACCOUNT_ID = ''
        with pytest.raises(ZoomError):
            zoom_client.get_access_token()

    def test_the_token_is_never_logged(self, fake_zoom, caplog):
        with caplog.at_level(logging.DEBUG):
            meeting = zoom_client.create_meeting('Lesson', START)
            fake_zoom.rotate_token()
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert 'fake-zoom-access-token' not in caplog.text and 'fake-zoom_client_secret' not in caplog.text


# ====================================================================== retries
class TestRetries:
    def test_a_429_honours_retry_after(self, fake_zoom):
        fake_zoom.rate_limit_next('create', retry_after=3)
        zoom_client.create_meeting('Lesson', START)
        assert fake_zoom.sleeps == [3] and len(posts(fake_zoom)) == 2

    def test_a_retry_after_above_the_cap_is_not_slept_and_is_handed_to_the_caller(self, fake_zoom, settings):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.rate_limit_next('get', retry_after=settings.ZOOM_RETRY_AFTER_CAP_SECONDS + 50)
        with pytest.raises(ZoomError) as err:
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert err.value.retry_after_seconds == settings.ZOOM_RETRY_AFTER_CAP_SECONDS + 50
        assert err.value.status == 429
        assert fake_zoom.sleeps == [] and len(gets(fake_zoom, '/meetings/')) == 1

    def test_a_429_without_retry_after_backs_off(self, fake_zoom, settings):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.rate_limit_next('get')
        zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(fake_zoom.sleeps) == 1 and 0 < fake_zoom.sleeps[0] <= settings.ZOOM_RETRY_AFTER_CAP_SECONDS

    @pytest.mark.parametrize('value', ['soon', '-5', ''])
    def test_a_garbled_retry_after_backs_off_normally(self, fake_zoom, settings, value):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom._special.setdefault('get', []).append(('429', {'Retry-After': value}))
        zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(fake_zoom.sleeps) == 1 and 0 < fake_zoom.sleeps[0] <= settings.ZOOM_RETRY_AFTER_CAP_SECONDS

    def test_a_5xx_is_retried_with_jittered_back_off(self, fake_zoom, settings):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.fail_next('get', 503)
        fake_zoom.fail_next('get', 502)
        assert zoom_client.get_meeting_status(meeting['meeting_id'])['status'] == 'waiting'
        assert len(fake_zoom.sleeps) == 2
        assert all(0 < s <= settings.ZOOM_RETRY_AFTER_CAP_SECONDS for s in fake_zoom.sleeps)

    def test_the_back_off_is_jittered_and_grows(self, monkeypatch):
        draws = iter([1.0, 1.0, 1.0])
        monkeypatch.setattr(zoom_module.random, 'uniform', lambda a, b: b * next(draws))
        first, second, third = (zoom_module.backoff_seconds(n) for n in (1, 2, 3))
        assert first < second < third
        monkeypatch.setattr(zoom_module.random, 'uniform', lambda a, b: a)
        assert zoom_module.backoff_seconds(2) < second                     # full jitter: anywhere in [0, cap]

    def test_attempts_are_bounded(self, fake_zoom, settings):
        meeting = zoom_client.create_meeting('Lesson', START)
        for _ in range(settings.ZOOM_HTTP_MAX_ATTEMPTS + 2):
            fake_zoom.fail_next('get', 500)
        with pytest.raises(ZoomError, match='500'):
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(gets(fake_zoom, '/meetings/')) == settings.ZOOM_HTTP_MAX_ATTEMPTS
        assert len(fake_zoom.sleeps) == settings.ZOOM_HTTP_MAX_ATTEMPTS - 1

    @pytest.mark.parametrize('status', [400, 403, 404, 409, 422])
    def test_other_4xx_are_never_retried(self, fake_zoom, status):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.fail_next('get', status)
        with pytest.raises(ZoomError):
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(gets(fake_zoom, '/meetings/')) == 1 and fake_zoom.sleeps == []

    def test_a_timeout_on_a_read_is_final_for_this_call(self, fake_zoom):
        meeting = zoom_client.create_meeting('Lesson', START)
        fake_zoom.timeout_next('get')
        with pytest.raises(ZoomError):
            zoom_client.get_meeting_status(meeting['meeting_id'])
        assert len(gets(fake_zoom, '/meetings/')) == 1

    def test_token_requests_follow_the_same_policy(self, fake_zoom):
        fake_zoom.fail_next('token', 500)
        assert zoom_client.get_access_token() == fake_zoom.access_token
        assert fake_zoom.token_requests == 2 and len(fake_zoom.sleeps) == 1
        cache.clear()
        fake_zoom.fail_next('token', 401)
        with pytest.raises(ZoomError):
            zoom_client.get_access_token()
        assert fake_zoom.token_requests == 3

    def test_errors_carry_no_provider_body(self, fake_zoom):
        fake_zoom.fail_next('create', 400, body={'code': 300, 'message': 'PROVIDER-SECRET student@x.test'})
        with pytest.raises(ZoomError) as err:
            zoom_client.create_meeting('Lesson', START)
        assert 'PROVIDER-SECRET' not in str(err.value) and 'student@x.test' not in str(err.value)

    def test_fulfilment_honours_a_long_retry_after(self):
        from apps.bookings.services.fulfillment import classify_failure
        assert classify_failure(ZoomError('rate limited', status=429, retry_after_seconds=900)) == (False, 900)
        assert classify_failure(ZoomError('down', status=503)) == (False, None)


# ====================================================================== create_meeting
class TestCreateMeeting:
    def test_recording_is_off_and_the_booking_marker_is_set(self, fake_zoom):
        zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        body = fake_zoom.created[0]
        assert body['settings']['auto_recording'] == 'none'
        marker = zoom_module.booking_marker(BOOKING_ID)
        assert marker in body['agenda'] and BOOKING_ID in marker

    def test_the_result_carries_no_host_start_url(self, fake_zoom):
        room = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert 'start_url' not in room
        assert room['host_user_id'] == 'me' and room['join_url'] and room['meeting_id']

    def test_the_meeting_is_created_for_the_picked_host(self, fake_zoom):
        zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID, host_user_id='host-2@sharonesl.com')
        assert posts(fake_zoom)[0].url.endswith('/users/host-2@sharonesl.com/meetings')

    @pytest.mark.parametrize('host', ['', '../admin', 'a/b', 'me?x=1', 'x' * 200])
    def test_an_unsafe_host_id_is_refused_before_any_call(self, fake_zoom, host):
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID, host_user_id=host)
        assert posts(fake_zoom) == []

    def test_a_timeout_after_zoom_created_the_meeting_finds_it_instead_of_creating_a_second(self, fake_zoom):
        fake_zoom.timeout_next('create', created=True)
        room = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert len(fake_zoom.meetings) == 1 and room['meeting_id'] in fake_zoom.meetings
        assert len(posts(fake_zoom)) == 1 and gets(fake_zoom, '/users/me/meetings')
        assert room['join_url'] and room['password'] == 'fake123'

    def test_a_timeout_before_zoom_created_anything_searches_then_retries(self, fake_zoom):
        fake_zoom.timeout_next('create', created=False)
        room = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert len(fake_zoom.meetings) == 1 and room['meeting_id'] in fake_zoom.meetings
        assert len(posts(fake_zoom)) == 2
        search = gets(fake_zoom, '/users/me/meetings')
        order = [('search' if r is search[0] else 'post') for r in fake_zoom.requests
                 if r is search[0] or r in posts(fake_zoom)]
        assert order == ['post', 'search', 'post']          # identity, not ==: the two POSTs are equal records

    def test_a_5xx_on_create_is_also_ambiguous(self, fake_zoom):
        fake_zoom.fail_next('create', 502)
        zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert len(fake_zoom.meetings) == 1 and gets(fake_zoom, '/users/me/meetings')

    def test_a_429_on_create_is_retried_without_a_search(self, fake_zoom):
        fake_zoom.rate_limit_next('create', retry_after=1)
        zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert gets(fake_zoom, '/users/me/meetings') == [] and len(posts(fake_zoom)) == 2

    def test_without_a_booking_id_an_ambiguous_create_is_never_retried(self, fake_zoom):
        fake_zoom.timeout_next('create', created=False)
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START)
        assert len(posts(fake_zoom)) == 1

    def test_a_failed_search_stops_the_retry(self, fake_zoom):
        fake_zoom.timeout_next('create', created=False)
        fake_zoom.fail_next('list', 400)
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert len(posts(fake_zoom)) == 1

    def test_ambiguous_creates_are_bounded(self, fake_zoom, settings):
        fake_zoom.timeout_next('create', created=False, times=settings.ZOOM_HTTP_MAX_ATTEMPTS + 2)
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        assert len(posts(fake_zoom)) == settings.ZOOM_HTTP_MAX_ATTEMPTS

    def test_search_first_reuses_the_meeting_of_an_earlier_attempt(self, fake_zoom):
        first = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        again = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID, search_first=True)
        assert again['meeting_id'] == first['meeting_id'] and len(posts(fake_zoom)) == 1

    def test_the_search_ignores_other_bookings_and_follows_pages(self, fake_zoom):
        for n in range(5):
            zoom_client.create_meeting('Other', START, booking_id=f'other-{n}')
        mine = zoom_client.create_meeting('Lesson', START, booking_id=BOOKING_ID)
        found = zoom_client.find_meeting_for_booking(BOOKING_ID, page_size=2)
        assert found['meeting_id'] == mine['meeting_id']
        assert len(gets(fake_zoom, '/users/me/meetings')) == 3
        assert zoom_client.find_meeting_for_booking('no-such-booking', page_size=2) is None

    def test_a_marker_is_not_matched_as_a_prefix(self, fake_zoom):
        zoom_client.create_meeting('Other', START, booking_id=BOOKING_ID + '0')
        assert zoom_client.find_meeting_for_booking(BOOKING_ID) is None


# ====================================================================== silent-failure guard + simulation
class TestNoSilentFailure:
    def test_zoom_py_has_no_return_empty_string(self):
        assert 'return ""' not in inspect.getsource(zoom_module) and "return ''" not in inspect.getsource(zoom_module)

    def test_the_guard_allowlist_for_zoom_is_gone(self):
        from guards.test_guard_integrations_silent_failures import ALLOWLIST
        assert 'integrations/zoom.py' not in ALLOWLIST

    def test_simulated_rooms_have_no_host_link_stored_and_a_simulated_start_link(self, simulated_zoom):
        room = zoom_client.create_meeting('t', START, booking_id=BOOKING_ID)
        assert 'start_url' not in room and room['host_user_id'] == 'me'
        assert zoom_client.get_start_url(room['meeting_id']).startswith('https://zoom.us/s/')

    def test_without_credentials_and_simulation_the_start_link_raises(self, settings):
        settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS = False
        with pytest.raises(ZoomError):
            zoom_client.get_start_url('123')
