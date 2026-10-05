"""
T1a Architect sign-off conditions (2026-10-04): stale full-row saves, instance writes to the generated flags, the legacy
verify shim's fake reinstatement, create_teacher_profile actor rules, admin add audit row.
"""
import pytest
from rest_framework.test import APIClient

import factories as f
from apps.teachers.models import TeacherProfile, TeacherStatusChange, TeacherStrike
from apps.teachers.strikes import add_strike
from apps.teachers.vetting import TransitionNotPermitted, create_teacher_profile, transition_teacher

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ M1: a stale full-row save cannot undo a suspension
def test_power_backup_patch_after_a_strike_suspension_keeps_the_suspension(settings):
    settings.STRIKE_LIMIT = 1
    tutor = f.make_teacher_profile(status='approved')
    user = tutor.user
    stale = user.teacher_profile                        # cached on the user object the request will carry: approved
    assert stale.status == 'approved'
    add_strike(TeacherProfile.objects.get(pk=tutor.pk), TeacherStrike.Kind.NO_SHOW)    # suspends via the service
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch('/api/v1/teachers/profile/power-backup/', {'has_inverter_backup': True}, format='json')
    assert res.status_code == 200
    tutor.refresh_from_db()
    assert tutor.status == 'suspended' and tutor.is_active is False
    assert tutor.sla_strikes == 1 and tutor.has_inverter_backup is True
    assert TeacherStatusChange.objects.filter(teacher=tutor).count() == 1


def test_a_stale_full_save_writes_other_fields_but_never_status_or_strikes():
    tutor = f.make_teacher_profile(status='approved')
    stale = TeacherProfile.objects.get(pk=tutor.pk)
    transition_teacher(tutor, 'suspended', actor='system:test')
    TeacherProfile.objects.filter(pk=tutor.pk).update(sla_strikes=3)
    stale.bio = 'new bio'
    stale.save()
    tutor.refresh_from_db()
    assert (tutor.status, tutor.sla_strikes, tutor.bio) == ('suspended', 3, 'new bio')


def test_changing_status_on_an_instance_and_saving_the_row_raises():
    tutor = f.make_teacher_profile(status='approved')
    tutor.status = 'suspended'
    with pytest.raises(ValueError):
        tutor.save()
    tutor.refresh_from_db()
    assert tutor.status == 'approved'
    tutor.sla_strikes = 5
    with pytest.raises(ValueError):
        tutor.save()


def test_a_loaded_instance_with_a_changed_status_raises_on_a_full_save():
    tutor = f.make_teacher_profile(status='approved')
    loaded = TeacherProfile.objects.get(pk=tutor.pk)             # from_db remembers the loaded status
    loaded.status = 'rejected'
    with pytest.raises(ValueError):
        loaded.save()


def test_a_full_save_after_the_service_refreshed_the_instance_is_fine():
    tutor = f.make_teacher_profile(status='approved')
    transition_teacher(tutor, 'suspended', actor='system:test')
    tutor.bio = 'x'
    tutor.save()                                         # instance knows the new status: no false alarm
    tutor.refresh_from_db()
    assert (tutor.status, tutor.bio) == ('suspended', 'x')


def test_assigning_a_generated_flag_on_an_instance_raises():
    tutor = f.make_teacher_profile(status='approved')
    for name in ('is_verified', 'is_active'):
        with pytest.raises(AttributeError):
            setattr(tutor, name, False)
    tutor.refresh_from_db()                              # Django's own loading still works
    loaded = TeacherProfile.objects.only('id', 'status').get(pk=tutor.pk)
    assert (tutor.is_active, loaded.is_verified) == (True, True)    # deferred load works too


def test_bulk_create_still_returns_the_generated_flags():
    users = [f.make_user(role='teacher') for _ in range(2)]
    rows = TeacherProfile.objects.bulk_create([TeacherProfile(user=u, status='suspended') for u in users])
    assert all(TeacherProfile.objects.get(pk=r.pk).is_active is False for r in rows)


