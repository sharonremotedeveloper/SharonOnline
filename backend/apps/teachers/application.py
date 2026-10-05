"""
Tutor application funnel (slice T5a, docs/TUTOR_STATUS_MACHINE.md section 14).

    overview(teacher) -> dict                          the five steps, what is missing, whether the tutor may submit
    update_application(teacher, data) -> TeacherApplication     speed test / power backup / declaration; locked once sent
    submit_application(teacher, *, actor) -> TeacherTransitionResult

Steps: profile (headline, bio, a specialty), uploads (live TeacherAsset rows for APPLICATION_REQUIRED_ASSET_KINDS), power backup
(confirmed), speed test (recent and at least the minimum), declaration (accepted). Submitting moves `applied` /
`changes_requested` -> `submitted` through teachers/vetting.py with the TUTOR as actor (so staff get the `vetting_submitted`
alert); nothing else may submit for them. The application is editable only in those two statuses.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from apps.common import clock
from apps.teachers import vetting
from apps.teachers.models import TeacherApplication, TeacherAsset, TeacherProfile

St = TeacherProfile.Status
EDITABLE = (St.APPLIED, St.CHANGES_REQUESTED)


class ApplicationError(Exception):
    http_status = 400
    code = 'invalid'


class ApplicationLocked(ApplicationError):
    http_status, code = 409, 'application_locked'


class CannotSubmit(ApplicationError):
    http_status, code = 409, 'cannot_submit'


class ApplicationIncomplete(ApplicationError):
    http_status, code = 400, 'application_incomplete'

    def __init__(self, missing):
        self.missing = missing
        super().__init__(f'The application is incomplete: {", ".join(missing)}.')


def get_application(teacher) -> TeacherApplication:
    return TeacherApplication.objects.get_or_create(teacher=teacher)[0]


def requirements() -> dict:
    return {'upload_kinds': list(settings.APPLICATION_REQUIRED_ASSET_KINDS),
            'min_download_mbps': float(settings.APPLICATION_MIN_DOWNLOAD_MBPS),
            'min_upload_mbps': float(settings.APPLICATION_MIN_UPLOAD_MBPS),
            'speed_test_max_age_hours': int(settings.APPLICATION_SPEED_TEST_MAX_AGE_HOURS)}


def _profile_step(teacher):
    checks = (('headline', bool((teacher.headline or '').strip())), ('bio', bool((teacher.bio or '').strip())),
              ('specialties', bool(teacher.specialties)))
    missing = [name for name, ok in checks if not ok]
    return {'key': 'profile', 'complete': not missing, 'missing': missing, 'detail': ''}


def _uploads_step(teacher):
    live = set(TeacherAsset.objects.filter(teacher=teacher, replaced_at__isnull=True).values_list('kind', flat=True))
    missing = [kind for kind in settings.APPLICATION_REQUIRED_ASSET_KINDS if kind not in live]
    return {'key': 'uploads', 'complete': not missing, 'missing': missing, 'detail': ''}


def _speed_step(app, now):
    down, up, at = app.speed_test_download_mbps, app.speed_test_upload_mbps, app.speed_test_at
    min_down = Decimal(str(settings.APPLICATION_MIN_DOWNLOAD_MBPS))
    min_up = Decimal(str(settings.APPLICATION_MIN_UPLOAD_MBPS))
    row = {'key': 'speed_test', 'complete': False, 'missing': ['speed_test'], 'detail': ''}
    if at is None or down is None or up is None:
        row['detail'] = 'No speed test recorded.'
    elif down < min_down or up < min_up:
        row['detail'] = f'Your connection measured {down} / {up} Mbps, below the {min_down} / {min_up} Mbps minimum.'
    elif now - at > timedelta(hours=settings.APPLICATION_SPEED_TEST_MAX_AGE_HOURS):
        row['detail'] = 'The speed test is too old: run it again.'
    else:
        row.update(complete=True, missing=[])
    return row


def _flag_step(key, stamped_at):
    return {'key': key, 'complete': stamped_at is not None, 'missing': [] if stamped_at else [key], 'detail': ''}


def steps(teacher, app, now) -> list:
    return [_profile_step(teacher), _uploads_step(teacher), _flag_step('power_backup', app.power_backup_confirmed_at),
            _speed_step(app, now), _flag_step('declaration', app.declaration_accepted_at)]


def overview(teacher) -> dict:
    app, now = get_application(teacher), clock.now()
    rows = steps(teacher, app, now)
    return {'status': teacher.status, 'editable': teacher.status in EDITABLE, 'steps': rows,
            'can_submit': teacher.status in EDITABLE and all(r['complete'] for r in rows),
            'submitted_at': app.submitted_at, 'requirements': requirements()}


def update_application(teacher, data) -> TeacherApplication:
    """`data`: optional `speed_test` {download_mbps, upload_mbps}, `confirm_power_backup` True, `accept_declaration` True."""
    now = clock.now()
    with transaction.atomic():
        locked = TeacherProfile.objects.select_for_update().only('id', 'status').get(pk=teacher.pk)
        if locked.status not in EDITABLE:
            raise ApplicationLocked('This application has been sent and can no longer be edited.')
        app = TeacherApplication.objects.select_for_update().get_or_create(teacher=teacher)[0]
        if 'speed_test' in data:
            app.speed_test_download_mbps = data['speed_test']['download_mbps']
            app.speed_test_upload_mbps = data['speed_test']['upload_mbps']
            app.speed_test_at = now
        if data.get('confirm_power_backup') and app.power_backup_confirmed_at is None:
            app.power_backup_confirmed_at = now
        if data.get('accept_declaration') and app.declaration_accepted_at is None:
            app.declaration_accepted_at = now
        app.save()
    return app


def submit_application(teacher, *, actor):
    """Idempotent: an application already `submitted` is a no-op. Anything but applied / changes_requested / submitted is 409."""
    teacher.refresh_from_db(fields=['status'])
    if teacher.status == St.SUBMITTED:
        return vetting.transition_teacher(teacher, St.SUBMITTED, actor=actor)
    if teacher.status not in EDITABLE:
        raise CannotSubmit('This application cannot be submitted in its current status.')
    app, now = get_application(teacher), clock.now()
    missing = [row['key'] for row in steps(teacher, app, now) if not row['complete']]
    if missing:
        raise ApplicationIncomplete(missing)
    with transaction.atomic():
        result = vetting.transition_teacher(teacher, St.SUBMITTED, actor=actor, reason='application submitted')
        TeacherApplication.objects.filter(pk=app.pk).update(submitted_at=now)
    return result
