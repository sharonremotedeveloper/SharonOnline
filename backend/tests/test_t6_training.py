"""Slice T6: tutor onboarding training (plan sections 3.9, 9). Infrastructure only: the module CONTENT is Sharon's.
`TeacherProfile.training_completed_at` is set by the service when every published required module is done (never by hand);
the gate itself (`bookable()`, `TUTOR_TRAINING_GATE_ENABLED`) is T1b. The backfill must run before the gate is enabled."""
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.teachers import training
from apps.teachers.models import TeacherProfile, TrainingModule, TrainingProgress

pytestmark = pytest.mark.django_db


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def module(slug, position=1, *, required=True, published=True, **fields):
    return TrainingModule.objects.create(slug=slug, title=slug.title(), summary='s', body=f'# {slug}', position=position,
                                         is_required=required, is_published=published, **fields)


def untrained(status='approved'):
    return f.make_teacher_profile(status=status, training_completed_at=None)


# ------------------------------------------------------------------ models
def test_slug_is_unique_and_progress_is_one_row_per_tutor_and_module():
    m = module('safety')
    with pytest.raises(IntegrityError):
        TrainingModule.objects.create(slug='safety', title='x', position=2)
    tutor = untrained()
    TrainingProgress.objects.create(teacher=tutor, module=m)
    with pytest.raises(IntegrityError):
        TrainingProgress.objects.create(teacher=tutor, module=m)


def test_modules_are_ordered_by_position():
    module('b', 2)
    module('a', 1)
    assert list(TrainingModule.objects.values_list('slug', flat=True)) == ['a', 'b']


# ------------------------------------------------------------------ service
class TestCompletion:
    def test_completing_the_last_required_module_sets_the_date_once(self):
        tutor = untrained()
        a, b = module('a', 1), module('b', 2)
        assert training.complete_module(tutor, a).training_completed_at is None
        done = training.complete_module(tutor, b)
        assert done.training_completed_at is not None
        first = TeacherProfile.objects.get(pk=tutor.pk).training_completed_at
        assert first is not None
        training.complete_module(tutor, b)                                   # repeat: no change
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at == first

    def test_completing_a_module_twice_is_idempotent(self):
        tutor, m = untrained(), module('a')
        training.complete_module(tutor, m)
        training.complete_module(tutor, m)
        assert TrainingProgress.objects.filter(teacher=tutor).count() == 1

    def test_with_no_required_published_modules_nobody_completes_training(self):
        tutor = untrained()
        optional = module('opt', required=False)
        draft = module('draft', 2, published=False)
        training.complete_module(tutor, optional)
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at is None
        with pytest.raises(training.TrainingNotAvailable):
            training.complete_module(tutor, draft)                           # an unpublished module cannot be completed

    def test_optional_and_unpublished_modules_do_not_block_completion(self):
        tutor = untrained()
        module('a', 1)
        module('opt', 2, required=False)
        module('draft', 3, published=False)
        training.complete_module(tutor, TrainingModule.objects.get(slug='a'))
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at is not None

    def test_a_module_published_later_does_not_take_completion_away(self):
        tutor = untrained()
        training.complete_module(tutor, module('a'))
        stamp = TeacherProfile.objects.get(pk=tutor.pk).training_completed_at
        module('late', 2)
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at == stamp

    @pytest.mark.parametrize('status', ['applied', 'submitted', 'in_review', 'changes_requested', 'rejected', 'suspended'])
    def test_only_an_approved_tutor_can_train(self, status):
        tutor = untrained(status)
        with pytest.raises(training.TrainingNotAvailable):
            training.complete_module(tutor, module('a'))
        assert not TrainingProgress.objects.exists()

    def test_progress_of_one_tutor_never_completes_another(self):
        one, two = untrained(), untrained()
        training.complete_module(one, module('a'))
        assert TeacherProfile.objects.get(pk=two.pk).training_completed_at is None

    def test_summary_counts_only_required_published_modules(self):
        tutor = untrained()
        a = module('a', 1)
        module('b', 2)
        module('opt', 3, required=False)
        module('draft', 4, published=False)
        training.complete_module(tutor, a)
        s = training.summary(tutor)
        assert (s['required_total'], s['required_completed'], s['completed_at']) == (2, 1, None)


