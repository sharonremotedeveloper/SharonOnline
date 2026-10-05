"""
Slice Z1, QA round 1 (conditions of the approval):

* host-link window (`ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE`, 409 `too_early`)
* #2 search-before-create after ANY earlier attempt (a crashed worker leaves zoom_state PENDING, not FAILED)
* #3 a staff-issued host link is audited (`HostLinkIssue`) and holds escrow release until an admin reviews it
* #4 a cache outage degrades Zoom auth to a direct fetch; an unexpected error in the host-link path is a structured 502
* #5 the token lock outlives the worst-case fetch; #7 marker search is date-bounded
* NITs: pure-dot host ids, a 201 without an id, meeting ids validated before they enter a URL
"""
import logging
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.integrations import zoom_auth
from apps.integrations.zoom import ZoomError, zoom_client
from apps.payments.models import FulfillmentDispatch

S = Booking.Status
FD = FulfillmentDispatch.Status
URL = '/api/v1/bookings/{}/host-link/'
START = '2026-11-01T10:00:00Z'


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def lesson_in(minutes, **fields):
    start = timezone.now() + timedelta(minutes=minutes)
    return f.make_booking(status=S.CONFIRMED, start=start, **fields)


@pytest.fixture
def live(fake_zoom):
    booking = lesson_in(5)
    room = zoom_client.create_meeting('Lesson', START, booking_id=str(booking.id))
    Booking.objects.filter(pk=booking.pk).update(zoom_meeting_id=room['meeting_id'], zoom_join_url=room['join_url'])
    booking.refresh_from_db()
    return booking


