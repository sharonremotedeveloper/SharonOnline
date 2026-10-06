"""
Slice Z1 (PRP 12.1a): the host start link (ZAK) expires, so it is never stored or copied into calendar events again; the tutor
(or staff) fetches a fresh one when the classroom opens. HostPicker + Booking.zoom_host_user_id; fulfilment searches for an
earlier attempt's meeting before creating a new one on a retry. Zoom is tests/fakes.py::FakeZoom (no network).
"""
import logging
from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.integrations.zoom import zoom_client
from apps.payments.models import FulfillmentDispatch
from migration_helpers import migrate_and_build

S = Booking.Status
St = FulfillmentDispatch.StepState
URL = '/api/v1/bookings/{}/host-link/'


def fulfillment():
    from apps.bookings.services import fulfillment as module
    return module


def host_picker():
    from apps.integrations.zoom_hosts import host_picker as picker
    return picker


def client_for(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user)
    return c


@pytest.fixture
def live(fake_zoom):
    """A confirmed lesson starting in 5 minutes with a real (fake) Zoom room."""
    booking = f.make_booking(status=S.CONFIRMED, start=timezone.now() + timedelta(minutes=5))
    room = zoom_client.create_meeting('Lesson', '2026-11-01T10:00:00Z', booking_id=str(booking.id))
    Booking.objects.filter(pk=booking.pk).update(zoom_meeting_id=room['meeting_id'], zoom_join_url=room['join_url'])
    booking.refresh_from_db()
    return booking


# ====================================================================== the endpoint
@pytest.mark.django_db
class TestHostLinkEndpoint:
    def test_the_tutor_gets_a_fresh_start_link_every_time(self, live, fake_zoom):
        c = client_for(live.teacher.user)
        first, second = c.get(URL.format(live.id)), c.get(URL.format(live.id))
        assert first.status_code == 200 and second.status_code == 200
        assert first.data['start_url'] != second.data['start_url'] and 'zak=' in first.data['start_url']
        assert first.data['meeting_id'] == live.zoom_meeting_id
        assert first['Cache-Control'] == 'no-store'
        live.refresh_from_db()
        assert live.zoom_start_url == ''                       # fetched, never stored

    def test_staff_may_fetch_it(self, live):
        assert client_for(f.make_admin()).get(URL.format(live.id)).status_code == 200

    def test_the_booking_student_is_refused(self, live):
        res = client_for(live.student).get(URL.format(live.id))
        assert res.status_code == 403 and 'start_url' not in res.data

    @pytest.mark.parametrize('who', ['other_tutor', 'other_student'])
    def test_non_participants_get_404(self, live, who):
        user = f.make_teacher_profile().user if who == 'other_tutor' else f.make_student()
        res = client_for(user).get(URL.format(live.id))
        assert res.status_code == 404 and 'start_url' not in res.data

    def test_an_unknown_booking_is_404(self, live):
        import uuid
        assert client_for(live.teacher.user).get(URL.format(uuid.uuid4())).status_code == 404

    def test_anonymous_is_refused(self, live):
        assert client_for(None).get(URL.format(live.id)).status_code in (401, 403)

    def test_a_lesson_without_a_room_is_409(self, live):
        Booking.objects.filter(pk=live.pk).update(zoom_meeting_id='')
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 409 and res.data['code'] == 'no_meeting'

    @pytest.mark.parametrize('status', [S.CANCELLED_BY_STUDENT, S.COMPLETED, S.PENDING_PAYMENT, S.DISPUTED])
    def test_a_lesson_that_is_not_live_is_409(self, live, status):
        Booking.objects.filter(pk=live.pk).update(status=status)
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 409 and res.data['code'] == 'not_live'

    def test_in_progress_is_live(self, live):
        Booking.objects.filter(pk=live.pk).update(status=S.IN_PROGRESS)
        assert client_for(live.teacher.user).get(URL.format(live.id)).status_code == 200

    def test_an_ended_lesson_is_409(self, live):
        past = timezone.now() - timedelta(hours=2)
        Booking.objects.filter(pk=live.pk).update(start_time_utc=past, end_time_utc=past + timedelta(minutes=25))
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 409 and res.data['code'] == 'lesson_ended'

    def test_a_meeting_zoom_no_longer_has_is_409(self, live, fake_zoom):
        del fake_zoom.meetings[live.zoom_meeting_id]
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 409 and res.data['code'] == 'meeting_missing'

    def test_a_zoom_outage_is_502_without_provider_details(self, live, fake_zoom, settings):
        for _ in range(settings.ZOOM_HTTP_MAX_ATTEMPTS):
            fake_zoom.fail_next('get', 500, body={'message': 'PROVIDER-BODY'})
        res = client_for(live.teacher.user).get(URL.format(live.id))
        assert res.status_code == 502 and res.data['code'] == 'zoom_unavailable'
        assert 'PROVIDER-BODY' not in str(res.data)

    def test_logs_carry_ids_only(self, live, caplog):
        with caplog.at_level(logging.DEBUG):
            res = client_for(live.teacher.user).get(URL.format(live.id))
        assert str(live.id) in caplog.text
        assert 'zak=' not in caplog.text and res.data['start_url'] not in caplog.text
        assert live.teacher.user.email not in caplog.text

    def test_the_endpoint_is_throttled(self, live, settings, monkeypatch):
        from rest_framework.throttling import ScopedRateThrottle
        from apps.bookings.host_link_views import BookingHostLinkView
        assert BookingHostLinkView.throttle_scope in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        monkeypatch.setattr(ScopedRateThrottle, 'THROTTLE_RATES', {'zoom_host_link': '2/hour'})
        c = client_for(live.teacher.user)
        codes = [c.get(URL.format(live.id)).status_code for _ in range(3)]
        assert codes == [200, 200, 429]


