"""
Guard (i): every registered notification kind has a template, an example payload, a mandatory/optional flag (its
category) and a committed golden snapshot (plan §5; slice N1a).

Golden files live in `tests/golden/notifications/<kind>.txt`: subject, text and html rendered for a fixed tutor/student/
booking. A template change must update its snapshot in the same commit (review the diff). To create or refresh one,
render it with `golden_text(kind)` below and write the result with your editor; there is no auto-write switch.
"""
import uuid
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

import pytest

from apps.notifications import registry

GOLDEN_DIR = Path(__file__).resolve().parent.parent / 'golden' / 'notifications'
FIXED_BOOKING = uuid.UUID('00000000-0000-4000-8000-0000000000b1')
FIXED_START = datetime(2026, 3, 2, 7, 0, tzinfo=dt_timezone.utc)


def _kinds():
    return sorted(registry.all_kinds(), key=lambda k: k.name)


def golden_text(kind):
    """The snapshot for one kind (needs the database: call inside a django_db test)."""
    from apps.bookings.models import Booking
    from apps.teachers.models import TeacherProfile
    from apps.users.models import User
    student = User.objects.create_user(username='golden_student', email='golden_student@example.test', password='x',
                                       role=User.Role.STUDENT, first_name='Yuki', timezone='Asia/Tokyo')
    tutor_user = User.objects.create_user(username='golden_tutor', email='golden_tutor@example.test', password='x',
                                          role=User.Role.TEACHER, first_name='Thandi', timezone='Africa/Johannesburg')
    tutor = TeacherProfile.objects.create(user=tutor_user, status=TeacherProfile.Status.APPROVED, headline='TEFL')
    booking = Booking.objects.create(id=FIXED_BOOKING, teacher=tutor, student=student, start_time_utc=FIXED_START,
                                     end_time_utc=FIXED_START.replace(minute=25), status=Booking.Status.CONFIRMED)
    rendered = kind.render(student, kind.example(booking), booking)
    return (f'subject: {rendered.subject}\ntitle: {rendered.title}\n--- body\n{rendered.body}\n--- text\n'
            f'{rendered.text}\n--- html\n{rendered.html}\n')


@pytest.mark.parametrize('kind', _kinds(), ids=lambda k: k.name)
def test_kind_is_complete(kind):
    assert callable(kind.render), kind.name
    assert callable(kind.example), f'{kind.name}: register an example payload builder'
    assert kind.category in registry.CATEGORIES
    assert isinstance(kind.mandatory, bool)


@pytest.mark.django_db
@pytest.mark.parametrize('kind', _kinds(), ids=lambda k: k.name)
def test_golden_snapshot_matches(kind):
    path = GOLDEN_DIR / f'{kind.name}.txt'
    assert path.exists(), f'missing golden snapshot {path.name}: render golden_text(kind) and commit it'
    assert golden_text(kind) == path.read_text(encoding='utf-8'), f'{kind.name}: template changed, review + update'


def test_no_orphan_golden_files():
    names = {k.name for k in _kinds()}
    orphans = sorted(p.stem for p in GOLDEN_DIR.glob('*.txt') if p.stem not in names) if GOLDEN_DIR.exists() else []
    assert orphans == []
