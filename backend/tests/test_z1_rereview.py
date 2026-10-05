"""
Slice Z1, re-review REQUIRED conditions (the Video SDK migration retires this legacy path later; until then it is live):

1. the "Mark reviewed" admin action is gated like the sibling money admins and refuses self-review
2. who may obtain a staff host link == who can review it (no row that nobody can clear)
3. docs/SETTLEMENT_PATHS.md describes the hold; ZOOM_ATTENDANCE.md says it is legacy
"""
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking, HostLinkIssue
from apps.integrations.zoom import zoom_client

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


# ====================================================================== 2. who may obtain the link
@pytest.mark.django_db
class TestIssuerPredicate:
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

    def test_the_tutor_still_gets_their_own_link_without_a_row(self, live):
        assert client_for(live.teacher.user).get(URL.format(live.id)).status_code == 200
        assert not HostLinkIssue.objects.exists()


# ====================================================================== 3. docs
class TestDocs:
    def test_settlement_paths_describes_the_hold(self):
        text = (DOCS / 'SETTLEMENT_PATHS.md').read_text(encoding='utf-8')
        assert 'HostLinkIssue' in text and 'Mark reviewed' in text
        for word in ('student_no_show', 'student_late_cancelled', 'disputes', 'refunds'):
            assert word in text

    def test_zoom_attendance_says_the_hold_is_legacy(self):
        text = (DOCS / 'ZOOM_ATTENDANCE.md').read_text(encoding='utf-8')
        assert 'retire' in text and 'Video SDK' in text and 'V5' in text