# ====================================================================== the stored link is gone
@pytest.mark.django_db
class TestNoStoredHostLink:
    def test_fulfilment_stores_no_start_url_and_records_the_host(self, fake_zoom):
        booking = f.make_booking(status=S.CONFIRMED)
        assert fulfillment().run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_meeting_id and booking.zoom_join_url
        assert booking.zoom_start_url == '' and booking.zoom_host_user_id == 'me'
        assert fake_zoom.created[0]['settings']['auto_recording'] == 'none'
        assert str(booking.id) in fake_zoom.created[0]['agenda']

    def test_the_tutor_detail_payload_has_no_host_link(self, teacher_user, student_user):
        booking = f.make_booking(teacher_user, student_user, zoom_meeting_id='123', zoom_join_url='https://zoom.us/j/123',
                                 zoom_start_url='https://zoom.us/s/123?zak=LEGACY')
        data = client_for(teacher_user.user).get(f'/api/v1/bookings/{booking.id}/').data
        assert data['zoom_start_url'] == '' and data['zoom_url'] == 'https://zoom.us/j/123'
        assert 'LEGACY' not in str(data)

    def test_the_calendar_event_carries_only_the_join_link(self, fake_google, teacher_user, student_user):
        from apps.integrations.google_calendar import sync_booking_to_teacher_gcal
        user = teacher_user.user
        user.google_calendar_token = {'access_token': fake_google.access_token}
        user.save(update_fields=['google_calendar_token'])
        booking = f.make_booking(teacher_user, student_user, zoom_meeting_id='123', zoom_join_url='https://zoom.us/j/123',
                                 zoom_start_url='https://zoom.us/s/123?zak=LEGACY')
        booking.refresh_from_db()
        assert sync_booking_to_teacher_gcal(booking)
        event = next(iter(fake_google.events.values()))
        assert 'https://zoom.us/j/123' in event['description'] and 'zak' not in str(event)

    def test_a_reschedule_clears_the_host_id(self, teacher_user, student_user):
        from apps.bookings.services.rescheduling import MOVED_FIELDS
        from payment_helpers import captured
        from test_reschedule import open_slots, resched
        assert 'zoom_host_user_id' in MOVED_FIELDS
        b = captured(teacher_user, student_user, 30 * 60)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='111', zoom_host_user_id='host-1')
        with mock.patch('apps.bookings.services.rescheduling.cleanup_zoom_meeting'), \
                mock.patch('apps.bookings.services.rescheduling.dispatch_booking_fulfillment'):
            assert resched(student_user, b, open_slots(teacher_user)[0]).status_code == 200
        b.refresh_from_db()
        assert b.zoom_meeting_id == '' and b.zoom_host_user_id is None


