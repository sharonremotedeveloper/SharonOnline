"""
Tutor onboarding training (slice T6, docs/TUTOR_STATUS_MACHINE.md §13). Infrastructure only: Sharon writes the modules.

    complete_module(teacher, module) -> TeacherProfile     idempotent; sets training_completed_at when the last required one is done
    summary(teacher) -> dict                               counts over published + required modules
    backfill_training_completed() -> int                   stamps approved tutors that have no date (run BEFORE the gate is enabled)

Only an `approved` tutor trains (the gate hides approved-but-untrained tutors; everyone else has not been vetted yet). With
no published required module nobody can complete training, so enabling TUTOR_TRAINING_GATE_ENABLED before the content exists
would hide every tutor (the `backfill_training_completed` command warns about it). A module published later never takes a date
away. `training_completed_at` is written only here, with a conditional UPDATE (a concurrent completion cannot overwrite it).
"""
from django.db import IntegrityError, transaction

from apps.common import clock
from apps.teachers.models import TeacherProfile, TrainingModule, TrainingProgress


class TrainingNotAvailable(Exception):
    """The tutor may not train now (not approved) or the module is not published."""


def required_modules():
    return TrainingModule.objects.filter(is_published=True, is_required=True)


def summary(teacher) -> dict:
    required = set(required_modules().values_list('id', flat=True))
    done = set(TrainingProgress.objects.filter(teacher=teacher, module_id__in=required).values_list('module_id', flat=True))
    completed_at = TeacherProfile.objects.filter(pk=teacher.pk).values_list('training_completed_at', flat=True).first()
    return {'required_total': len(required), 'required_completed': len(done), 'completed_at': completed_at}


def complete_module(teacher, module) -> TeacherProfile:
    if teacher.status != TeacherProfile.Status.APPROVED:
        raise TrainingNotAvailable('Training opens once your application is approved.')
    if not module.is_published:
        raise TrainingNotAvailable('This module is not available.')
    with transaction.atomic():
        try:
            with transaction.atomic():
                TrainingProgress.objects.create(teacher=teacher, module=module)
        except IntegrityError:
            pass                                                   # already completed: idempotent
        s = summary(teacher)
        if s['required_total'] and s['required_completed'] == s['required_total']:
            TeacherProfile.objects.filter(pk=teacher.pk, training_completed_at__isnull=True).update(
                training_completed_at=clock.now())
    teacher.refresh_from_db(fields=['training_completed_at'])
    return teacher


def backfill_training_completed(*, dry_run=False) -> int:
    """Stamp every approved tutor without a training date (they were live before the gate). Idempotent."""
    pending = TeacherProfile.objects.filter(status=TeacherProfile.Status.APPROVED, training_completed_at__isnull=True)
    if dry_run:
        return pending.count()
    return pending.update(training_completed_at=clock.now())