# ------------------------------------------------------------------ M2: the legacy shim never fakes a reinstatement
def verify(admin, profile_id, body):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client.patch(f'/api/v1/admin/teachers/{profile_id}/verify/', body, format='json')


def test_rejecting_a_suspended_tutor_takes_the_direct_edge_and_writes_no_fake_approval(admin_user):
    """T1b: the staff-only suspended -> rejected edge (Anesu 2026-10-05) replaces the earlier 409."""
    tutor = f.make_teacher_profile(status='suspended')
    res = verify(admin_user, tutor.id, {'is_verified': False, 'rejection_reason': 'x'})
    assert res.status_code == 200
    assert list(TeacherStatusChange.objects.filter(teacher=tutor).values_list('to_status', flat=True)) == ['rejected']


def test_rejecting_a_live_tutor_through_vetting_is_409_from_the_locked_row(admin_user):
    """A live tutor is suspended first (that returns the lessons left without a tutor); the vetting endpoint refuses."""
    tutor = f.make_teacher_profile(status='approved')
    assert verify(admin_user, tutor.id, {'is_verified': False}).status_code == 409
    tutor.refresh_from_db()
    assert tutor.status == 'approved' and not TeacherStatusChange.objects.exists()


@pytest.mark.parametrize('start', ['in_review', 'submitted', 'applied', 'changes_requested', 'suspended'])
def test_reject_paths_never_pass_through_approved(admin_user, start):
    tutor = f.make_teacher_profile(status=start)
    assert verify(admin_user, tutor.id, {'is_verified': False}).status_code == 200
    rows = list(TeacherStatusChange.objects.filter(teacher=tutor).values_list('to_status', flat=True))
    assert rows[-1] == 'rejected' and 'approved' not in rows


# ------------------------------------------------------------------ minor 2: who may create a profile in which status
def test_the_tutor_may_only_create_an_applied_profile():
    user = f.make_user(role='teacher')
    with pytest.raises(TransitionNotPermitted):
        create_teacher_profile(user, status='approved', actor=user)
    assert create_teacher_profile(user, actor=user).status == 'applied'


def test_a_stranger_may_not_create_a_profile_for_someone_else():
    with pytest.raises(TransitionNotPermitted):
        create_teacher_profile(f.make_user(role='teacher'), actor=f.make_student())
    assert not TeacherProfile.objects.exists()


@pytest.mark.parametrize('actor', ['staff', 'system'])
def test_staff_and_system_may_create_any_status(actor):
    who = f.make_admin() if actor == 'staff' else 'system:test'
    assert create_teacher_profile(f.make_user(role='teacher'), status='approved', actor=who).status == 'approved'


# ------------------------------------------------------------------ minor 6: admin "add" writes the baseline audit row
def test_admin_add_profile_records_a_baseline_audit_row(admin_user, settings):
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    from django.urls import reverse
    client = APIClient()
    client.force_login(admin_user)
    user = f.make_user(role='teacher')
    data = {'user': str(user.pk), 'headline': 'h', 'accent': 'ZA', 'bio': '', 'specialties': '["FreeTalk"]', 'price_per_25min_usd': '9.00',
            'eskom_area_id': '', 'avatar_url': '', 'intro_audio_url': '', 'intro_video_url': '', 'intro_video_thumbnail': '',
            'tefl_certificate_url': '', 'rating_avg': '5.00', 'rating_count': '0',
            'availabilities-TOTAL_FORMS': '0', 'availabilities-INITIAL_FORMS': '0',
            'status_changes-TOTAL_FORMS': '0', 'status_changes-INITIAL_FORMS': '0'}
    res = client.post(reverse('admin:teachers_teacherprofile_add'), data)
    errors = res.context and [res.context['adminform'].form.errors, [fs.formset.errors for fs in res.context['inline_admin_formsets']]]
    assert res.status_code == 302, errors
    profile = TeacherProfile.objects.get(user=user)
    change = TeacherStatusChange.objects.get(teacher=profile)
    assert (profile.status, change.from_status, change.to_status, change.actor_user) == ('applied', '', 'applied', admin_user)