class RaisingCache:
    """A cache whose every call fails (Redis down)."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError(f'redis down: {name} secret-detail')
        return fail


# ====================================================================== host-link window
@pytest.mark.django_db
class TestHostLinkWindow:
    def test_before_the_window_is_409_too_early(self, live):
        Booking.objects.filter(pk=live.pk).update(start_time_utc=timezone.now() + timedelta(minutes=60),
                                                  end_time_utc=timezone.now() + timedelta(minutes=85))
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 409 and res.data['code'] == 'too_early'
        assert 'start_url' not in res.data

    def test_the_default_window_is_fifteen_minutes(self, live, settings):
        assert settings.ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE == 15
        Booking.objects.filter(pk=live.pk).update(start_time_utc=timezone.now() + timedelta(minutes=14),
                                                  end_time_utc=timezone.now() + timedelta(minutes=39))
        assert client_for(live.teacher.user).get(URL.format(live.id)).status_code == 200

    def test_the_window_is_a_setting(self, live, settings):
        settings.ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE = 5
        Booking.objects.filter(pk=live.pk).update(start_time_utc=timezone.now() + timedelta(minutes=10),
                                                  end_time_utc=timezone.now() + timedelta(minutes=35))
        assert client_for(live.teacher.user).get(URL.format(live.id)).data['code'] == 'too_early'

    def test_a_lesson_in_progress_after_its_start_is_open(self, live):
        Booking.objects.filter(pk=live.pk).update(start_time_utc=timezone.now() - timedelta(minutes=10),
                                                  end_time_utc=timezone.now() + timedelta(minutes=15))
        assert client_for(live.teacher.user).get(URL.format(live.id)).status_code == 200

    def test_the_setting_is_documented_in_env_example(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[2] / '.env.example').read_text(encoding='utf-8')
        assert 'ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE' in text


# ====================================================================== #2 search after any earlier attempt
@pytest.mark.django_db
class TestSearchAfterAnyEarlierAttempt:
    def test_a_reclaimed_claim_searches_before_creating(self, fake_zoom):
        from apps.bookings.services.fulfillment import run_fulfillment
        booking = f.make_booking(status=S.CONFIRMED)
        earlier = zoom_client.create_meeting('Lesson', booking.start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                             booking_id=str(booking.id))
        # The first worker died after Zoom built the room: RUNNING, attempts=1, zoom step never marked failed.
        FulfillmentDispatch.objects.create(booking=booking, status=FD.RUNNING, attempts=1, claim_token='dead-worker',
                                           claimed_at=timezone.now() - timedelta(hours=1))
        assert run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_meeting_id == earlier['meeting_id'] and len(fake_zoom.created) == 1
        assert FulfillmentDispatch.objects.get(booking=booking).attempts == 2

    def test_a_retryable_row_with_a_pending_zoom_step_also_searches(self, fake_zoom):
        from apps.bookings.services.fulfillment import run_fulfillment
        booking = f.make_booking(status=S.CONFIRMED)
        earlier = zoom_client.create_meeting('Lesson', booking.start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                             booking_id=str(booking.id))
        FulfillmentDispatch.objects.create(booking=booking, status=FD.RETRYABLE, attempts=2,
                                           next_retry_at=timezone.now() - timedelta(seconds=1))
        assert run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_meeting_id == earlier['meeting_id']

    def test_the_very_first_attempt_does_not_search(self, fake_zoom):
        from apps.bookings.services.fulfillment import run_fulfillment
        booking = f.make_booking(status=S.CONFIRMED)
        run_fulfillment(booking.id)
        assert not [r for r in fake_zoom.requests if r.method == 'GET' and '/users/' in r.url]


# ====================================================================== #3 staff host link
@pytest.mark.django_db
class TestStaffHostLinkAudit:
    def test_a_staff_issued_link_leaves_a_persistent_unreviewed_audit_row(self, live):
        from apps.bookings.models import HostLinkIssue
        admin = f.make_admin()
        assert client_for(admin).get(URL.format(live.id)).status_code == 200
        row = HostLinkIssue.objects.get(booking=live)
        assert row.issued_by_id == admin.pk and row.reviewed_at is None and row.reviewed_by_id is None

    def test_the_tutors_own_link_is_not_audited(self, live):
        from apps.bookings.models import HostLinkIssue
        assert client_for(live.teacher.user).get(URL.format(live.id)).status_code == 200
        assert not HostLinkIssue.objects.exists()

    def test_a_refused_staff_request_leaves_no_row(self, live):
        from apps.bookings.models import HostLinkIssue
        Booking.objects.filter(pk=live.pk).update(zoom_meeting_id='')
        assert client_for(f.make_admin()).get(URL.format(live.id)).status_code == 409
        assert not HostLinkIssue.objects.exists()

    def test_the_audit_row_is_ids_only_in_the_log(self, live, caplog):
        admin = f.make_admin()
        with caplog.at_level(logging.DEBUG):
            client_for(admin).get(URL.format(live.id))
        assert admin.email not in caplog.text and 'zak=' not in caplog.text

    def test_an_unreviewed_staff_hosted_lesson_is_not_releasable(self, live):
        from apps.bookings.models import HostLinkIssue
        from apps.payments.services.settlement import attendance_verified_for_release
        Booking.objects.filter(pk=live.pk).update(status=S.COMPLETED)
        live.refresh_from_db()
        assert attendance_verified_for_release(live, 25) is True
        HostLinkIssue.objects.create(booking=live, issued_by=f.make_admin())
        assert attendance_verified_for_release(live, 25) is False
        Booking.objects.filter(pk=live.pk).update(status=S.STUDENT_NO_SHOW)
        live.refresh_from_db()
        assert attendance_verified_for_release(live, 25) is False
        Booking.objects.filter(pk=live.pk).update(status=S.STUDENT_LATE_CANCELLED)
        live.refresh_from_db()
        assert attendance_verified_for_release(live, 25) is False

    def test_review_releases_the_hold_and_records_who(self, live):
        from apps.bookings.models import HostLinkIssue
        from apps.bookings.services.host_link import review_host_link_issues
        from apps.payments.services.settlement import attendance_verified_for_release
        Booking.objects.filter(pk=live.pk).update(status=S.COMPLETED)
        live.refresh_from_db()
        HostLinkIssue.objects.create(booking=live, issued_by=f.make_admin())
        reviewer = f.make_admin()
        assert review_host_link_issues(HostLinkIssue.objects.all(), reviewer) == 1
        row = HostLinkIssue.objects.get()
        assert row.reviewed_by_id == reviewer.pk and row.reviewed_at is not None
        assert attendance_verified_for_release(live, 25) is True
        assert review_host_link_issues(HostLinkIssue.objects.all(), reviewer) == 0     # already reviewed: no second stamp

    def test_the_release_task_holds_a_staff_hosted_lesson(self, live):
        from apps.bookings.models import HostLinkIssue
        from apps.payments.tasks import release_cleared_escrow_task
        past = timezone.now() - timedelta(days=3)
        Booking.objects.filter(pk=live.pk).update(status=S.COMPLETED, start_time_utc=past, end_time_utc=past + timedelta(minutes=25))
        HostLinkIssue.objects.create(booking=live, issued_by=f.make_admin())
        release_cleared_escrow_task()
        live.refresh_from_db()
        assert live.escrow_cleared_at is None

    def test_the_audit_model_is_registered_in_the_admin_with_a_review_action(self):
        from django.contrib import admin
        from apps.bookings.models import HostLinkIssue
        model_admin = admin.site._registry[HostLinkIssue]
        assert 'mark_reviewed' in {a for a in model_admin.get_actions(mock.Mock(user=mock.Mock(has_perm=lambda p: True)))}


# ====================================================================== #4 cache outage
@pytest.mark.django_db
class TestCacheOutage:
    def test_zoom_auth_falls_back_to_a_direct_fetch(self, fake_zoom, monkeypatch, caplog):
        monkeypatch.setattr(zoom_auth, 'cache', RaisingCache())
        with caplog.at_level(logging.DEBUG):
            assert zoom_client.get_access_token() == fake_zoom.access_token
            assert zoom_client.get_access_token() == fake_zoom.access_token
        assert fake_zoom.token_requests == 2                       # nothing cached, nothing locked
        assert 'secret-detail' not in caplog.text and 'ConnectionError' in caplog.text

    def test_a_whole_call_works_with_the_cache_down(self, fake_zoom, monkeypatch):
        monkeypatch.setattr(zoom_auth, 'cache', RaisingCache())
        room = zoom_client.create_meeting('Lesson', START, booking_id='b-1')
        assert zoom_client.get_meeting_status(room['meeting_id'])['status'] == 'waiting'
        fake_zoom.rotate_token()
        assert zoom_client.get_meeting_status(room['meeting_id'])['status'] == 'waiting'      # 401 path: invalidate swallowed

    def test_each_cache_step_degrades_on_its_own(self, fake_zoom, monkeypatch):
        real = zoom_auth.cache

        class Partial:
            def __init__(self, broken):
                self.broken = broken

            def __getattr__(self, name):
                if name == self.broken:
                    def fail(*a, **kw):
                        raise ConnectionError('down')
                    return fail
                return getattr(real, name)

        for broken in ('get', 'add', 'set', 'delete'):
            monkeypatch.setattr(zoom_auth, 'cache', Partial(broken))
            real.clear()
            assert zoom_client.get_access_token() == fake_zoom.access_token, broken
            zoom_auth.invalidate_token('acc', 'tok')
            zoom_auth.release_lock('k', 'owner')

    def test_an_unexpected_error_in_the_host_link_path_is_a_structured_502(self, live, monkeypatch, caplog):
        monkeypatch.setattr(zoom_client, 'get_start_url', mock.Mock(side_effect=RuntimeError('boom secret-detail')))
        with caplog.at_level(logging.DEBUG):
            res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 502 and res.data['code'] == 'zoom_unavailable'
        assert 'secret-detail' not in caplog.text and 'secret-detail' not in str(res.data)


# ====================================================================== #5 lock TTL, #7 bounded search
class TestLockAndSearch:
    def test_the_lock_outlives_the_worst_case_token_fetch(self, settings):
        worst = settings.ZOOM_HTTP_MAX_ATTEMPTS * (settings.ZOOM_HTTP_TIMEOUT_SECONDS + settings.ZOOM_RETRY_AFTER_CAP_SECONDS)
        assert zoom_auth.lock_seconds() > worst

    def test_the_lock_is_taken_with_that_ttl(self, monkeypatch):
        seen = []
        real = zoom_auth.cache
        monkeypatch.setattr(zoom_auth.cache, 'add', lambda k, v, t=None, **kw: seen.append(t) or real.add(k, v, t))
        assert zoom_auth.acquire_lock('k')
        assert seen == [zoom_auth.lock_seconds()]

    def test_the_marker_search_is_bounded_by_date(self, fake_zoom):
        zoom_client.find_meeting_for_booking('b-1', start_time='2026-11-01T10:00:00Z')
        params = [r.params for r in fake_zoom.requests if r.method == 'GET' and '/users/' in r.url][0]
        assert params['from'] == '2026-10-31' and params['to'] == '2026-11-02'

    def test_without_a_start_time_the_search_is_not_bounded(self, fake_zoom):
        zoom_client.find_meeting_for_booking('b-1')
        params = [r.params for r in fake_zoom.requests if r.method == 'GET' and '/users/' in r.url][0]
        assert 'from' not in params and 'to' not in params

    def test_the_create_search_passes_the_start_time(self, fake_zoom):
        fake_zoom.timeout_next('create', created=True)
        zoom_client.create_meeting('Lesson', START, booking_id='b-1')
        params = [r.params for r in fake_zoom.requests if r.method == 'GET' and '/users/' in r.url][0]
        assert params['from'] == '2026-10-31'


# ====================================================================== NITs
class TestIdValidation:
    @pytest.mark.parametrize('host', ['.', '..', '...'])
    def test_pure_dot_host_ids_are_refused(self, fake_zoom, host):
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START, booking_id='b-1', host_user_id=host)
        assert not [r for r in fake_zoom.requests if '/users/' in r.url]

    def test_a_201_without_an_id_is_an_error_not_the_string_none(self, fake_zoom, monkeypatch):
        monkeypatch.setattr(fake_zoom, '_create', lambda host, body: __import__('fakes').FakeResponse(201, {'join_url': 'x'}))
        with pytest.raises(ZoomError):
            zoom_client.create_meeting('Lesson', START, booking_id='b-1')

    @pytest.mark.parametrize('meeting_id', ['../users', 'a/b', '1?x=2', '', ' 1', 'x' * 100, '..'])
    def test_an_unsafe_meeting_id_never_reaches_a_url(self, fake_zoom, meeting_id):
        for call in (zoom_client.get_meeting_status, zoom_client.get_start_url, zoom_client.get_past_instances,
                     zoom_client.delete_meeting):
            with pytest.raises(ZoomError):
                call(meeting_id)
        assert fake_zoom.requests == []

    def test_a_normal_meeting_id_and_a_uuid_style_id_pass(self, fake_zoom):
        room = zoom_client.create_meeting('Lesson', START, booking_id='b-1')
        assert zoom_client.get_meeting_status(room['meeting_id'])['status'] == 'waiting'
        with pytest.raises(ZoomError):          # valid shape, unknown meeting: a 404, not a validation error
            zoom_client.get_meeting_status('abc_DEF=12-3')
