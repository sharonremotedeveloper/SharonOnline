"""
Slice Z1, re-review conditions (run on the integration branch with N1a merged):

1. the "Mark reviewed" admin action is gated like the sibling money admins and refuses self-review
2. who may obtain a staff host link == who can review it; a staff alert is raised (N1a `alert_staff`)
3. docs/SETTLEMENT_PATHS.md describes the hold
4. held rows cannot starve the escrow release batch
NITs: reviewed_by implies reviewed_at (constraint); the admin lists unreviewed rows first
"""
import logging
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import AttendanceAudit, Booking, HostLinkIssue
from apps.integrations.zoom import zoom_client
from payment_helpers import captured

S = Booking.Status
URL = '/api/v1/bookings/{}/host-link/'
START = '2026-11-01T10:00:00Z'
DOCS = Path(__file__).resolve().parents[2] / 'docs'


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def live(fake_zoom):
    start = timezone.now() + timedelta(minutes=5)
    booking = f.make_booking(status=S.CONFIRMED, start=start)
    room = zoom_client.create_meeting('Lesson', START, booking_id=str(booking.id))
    Booking.objects.filter(pk=booking.pk).update(zoom_meeting_id=room['meeting_id'], zoom_join_url=room['join_url'])
    booking.refresh_from_db()
    return booking


def plain_admin():
    """An admin who can use Django admin but is NOT a superuser."""
    return f.make_admin(is_superuser=False)


def model_admin():
    return admin.site._registry[HostLinkIssue]


def request_as(user):
    request = RequestFactory().get('/admin/')
    request.user = user
    return request


def open_issue(booking, issuer=None):
    return HostLinkIssue.objects.create(booking=booking, issued_by=issuer or plain_admin())


# ====================================================================== 1. admin permission
@pytest.mark.django_db
class TestReviewPermission:
    def run_action(self, user, queryset):
        with mock.patch.object(model_admin(), 'message_user'):
            model_admin().mark_reviewed(request_as(user), queryset)

    def test_non_admin_staff_is_refused(self, live):
        row = open_issue(live)
        support = f.make_user('teacher', is_staff=True)           # staff flag, but not the admin role
        assert not model_admin().has_review_permission(request_as(support))
        with pytest.raises(PermissionDenied):
            self.run_action(support, HostLinkIssue.objects.filter(pk=row.pk))
        row.refresh_from_db()
        assert row.reviewed_at is None

    def test_the_action_is_hidden_from_non_admin_staff(self, live):
        support = f.make_user('teacher', is_staff=True)
        assert 'mark_reviewed' not in model_admin().get_actions(request_as(support))
        assert 'mark_reviewed' in model_admin().get_actions(request_as(plain_admin()))

    def test_an_inactive_admin_is_refused(self, live):
        row = open_issue(live)
        gone = f.make_admin(is_superuser=False, is_active=False)
        assert not model_admin().has_review_permission(request_as(gone))
        with pytest.raises(PermissionDenied):
            self.run_action(gone, HostLinkIssue.objects.filter(pk=row.pk))

    def test_a_role_admin_without_the_staff_flag_is_refused(self, live):
        row = open_issue(live)
        outsider = f.make_admin(is_superuser=False, is_staff=False)
        with pytest.raises(PermissionDenied):
            self.run_action(outsider, HostLinkIssue.objects.filter(pk=row.pk))

    def test_the_issuer_cannot_review_their_own_link(self, live):
        issuer = plain_admin()
        row = open_issue(live, issuer)
        with pytest.raises(PermissionDenied):
            self.run_action(issuer, HostLinkIssue.objects.filter(pk=row.pk))
        row.refresh_from_db()
        assert row.reviewed_at is None and row.reviewed_by_id is None

    def test_one_self_issued_row_in_the_selection_refuses_the_whole_action(self, live):
        issuer = plain_admin()
        mine, theirs = open_issue(live, issuer), open_issue(live)
        with pytest.raises(PermissionDenied):
            self.run_action(issuer, HostLinkIssue.objects.filter(pk__in=[mine.pk, theirs.pk]))
        assert not HostLinkIssue.objects.filter(reviewed_at__isnull=False).exists()

    def test_another_admin_may_review(self, live):
        row = open_issue(live)
        reviewer = plain_admin()
        self.run_action(reviewer, HostLinkIssue.objects.filter(pk=row.pk))
        row.refresh_from_db()
        assert row.reviewed_by_id == reviewer.pk and row.reviewed_at is not None

    def test_a_superuser_may_review_even_their_own_link(self, live):
        root = f.make_admin()                                           # is_superuser=True
        row = open_issue(live, root)
        self.run_action(root, HostLinkIssue.objects.filter(pk=row.pk))
        row.refresh_from_db()
        assert row.reviewed_by_id == root.pk

    def test_an_issuer_who_was_deleted_does_not_block_review(self, live):
        row = HostLinkIssue.objects.create(booking=live, issued_by=None)
        reviewer = plain_admin()
        self.run_action(reviewer, HostLinkIssue.objects.filter(pk=row.pk))
        row.refresh_from_db()
        assert row.reviewed_at is not None


