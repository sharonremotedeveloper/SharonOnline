"""Slice N1a: notifications app core - models, registry, notify(), preferences, keys (plan §3.2, docs/NOTIFICATIONS.md §2)."""
import uuid
from datetime import datetime, timezone as dt_timezone
from unittest import mock

import pytest
from django.db import IntegrityError, transaction
from django.test import TestCase

import factories as f
from apps.notifications import registry, service
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.registry import EMAIL, IN_APP, Kind, Rendered
from apps.notifications.rendering import local_time, one_line
from apps.notifications.service import InvalidNotification, booking_generation, booking_key, notify

ES = Notification.EmailState


def on_commit():
    return TestCase.captureOnCommitCallbacks(execute=True)


def _plain(ctx_user, payload, booking):
    return Rendered(subject='Hello', html='<p>Hello</p>', text='Hello', title='Hello', body='Hello body')


@pytest.fixture
def kinds(monkeypatch):
    """Ad-hoc kinds for the machinery (registered for this test only)."""
    made = {
        'optional_both': Kind('optional_both', 'booking', frozenset({EMAIL, IN_APP}), _plain),
        'mandatory_both': Kind('mandatory_both', 'cancellation', frozenset({EMAIL, IN_APP}), _plain),
        'email_only': Kind('email_only', 'payment', frozenset({EMAIL}), _plain),
        'in_app_only': Kind('in_app_only', 'booking', frozenset({IN_APP}), _plain),
    }
    for name, kind in made.items():
        monkeypatch.setitem(registry._REGISTRY, name, kind)
    return made


@pytest.fixture
def no_delivery(monkeypatch):
    """Record enqueues instead of delivering."""
    from apps.notifications import tasks
    calls = []
    monkeypatch.setattr(tasks.deliver_notification_task, 'delay', lambda nid: calls.append(nid))
    return calls


# ====================================================================== registry
class TestRegistry:
    def test_mandatory_set_lives_in_code(self):
        assert registry.MANDATORY_CATEGORIES >= {'security', 'payment', 'cancellation', 'refund', 'bank_change',
                                                 'strike', 'suspension', 'vetting_outcome'}

    def test_mandatory_follows_the_category(self):
        assert Kind('k_one', 'refund', frozenset({EMAIL}), _plain).mandatory is True
        assert Kind('k_two', 'booking', frozenset({EMAIL}), _plain).mandatory is False

    def test_email_only(self):
        assert Kind('k_one', 'payment', frozenset({EMAIL}), _plain).email_only is True
        assert Kind('k_two', 'payment', frozenset({EMAIL, IN_APP}), _plain).email_only is False

    def test_register_rejects_duplicates_bad_names_channels_and_categories(self, monkeypatch):
        monkeypatch.setattr(registry, '_REGISTRY', {})
        registry.register(Kind('fine_kind', 'booking', frozenset({EMAIL}), _plain))
        with pytest.raises(ValueError):
            registry.register(Kind('fine_kind', 'booking', frozenset({EMAIL}), _plain))
        with pytest.raises(ValueError):
            registry.register(Kind('Bad Name', 'booking', frozenset({EMAIL}), _plain))
        with pytest.raises(ValueError):
            registry.register(Kind('no_channel', 'booking', frozenset(), _plain))
        with pytest.raises(ValueError):
            registry.register(Kind('odd_channel', 'booking', frozenset({'sms'}), _plain))
        with pytest.raises(ValueError):
            registry.register(Kind('odd_category', 'gossip', frozenset({EMAIL}), _plain))

    def test_unknown_kind_raises(self):
        with pytest.raises(registry.UnknownKind):
            registry.get('no_such_kind')

    def test_builtin_kinds_are_registered(self):
        names = {k.name for k in registry.all_kinds()}
        assert {'admin_alert', 'sample_lesson_notice'} <= names
        assert registry.get('admin_alert').mandatory is True


# ====================================================================== rendering helpers
@pytest.mark.django_db
class TestRendering:
    WHEN = datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc)

    def test_time_in_the_recipients_zone(self):
        user = f.make_student(timezone='Asia/Tokyo')
        text = local_time(self.WHEN, user)
        assert '18:00' in text and 'Asia/Tokyo' in text

    @pytest.mark.parametrize('tz', ['', 'Not/AZone', '../../etc/passwd'])
    def test_blank_or_invalid_zone_is_utc_with_a_visible_label(self, tz):
        user = f.make_student()
        user.timezone = tz
        text = local_time(self.WHEN, user)
        assert '09:00' in text and 'UTC' in text and 'time zone' in text.lower()

    def test_one_line_removes_header_injection(self):
        assert one_line('Hi\r\nBcc: evil@example.test\tthere') == 'Hi Bcc: evil@example.test there'
        assert len(one_line('x' * 1000)) <= 200


