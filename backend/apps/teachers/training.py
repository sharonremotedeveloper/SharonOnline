"""
Tutor onboarding training (slice T6, docs/TUTOR_STATUS_MACHINE.md §13). Infrastructure only: Sharon writes the modules.

    complete_module(teacher, module) -> TeacherProfile     idempotent; sets training_completed_at when the last required one is done
    summary(teacher) -> dict                               counts over published + required modules
    backfill_training_completed() -> int                   stamps approved tutors that have no date (run BEFORE the gate is enabled)
    save_module(module, fields, confirm_regate=...)        staff create/edit (Wave 2, /admin/training); re-gates tutors, see below
    tutors_to_regate(module) -> queryset                   who would lose their date if `module` became published + required
    parse_youtube_id(url) -> str                           the only way a video gets onto a module

Only an `approved` tutor trains (the gate hides approved-but-untrained tutors; everyone else has not been vetted yet). With
no published required module nobody can complete training, so enabling TUTOR_TRAINING_GATE_ENABLED before the content exists
would hide every tutor (the `backfill_training_completed` command warns about it). `training_completed_at` is written only here,
with conditional UPDATEs (a concurrent completion cannot overwrite it).

Re-gating (Anesu, 2026-10-18: a new required module must be completed by ALL tutors, no grace period): when a module becomes
published + required, every tutor with a date who has not completed that module loses the date, so while the gate is on they
drop out of `bookable()` (new bookings only; lessons already booked never consult it) until they finish every required module
again. Staff must confirm the number first. Unpublishing a module or making it optional never takes anything away.
"""
import re
from urllib.parse import parse_qs, urlsplit

from django.db import IntegrityError, transaction

from apps.common import clock
from apps.teachers.models import TeacherProfile, TrainingModule, TrainingProgress


class TrainingNotAvailable(Exception):
    """The tutor may not train now (not approved) or the module is not published."""


class InvalidVideoLink(ValueError):
    """Not a YouTube link we accept."""


class RegateConfirmationRequired(Exception):
    """Saving would take the training date away from `count` tutors; staff must confirm first (HTTP 409)."""

    def __init__(self, count: int):
        super().__init__(f'{count} tutor(s) would need to complete this module before they can be booked again.')
        self.count = count


_YOUTUBE_ID = re.compile(r'[A-Za-z0-9_-]{11}')
_YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'}


def parse_youtube_id(url: str) -> str:
    """'' for an empty value; the 11-character video id for youtube.com/watch?v=, youtu.be/<id>, /embed/<id> or /shorts/<id>
    links; InvalidVideoLink for anything else. Only the id is stored, so the page can only ever embed a YouTube video."""
    url = (url or '').strip()
    if not url:
        return ''
    if _YOUTUBE_ID.fullmatch(url):
        return url
    parts = urlsplit(url if '://' in url else f'https://{url}')
    host = (parts.hostname or '').lower()
    candidate = ''
    if parts.scheme in ('http', 'https'):
        if host in ('youtu.be', 'www.youtu.be'):
            candidate = parts.path.strip('/').split('/')[0]
        elif host in _YOUTUBE_HOSTS:
            segments = [p for p in parts.path.split('/') if p]
            if segments[:1] == ['watch']:
                candidate = (parse_qs(parts.query).get('v') or [''])[0]
            elif len(segments) >= 2 and segments[0] in ('embed', 'shorts', 'live'):
                candidate = segments[1]
    if not _YOUTUBE_ID.fullmatch(candidate):
        raise InvalidVideoLink('Paste a YouTube link, for example https://www.youtube.com/watch?v=dQw4w9WgXcQ.')
    return candidate


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


def _gates(module) -> bool:
    return bool(module.is_published and module.is_required)


def tutors_to_regate(module):
    """Tutors holding a training date who have not completed `module` (all of them for a module not saved yet)."""
    qs = TeacherProfile.objects.filter(training_completed_at__isnull=False)
    if module.pk and TrainingModule.objects.filter(pk=module.pk).exists():
        qs = qs.exclude(training_progress__module_id=module.pk)
    return qs


EDITABLE_FIELDS = ('slug', 'title', 'summary', 'body', 'video_youtube_id', 'position', 'estimated_minutes', 'is_required',
                   'is_published')


def save_module(module, fields: dict, *, confirm_regate: bool = False):
    """Create (`module` None) or update a module from already-validated `fields`. Returns (module, tutors re-gated).
    Raises RegateConfirmationRequired when the change would take a date away and `confirm_regate` is not set."""
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f'not editable: {sorted(unknown)}')
    with transaction.atomic():
        if module is None:
            module, was_gating = TrainingModule(), False
        else:
            module = TrainingModule.objects.select_for_update().get(pk=module.pk)
            was_gating = _gates(module)
        for name, value in fields.items():
            setattr(module, name, value)
        regate = _gates(module) and not was_gating
        affected = []
        if regate:
            affected = list(tutors_to_regate(module).values_list('pk', 'user_id'))
            if affected and not confirm_regate:
                raise RegateConfirmationRequired(len(affected))
        module.save()
        if affected:
            TeacherProfile.objects.filter(pk__in=[pk for pk, _ in affected]).exclude(
                training_progress__module_id=module.pk).update(training_completed_at=None)
            module_id, user_ids = module.pk, [user_id for _, user_id in affected]
            transaction.on_commit(lambda: _tell_tutors(module_id, user_ids))
    return module, len(affected)


def _tell_tutors(module_id, user_ids):
    from apps.notifications.service import notify
    from apps.users.models import User
    for user in User.objects.filter(pk__in=user_ids):
        notify(user, 'training_required', key=f'training-required:{module_id}:{user.pk}', payload={'module_id': str(module_id)})


def backfill_training_completed(*, dry_run=False) -> int:
    """Stamp every approved tutor without a training date (they were live before the gate). Idempotent."""
    pending = TeacherProfile.objects.filter(status=TeacherProfile.Status.APPROVED, training_completed_at__isnull=True)
    if dry_run:
        return pending.count()
    return pending.update(training_completed_at=clock.now())