# ====================================================================== HostPicker
@pytest.mark.django_db
class TestHostPicker:
    def test_default_is_me(self, settings):
        booking = f.make_booking()
        assert host_picker().pick_host(booking) == 'me'

    def test_the_setting_chooses_the_host(self, settings, fake_zoom):
        settings.ZOOM_HOST_USER_ID = 'host-1@sharonesl.com'
        booking = f.make_booking(status=S.CONFIRMED)
        assert fulfillment().run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_host_user_id == 'host-1@sharonesl.com'
        assert any(r.url.endswith('/users/host-1@sharonesl.com/meetings') for r in fake_zoom.requests)

    def test_the_field_is_nullable_and_defaults_to_none(self):
        field = Booking._meta.get_field('zoom_host_user_id')
        assert field.null and f.make_booking().zoom_host_user_id is None


# ====================================================================== fulfilment retry searches first
def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _failed_zoom_step(booking):
    FulfillmentDispatch.objects.create(booking=booking, status=FulfillmentDispatch.Status.RETRYABLE, attempts=1,
                                       zoom_state=St.FAILED, next_retry_at=timezone.now() - timedelta(seconds=1))


@pytest.mark.django_db
class TestFulfilmentRetrySearchesFirst:
    def test_a_retried_zoom_step_reuses_the_meeting_an_earlier_attempt_created(self, fake_zoom):
        booking = f.make_booking(status=S.CONFIRMED)
        earlier = zoom_client.create_meeting('Lesson', _iso(booking.start_time_utc), booking_id=str(booking.id))
        _failed_zoom_step(booking)
        assert fulfillment().run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_meeting_id == earlier['meeting_id'] and len(fake_zoom.created) == 1

    def test_the_old_room_of_a_rescheduled_lesson_is_never_reused(self, fake_zoom):
        booking = f.make_booking(status=S.CONFIRMED)
        old = zoom_client.create_meeting('Lesson', _iso(booking.start_time_utc - timedelta(days=1)),
                                         booking_id=str(booking.id))          # not yet deleted by the cleanup task
        _failed_zoom_step(booking)
        assert fulfillment().run_fulfillment(booking.id) == 'succeeded'
        booking.refresh_from_db()
        assert booking.zoom_meeting_id != old['meeting_id'] and len(fake_zoom.created) == 2

    def test_a_first_attempt_does_not_search(self, fake_zoom):
        booking = f.make_booking(status=S.CONFIRMED)
        fulfillment().run_fulfillment(booking.id)
        assert not [r for r in fake_zoom.requests if r.method == 'GET' and '/users/' in r.url]

    def test_a_timeout_during_fulfilment_never_leaves_two_rooms(self, fake_zoom):
        booking = f.make_booking(status=S.CONFIRMED)
        fake_zoom.timeout_next('create', created=True)
        assert fulfillment().run_fulfillment(booking.id) == 'succeeded'
        assert len(fake_zoom.meetings) == 1


# ====================================================================== data migration
@pytest.fixture
def price_catalog(db):
    """A transactional test may run after another one flushed the migration-seeded catalog (ERR-133)."""
    from decimal import Decimal
    from apps.payments.models import LessonPrice
    for currency, amount in (('USD', '9.00'), ('EUR', '8.50'), ('ZAR', '162.00'), ('JPY', '1350.00')):
        LessonPrice.objects.get_or_create(currency=currency, defaults={'amount': Decimal(amount)})


def _migration_case():
    def build(old_apps):
        Booking_ = old_apps.get_model('bookings', 'Booking')
        b = f.make_booking()
        Booking_.objects.filter(pk=b.pk).update(zoom_start_url='https://zoom.us/s/1?zak=OLD')
        return b

    holder = {}

    def build_and_keep(old_apps):
        holder['id'] = build(old_apps).pk

    def verify(new_apps):
        return new_apps.get_model('bookings', 'Booking').objects.get(pk=holder['id']).zoom_start_url

    return build_and_keep, verify


BEFORE = [('bookings', '0014_booking_zoom_host_user_id')]
AFTER = [('bookings', '0015_clear_stored_zoom_start_urls')]


@pytest.mark.django_db(transaction=True)
def test_the_data_migration_blanks_stored_host_links(price_catalog):
    build, verify = _migration_case()
    assert migrate_and_build(BEFORE, AFTER, build, verify) == ''


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_the_data_migration_blanks_stored_host_links_on_postgres(price_catalog):
    if connection.vendor != 'postgresql':
        pytest.skip('populated-DB data migration on PostgreSQL (run in the Postgres CI job)')
    build, verify = _migration_case()
    assert migrate_and_build(BEFORE, AFTER, build, verify) == ''


@pytest.mark.django_db(transaction=True)
def test_the_data_migration_reverses_as_a_no_op(price_catalog):
    assert migrate_and_build(AFTER, BEFORE) is not None