# ====================================================================== notify()
@pytest.mark.django_db
class TestNotify:
    def test_creates_row_with_rendered_payload_persisted(self, kinds, no_delivery):
        user = f.make_student()
        with on_commit():
            n = notify(user, 'optional_both', key='k:1', payload={'booking_id': str(uuid.uuid4())})
        n.refresh_from_db()
        assert (n.kind, n.in_app, n.email_state) == ('optional_both', True, ES.PENDING)
        assert (n.rendered_subject, n.rendered_html, n.rendered_text) == ('Hello', '<p>Hello</p>', 'Hello')
        assert (n.title, n.body) == ('Hello', 'Hello body')
        assert no_delivery == [str(n.pk)]

    def test_enqueue_happens_only_on_commit(self, kinds, no_delivery):
        user = f.make_student()
        with on_commit() as callbacks:
            notify(user, 'optional_both', key='k:2', payload={})
            assert no_delivery == []
        assert len(callbacks) == 1 and len(no_delivery) == 1

    def test_rolled_back_caller_leaves_nothing(self, kinds, no_delivery):
        user = f.make_student()
        with on_commit():
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    notify(user, 'optional_both', key='k:3', payload={})
                    raise RuntimeError('caller failed')
        assert not Notification.objects.filter(idempotency_key='k:3').exists()
        assert no_delivery == []

    def test_duplicate_key_returns_existing_row_and_does_not_enqueue_again(self, kinds, no_delivery):
        user = f.make_student()
        with on_commit():
            first = notify(user, 'optional_both', key='k:4', payload={})
        with on_commit():
            again = notify(user, 'optional_both', key='k:4', payload={})
        assert again.pk == first.pk
        assert Notification.objects.filter(idempotency_key='k:4').count() == 1
        assert no_delivery == [str(first.pk)]

    def test_duplicate_insert_race_never_poisons_the_callers_transaction(self, kinds, no_delivery):
        """The insert loses a race (IntegrityError inside notify's savepoint): the caller's transaction stays usable."""
        user = f.make_student()
        existing = Notification.objects.create(user=user, kind='optional_both', idempotency_key='k:5', title='t')
        real_filter = Notification.objects.filter

        def blind_filter(*args, **kwargs):            # the pre-check misses the row (written by a concurrent worker)
            if kwargs.get('idempotency_key') == 'k:5':
                return Notification.objects.none()
            return real_filter(*args, **kwargs)

        with transaction.atomic():
            with mock.patch.object(Notification.objects, 'filter', side_effect=blind_filter):
                got = notify(user, 'optional_both', key='k:5', payload={})
            assert got.pk == existing.pk
            f.make_student()                           # the caller's transaction still works
        assert Notification.objects.filter(idempotency_key='k:5').count() == 1

    def test_optional_email_off_by_preference(self, kinds, no_delivery):
        user = f.make_student()
        NotificationPreference.objects.create(user=user, email_by_kind={'optional_both': False})
        with on_commit():
            n = notify(user, 'optional_both', key='k:6', payload={})
        assert (n.email_state, n.in_app) == (ES.SKIPPED, True)
        assert n.rendered_html == '' and no_delivery == []

    def test_mandatory_kind_always_emails_despite_preference(self, kinds, no_delivery):
        user = f.make_student()
        NotificationPreference.objects.create(user=user, email_by_kind={'mandatory_both': False},
                                              in_app_by_kind={'mandatory_both': False})
        with on_commit():
            n = notify(user, 'mandatory_both', key='k:7', payload={})
        assert (n.email_state, n.in_app) == (ES.PENDING, True)
        assert no_delivery == [str(n.pk)]

    def test_optional_in_app_off_keeps_the_email_but_hides_the_item(self, kinds, no_delivery):
        user = f.make_student()
        NotificationPreference.objects.create(user=user, in_app_by_kind={'optional_both': False})
        n = notify(user, 'optional_both', key='k:8', payload={})
        assert (n.email_state, n.in_app) == (ES.PENDING, False)

    def test_nothing_wanted_creates_nothing(self, kinds, no_delivery):
        user = f.make_student()
        NotificationPreference.objects.create(user=user, email_by_kind={'optional_both': False},
                                              in_app_by_kind={'optional_both': False})
        assert notify(user, 'optional_both', key='k:9', payload={}) is None
        assert not Notification.objects.exists()

    def test_email_only_kind_is_never_an_in_app_item(self, kinds, no_delivery):
        user = f.make_student()
        n = notify(user, 'email_only', key='k:10', payload={})
        assert (n.in_app, n.email_state) == (False, ES.PENDING)

    def test_in_app_only_kind_skips_email(self, kinds, no_delivery):
        user = f.make_student()
        n = notify(user, 'in_app_only', key='k:11', payload={})
        assert (n.in_app, n.email_state, n.rendered_subject) == (True, ES.SKIPPED, '')

    def test_unknown_kind_raises(self, no_delivery):
        with pytest.raises(registry.UnknownKind):
            notify(f.make_student(), 'nope', key='k:12', payload={})

    @pytest.mark.parametrize('payload', [
        {'student_review': 'x'}, {'dossier_text': 'x'}, {'reset_token': 'x'}, {'note': 'x'}, {'email': 'a@b.test'},
        {'nested': {'a': 1}}, {'items': [1, 2]}, {'Bad-Key': 1}, {'long': 'x' * 200}, {'amount': 1.5},
    ])
    def test_payload_is_ids_only(self, kinds, no_delivery, payload):
        with pytest.raises(InvalidNotification):
            notify(f.make_student(), 'optional_both', key='k:13', payload=payload)

    def test_payload_accepts_ids_and_converts_uuids(self, kinds, no_delivery):
        bid = uuid.uuid4()
        n = notify(f.make_student(), 'optional_both', key='k:14',
                   payload={'booking_id': bid, 'attempts': 3, 'permanent': True, 'step': 'room', 'none': None})
        n.refresh_from_db()
        assert n.payload == {'booking_id': str(bid), 'attempts': 3, 'permanent': True, 'step': 'room', 'none': None}

    @pytest.mark.parametrize('key', ['', 'has space', 'line\nbreak', 'x' * 201, 'café'])
    def test_key_must_be_a_safe_header_value(self, kinds, no_delivery, key):
        with pytest.raises(InvalidNotification):
            notify(f.make_student(), 'optional_both', key=key, payload={})

    def test_booking_fk_is_stored(self, kinds, no_delivery):
        tutor = f.make_teacher_profile()
        student = f.make_student()
        booking = f.make_booking(tutor, student, status='confirmed')
        n = notify(student, 'optional_both', key='k:15', payload={}, booking=booking)
        assert n.booking_id == booking.pk

    def test_broker_down_at_commit_is_logged_and_left_for_the_sweep(self, kinds, monkeypatch, caplog):
        from apps.notifications import tasks

        def down(nid):
            raise ConnectionError('broker down')

        monkeypatch.setattr(tasks.deliver_notification_task, 'delay', down)
        user = f.make_student()
        with on_commit():
            n = notify(user, 'optional_both', key='k:16', payload={})
        n.refresh_from_db()
        assert n.email_state == ES.PENDING
        assert str(n.pk) in caplog.text and 'broker down' not in caplog.text