# ====================================================================== 2. who may obtain the link, and the alert
@pytest.mark.django_db
class TestIssuerPredicateAndAlert:
    def test_an_admin_role_without_django_admin_access_gets_no_link_and_no_row(self, live):
        outsider = f.make_admin(is_superuser=False, is_staff=False)
        assert client_for(outsider).get(URL.format(live.id)).status_code == 404
        assert not HostLinkIssue.objects.exists()

    def test_staff_flag_without_the_admin_role_gets_no_link(self, live):
        support = f.make_user('teacher', is_staff=True)
        assert client_for(support).get(URL.format(live.id)).status_code == 404
        assert not HostLinkIssue.objects.exists()

    def test_a_reviewer_capable_admin_gets_the_link_and_an_open_row(self, live):
        admin_user = plain_admin()
        assert client_for(admin_user).get(URL.format(live.id)).status_code == 200
        assert HostLinkIssue.objects.get().issued_by_id == admin_user.pk

    def test_the_issuer_predicate_is_the_reviewer_predicate(self):
        from apps.bookings.services import host_link
        for user in (plain_admin(), f.make_admin(), f.make_admin(is_staff=False), f.make_user('teacher', is_staff=True),
                     f.make_admin(is_active=False)):
            assert host_link.can_review(user) == model_admin().has_review_permission(request_as(user))

    def test_a_staff_alert_is_raised_with_ids_only(self, live):
        admin_user = plain_admin()
        with mock.patch('apps.bookings.services.host_link.alert_staff') as alert:
            assert client_for(admin_user).get(URL.format(live.id)).status_code == 200
        alert.assert_called_once()
        args, kwargs = alert.call_args
        assert args == ('host_link_issued_to_staff',)
        assert kwargs['key'] == f'admin:host-link:{live.id}'
        assert kwargs['payload'] == {'booking_id': str(live.id), 'issued_by': str(admin_user.pk)}

    def test_the_alert_is_not_raised_for_the_tutor_or_a_refused_request(self, live):
        with mock.patch('apps.bookings.services.host_link.alert_staff') as alert:
            client_for(live.teacher.user).get(URL.format(live.id))
            Booking.objects.filter(pk=live.pk).update(zoom_meeting_id='')
            client_for(plain_admin()).get(URL.format(live.id))
        alert.assert_not_called()

    def test_the_alert_runs_after_the_row_exists(self, live):
        seen = []
        with mock.patch('apps.bookings.services.host_link.alert_staff',
                        side_effect=lambda *a, **k: seen.append(HostLinkIssue.objects.count())):
            client_for(plain_admin()).get(URL.format(live.id))
        assert seen == [1]

    def test_the_real_alert_notifies_the_other_admins(self, live):
        from apps.notifications.models import Notification
        issuer, other = plain_admin(), plain_admin()
        assert client_for(issuer).get(URL.format(live.id)).status_code == 200
        assert Notification.objects.filter(user=other, kind='admin_alert').exists()

    def test_the_alert_code_has_a_title_and_does_not_change_the_snapshot(self):
        from apps.notifications.builtin_kinds import ALERT_TITLES, _example_admin_alert
        assert 'host_link_issued_to_staff' in ALERT_TITLES
        assert _example_admin_alert(mock.Mock(pk='b'))['alert'] == 'fulfilment_failed'

    def test_a_failing_alert_does_not_break_the_link(self, live):
        with mock.patch('apps.bookings.services.host_link.alert_staff', side_effect=RuntimeError('x')):
            res = client_for(plain_admin()).get(URL.format(live.id))
        assert res.status_code == 200 and HostLinkIssue.objects.count() == 1