# ------------------------------------------------------------------ the gate (T1b) with real training
def test_with_the_gate_on_the_tutor_becomes_bookable_after_finishing_the_required_modules(settings):
    settings.TUTOR_TRAINING_GATE_ENABLED = True
    tutor = untrained()
    m = module('a')
    assert not TeacherProfile.objects.bookable().filter(pk=tutor.pk).exists()
    training.complete_module(tutor, m)
    assert TeacherProfile.objects.bookable().filter(pk=tutor.pk).exists()


# ------------------------------------------------------------------ API
class TestApi:
    LIST = '/api/v1/teachers/me/training/'

    def test_the_tutor_sees_published_modules_in_order_with_their_own_progress(self):
        tutor = untrained()
        a = module('a', 1)
        module('b', 2)
        module('draft', 3, published=False)
        training.complete_module(tutor, a)
        body = api(tutor.user).get(self.LIST).json()
        assert [m['slug'] for m in body['modules']] == ['a', 'b']
        assert [m['completed'] for m in body['modules']] == [True, False]
        assert body['required_total'] == 2 and body['required_completed'] == 1 and body['completed_at'] is None
        assert 'body' not in body['modules'][0]                    # the list is light; content comes from the detail

    def test_detail_returns_the_content_but_not_for_a_draft(self):
        tutor = untrained()
        module('a')
        module('draft', 2, published=False)
        assert api(tutor.user).get(f'{self.LIST}a/').json()['body'] == '# a'
        assert api(tutor.user).get(f'{self.LIST}draft/').status_code == 404

    def test_complete_is_idempotent_and_reports_the_new_state(self):
        tutor = untrained()
        module('a')
        for _ in range(2):
            res = api(tutor.user).post(f'{self.LIST}a/complete/')
            assert res.status_code == 200
            assert res.json()['completed_at'] and res.json()['required_completed'] == 1

    def test_complete_unknown_or_draft_is_404_and_a_non_approved_tutor_409(self):
        approved = untrained()
        module('draft', published=False)
        assert api(approved.user).post(f'{self.LIST}draft/complete/').status_code == 404
        assert api(approved.user).post(f'{self.LIST}nope/complete/').status_code == 404
        module('a', 2)
        applicant = untrained('applied')
        assert api(applicant.user).post(f'{self.LIST}a/complete/').status_code == 409

    @pytest.mark.parametrize('who', ['student', 'anon'])
    def test_only_tutors(self, who):
        user = f.make_student() if who == 'student' else None
        assert api(user).get(self.LIST).status_code in (401, 403)
        assert api(user).post(f'{self.LIST}a/complete/').status_code in (401, 403)

    def test_a_tutor_cannot_complete_for_someone_else(self):
        mine, other = untrained(), untrained()
        module('a')
        api(mine.user).post(f'{self.LIST}a/complete/')
        assert not TrainingProgress.objects.filter(teacher=other).exists()


# ------------------------------------------------------------------ backfill (before the gate is switched on)
class TestBackfill:
    def run(self, *args):
        out = StringIO()
        call_command('backfill_training_completed', *args, stdout=out)
        return out.getvalue()

    def test_stamps_every_approved_untrained_tutor_once(self):
        approved = untrained()
        trained = f.make_teacher_profile(status='approved', training_completed_at=timezone.now() - timedelta(days=30))
        stamp = trained.training_completed_at
        applicant = untrained('applied')
        suspended = untrained('suspended')
        assert training.backfill_training_completed() == 1
        assert TeacherProfile.objects.get(pk=approved.pk).training_completed_at is not None
        assert TeacherProfile.objects.get(pk=trained.pk).training_completed_at == stamp
        assert TeacherProfile.objects.get(pk=applicant.pk).training_completed_at is None
        assert TeacherProfile.objects.get(pk=suspended.pk).training_completed_at is None
        assert training.backfill_training_completed() == 0                  # idempotent

    def test_the_command_reports_and_dry_run_changes_nothing(self):
        tutor = untrained()
        assert 'would stamp 1' in self.run('--dry-run')
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at is None
        assert 'stamped 1' in self.run()
        assert TeacherProfile.objects.get(pk=tutor.pk).training_completed_at is not None
        assert 'stamped 0' in self.run()

    def test_the_command_warns_when_there_is_no_published_required_module(self):
        assert 'no published required training module' in self.run('--dry-run').lower()
        module('a')
        assert 'no published required training module' not in self.run('--dry-run').lower()
