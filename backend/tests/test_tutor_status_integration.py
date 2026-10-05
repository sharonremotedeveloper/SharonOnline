"""
T1a: the places that used to write `is_verified` / `is_active` directly now go through the tutor status service:
strikes, the legacy admin verify endpoint (temporary shim until T1b), the Django admin, the serializers and the seeds.
"""
import io

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

import factories as f
from apps.teachers.models import TeacherProfile, TeacherStatusChange, TeacherStrike
from apps.teachers.strikes import add_strike

pytestmark = pytest.mark.django_db
KINDS = (TeacherStrike.Kind.NO_SHOW, TeacherStrike.Kind.LATE_CANCEL, TeacherStrike.Kind.MEMO_SLA)


# ------------------------------------------------------------------ strikes map to `suspended`
class TestStrikes:
    def test_the_limit_suspends_through_the_service(self, settings):
        settings.STRIKE_LIMIT = 3
        tutor = f.make_teacher_profile(status='approved')
        for kind in KINDS:
            add_strike(tutor, kind)
        assert tutor.status == 'suspended' and tutor.is_active is False and tutor.sla_strikes == 3   # caller copy fresh
        change = TeacherStatusChange.objects.get(teacher=tutor)
        assert (change.from_status, change.to_status, change.actor) == ('approved', 'suspended', 'system:strikes')

    def test_below_the_limit_nothing_changes(self, settings):
        settings.STRIKE_LIMIT = 3
        tutor = f.make_teacher_profile(status='approved')
        add_strike(tutor, KINDS[0])
        assert tutor.status == 'approved' and not TeacherStatusChange.objects.exists()

    def test_an_already_suspended_tutor_is_a_status_no_op(self, settings):
        settings.STRIKE_LIMIT = 1
        tutor = f.make_teacher_profile(status='approved')
        add_strike(tutor, KINDS[0])
        assert add_strike(tutor, KINDS[1]) == 2
        tutor.refresh_from_db()
        assert tutor.status == 'suspended' and tutor.sla_strikes == 2
        assert TeacherStatusChange.objects.filter(teacher=tutor).count() == 1

    @pytest.mark.parametrize('status', ['applied', 'submitted', 'in_review', 'changes_requested', 'rejected'])
    def test_a_tutor_who_is_not_approved_only_records_the_strike(self, settings, status):
        settings.STRIKE_LIMIT = 1
        tutor = f.make_teacher_profile(status=status)
        assert add_strike(tutor, KINDS[0]) == 1
        tutor.refresh_from_db()
        assert tutor.status == status and tutor.sla_strikes == 1
        assert TeacherStrike.objects.filter(teacher=tutor).count() == 1 and not TeacherStatusChange.objects.exists()

    def test_a_strike_inside_a_booking_lock_does_not_lock_bookings_again(self, settings):
        from django.db import transaction
        from apps.bookings.models import Booking
        settings.STRIKE_LIMIT = 1
        tutor = f.make_teacher_profile(status='approved')
        booking = f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED)
        with transaction.atomic():
            locked = Booking.objects.select_for_update().get(pk=booking.pk)
            add_strike(locked.teacher, KINDS[0], booking=locked)
        tutor.refresh_from_db()
        assert tutor.status == 'suspended'


# ------------------------------------------------------------------ legacy PATCH /admin/teachers/<id>/verify/
# T1b rebuilt it on the explicit review actions (no path-walking): tests/test_t1b_review_actions.py::TestLegacyVerify.
def verify(admin, profile_id, body):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client.patch(f'/api/v1/admin/teachers/{profile_id}/verify/', body, format='json')


def test_legacy_verify_records_the_admin_on_every_row(admin_user):
    profile = f.make_teacher_profile(status='applied')
    rubric = {'pronunciation': 4, 'teaching_presence': 4, 'professionalism': 4, 'credentials': 4}
    assert verify(admin_user, profile.id, {'is_verified': True, 'rubric': rubric}).status_code == 200
    rows = list(TeacherStatusChange.objects.filter(teacher=profile).values_list('actor_user', 'reason'))
    assert len(rows) == 3 and all(row == (admin_user.pk, 'legacy-verify') for row in rows)


# ------------------------------------------------------------------ Django admin and serializers
def test_admin_change_page_renders_with_read_only_status(admin_user, settings):
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    client = APIClient()
    client.force_login(admin_user)
    profile = f.make_teacher_profile(status='approved')
    res = client.get(reverse('admin:teachers_teacherprofile_change', args=[profile.pk]))
    assert res.status_code == 200
    form = res.context['adminform'].form
    for name in ('status', 'is_verified', 'is_active'):
        assert name not in form.fields
    assert client.get(reverse('admin:teachers_teacherprofile_changelist') + '?status__exact=approved').status_code == 200


def test_admin_cannot_change_audit_rows(admin_user):
    from django.contrib import admin
    model_admin = admin.site._registry[TeacherStatusChange]
    request = type('R', (), {'user': admin_user})()
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


def test_public_serializer_pins_is_verified_read_only():
    from apps.teachers.serializers import TeacherListSerializer
    field = TeacherListSerializer().fields['is_verified']
    assert field.read_only is True


# ------------------------------------------------------------------ seeds
def test_seed_data_creates_approved_tutors_with_a_baseline_audit_row():
    call_command('seed_data', stdout=io.StringIO())
    tutors = TeacherProfile.objects.all()
    assert tutors and all(t.status == 'approved' and t.training_completed_at for t in tutors)
    assert TeacherStatusChange.objects.filter(from_status='', to_status='approved').count() == tutors.count()
    call_command('seed_data', stdout=io.StringIO())                     # idempotent: no second profile or audit row
    assert TeacherStatusChange.objects.count() == tutors.count()


def test_seed_phase41_creates_submitted_applications():
    call_command('seed_data', stdout=io.StringIO())
    approved = set(TeacherProfile.objects.values_list('pk', flat=True))
    call_command('seed_phase41_data', stdout=io.StringIO())
    applicants = TeacherProfile.objects.exclude(pk__in=approved)
    assert applicants and all(t.status == 'submitted' for t in applicants)