# ====================================================================== 3. docs
class TestDocs:
    def test_settlement_paths_describes_the_hold(self):
        text = (DOCS / 'SETTLEMENT_PATHS.md').read_text(encoding='utf-8')
        assert 'HostLinkIssue' in text and 'Mark reviewed' in text
        for word in ('student_no_show', 'student_late_cancelled', 'disputes', 'refunds'):
            assert word in text

    def test_zoom_attendance_no_longer_defers_the_alert_and_notes_the_uuid_encoding(self):
        text = (DOCS / 'ZOOM_ATTENDANCE.md').read_text(encoding='utf-8')
        assert 'host_link_issued_to_staff' in text and 'double' in text.lower() and 'numeric' in text.lower()


# ====================================================================== 4. held rows do not starve the release batch
@pytest.mark.django_db
class TestReleaseBatch:
    def test_held_rows_are_not_even_candidates(self, teacher_user, student_user, caplog):
        from apps.payments import tasks as payment_tasks
        issuer = plain_admin()
        base = timezone.now() - timedelta(days=5)
        for i in range(51):                                             # more than the 50-row batch
            start = base - timedelta(hours=i)
            held = f.make_booking(teacher_user, student_user, status=S.COMPLETED, start=start)
            HostLinkIssue.objects.create(booking=held, issued_by=issuer)
        good = captured(teacher_user, student_user, 10)
        end = timezone.now() - timedelta(hours=30)
        Booking.objects.filter(pk=good.pk).update(status=S.COMPLETED, start_time_utc=end - timedelta(minutes=25), end_time_utc=end)
        AttendanceAudit.objects.create(booking=good, participant_email=teacher_user.user.email, total_minutes=25)
        real = payment_tasks.attendance_verified_for_release
        with mock.patch.object(payment_tasks, 'attendance_verified_for_release', side_effect=real) as check, \
                caplog.at_level(logging.WARNING):
            result = payment_tasks.release_cleared_escrow_task()
        assert result['cleared_count'] == 1
        assert check.call_count == 1                                    # only the releasable booking was ever examined
        assert any('awaiting attendance review' in r.getMessage() and '51' in r.getMessage() for r in caplog.records)

    def test_a_reviewed_row_no_longer_excludes_the_booking(self, teacher_user, student_user):
        from apps.bookings.services.host_link import review_host_link_issues
        from apps.payments import tasks as payment_tasks
        good = captured(teacher_user, student_user, 10)
        end = timezone.now() - timedelta(hours=30)
        Booking.objects.filter(pk=good.pk).update(status=S.COMPLETED, start_time_utc=end - timedelta(minutes=25), end_time_utc=end)
        AttendanceAudit.objects.create(booking=good, participant_email=teacher_user.user.email, total_minutes=25)
        HostLinkIssue.objects.create(booking=good, issued_by=plain_admin())
        assert payment_tasks.release_cleared_escrow_task()['cleared_count'] == 0
        review_host_link_issues(HostLinkIssue.objects.all(), plain_admin())
        assert payment_tasks.release_cleared_escrow_task()['cleared_count'] == 1


# ====================================================================== NITs
@pytest.mark.django_db
class TestModelAndAdminList:
    def test_a_reviewer_without_a_review_time_is_rejected_by_the_database(self, live):
        with pytest.raises(IntegrityError), transaction.atomic():
            HostLinkIssue.objects.create(booking=live, issued_by=plain_admin(), reviewed_by=plain_admin())

    def test_a_review_time_without_a_reviewer_is_allowed(self, live):
        """The reviewer account may be deleted later (SET_NULL), so the constraint is one-directional."""
        row = HostLinkIssue.objects.create(booking=live, issued_by=plain_admin(), reviewed_at=timezone.now())
        assert row.reviewed_by_id is None

    def test_a_deleted_reviewer_does_not_break_the_row(self, live):
        reviewer = plain_admin()
        row = HostLinkIssue.objects.create(booking=live, issued_by=plain_admin(), reviewed_at=timezone.now(), reviewed_by=reviewer)
        reviewer.delete()
        row.refresh_from_db()
        assert row.reviewed_by_id is None and row.reviewed_at is not None

    def test_the_admin_lists_unreviewed_rows_first(self, live):
        issuer = plain_admin()
        old_reviewed = HostLinkIssue.objects.create(booking=live, issued_by=issuer, reviewed_at=timezone.now(),
                                                    reviewed_by=plain_admin())
        newest_open = open_issue(live, issuer)
        older_open = open_issue(live, issuer)
        HostLinkIssue.objects.filter(pk=older_open.pk).update(created_at=timezone.now() - timedelta(days=1))
        request = request_as(f.make_admin())
        order = [r.pk for r in model_admin().get_queryset(request)]
        assert order[:2] == [newest_open.pk, older_open.pk] and order[-1] == old_reviewed.pk