# ====================================================================== keys
@pytest.mark.django_db
class TestKeys:
    def test_generation_token_is_booking_and_reschedule_count(self):
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), status='confirmed')
        assert booking_generation(booking) == f'{booking.pk}:0'
        booking.reschedule_count = 2
        assert booking_generation(booking) == f'{booking.pk}:2'

    def test_booking_key_rearms_after_reschedule(self):
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), status='confirmed')
        before = booking_key('reminder:24h', booking, 'student')
        booking.reschedule_count = 1
        after = booking_key('reminder:24h', booking, 'student')
        assert before == f'reminder:24h:{booking.pk}:0:student' and before != after

    def test_booking_key_without_role(self):
        booking = f.make_booking(f.make_teacher_profile(), f.make_student(), status='confirmed')
        assert booking_key('memo-warn', booking) == f'memo-warn:{booking.pk}:0'


# ====================================================================== model
@pytest.mark.django_db
class TestModel:
    def test_idempotency_key_is_unique(self):
        user = f.make_student()
        Notification.objects.create(user=user, kind='x', idempotency_key='dup')
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(user=user, kind='x', idempotency_key='dup')

    def test_list_index_exists(self):
        names = {tuple(i.fields) for i in Notification._meta.indexes}
        assert ('user', 'read_at', '-created_at') in names

    def test_created_at_uses_the_clock_seam(self, frozen_clock):
        n = Notification.objects.create(user=f.make_student(), kind='x', idempotency_key='clock')
        assert n.created_at == frozen_clock.now

    def test_email_states(self):
        assert set(ES.values) == {'pending', 'sending', 'sent', 'retryable', 'failed', 'skipped', 'bounced'}


# ====================================================================== queues / beat
class TestQueues:
    def test_notification_tasks_route_to_the_notifications_queue(self):
        from config.celery_schedule import CELERY_TASK_ROUTES
        for name in ('deliver_notification_task', 'sweep_notifications_task', 'purge_notifications_task'):
            assert CELERY_TASK_ROUTES[f'apps.notifications.tasks.{name}'] == {'queue': 'notifications'}

    def test_beat_entries(self):
        from config.celery_schedule import CELERY_BEAT_SCHEDULE
        by_task = {v['task']: v for v in CELERY_BEAT_SCHEDULE.values()}
        sweep = by_task['apps.notifications.tasks.sweep_notifications_task']
        assert sweep['schedule'] == 120.0 and sweep['options']['queue'] == 'notifications'
        assert sweep['options']['expires'] < 120
        purge = by_task['apps.notifications.tasks.purge_notifications_task']
        assert purge['options']['queue'] == 'notifications'

    def test_app_installed(self):
        from django.conf import settings
        assert 'apps.notifications' in settings.INSTALLED_APPS

    def test_task_names_are_explicit(self):
        from apps.notifications import tasks
        assert tasks.deliver_notification_task.name == 'apps.notifications.tasks.deliver_notification_task'
        assert tasks.sweep_notifications_task.name == 'apps.notifications.tasks.sweep_notifications_task'
        assert tasks.purge_notifications_task.name == 'apps.notifications.tasks.purge_notifications_task'
        assert service.notify is notify
