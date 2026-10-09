"""Slice N1a: every registered notification template, rendered with hostile data (plan §3.2, §7).

Hostile names are escaped in HTML, cannot inject a header through the subject, and no private text (the student's written
review, the tutor's CRM dossier, OAuth tokens) can reach any rendered field: payloads are ids only and renderers fetch what
they need.
"""
from datetime import datetime, timezone as dt_timezone

import pytest

import factories as f
from apps.bookings.models import Booking
from apps.crm.models import StudentTutorDossier
from apps.notifications import registry

HOSTILE_FIRST = '<script>alert(1)</script>\r\nBcc: evil@example.test'
HOSTILE_LAST = '"&\'<b>'
TUTOR_FIRST = '<img src=x onerror=alert(2)>'
SECRETS = ('SECRET-REVIEW-TEXT', 'SECRET-DOSSIER-TEXT', 'SECRET-GRAMMAR', 'SECRET-OAUTH-TOKEN')
START = datetime(2026, 3, 2, 7, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def hostile_lesson(db):
    student = f.make_student(first_name=HOSTILE_FIRST, last_name=HOSTILE_LAST,
                             google_calendar_token={'access_token': 'SECRET-OAUTH-TOKEN'})
    tutor = f.make_teacher_profile(availability=False)
    tutor.user.first_name = TUTOR_FIRST
    tutor.user.google_calendar_token = {'access_token': 'SECRET-OAUTH-TOKEN'}
    tutor.user.save(update_fields=['first_name', 'google_calendar_token'])
    booking = f.make_booking(tutor, student, status='completed')
    Booking.objects.filter(pk=booking.pk).update(student_review='SECRET-REVIEW-TEXT', start_time_utc=START)
    booking.refresh_from_db()
    StudentTutorDossier.objects.create(teacher=tutor, student=student, private_pedagogical_notes='SECRET-DOSSIER-TEXT',
                                       common_grammar_mistakes=['SECRET-GRAMMAR'])
    return student, tutor.user, booking


def _all_kinds():
    return sorted(registry.all_kinds(), key=lambda k: k.name)


def test_at_least_the_machinery_kinds_exist():
    assert {k.name for k in _all_kinds()} >= {'admin_alert', 'sample_lesson_notice'}


@pytest.mark.django_db
@pytest.mark.parametrize('kind', _all_kinds(), ids=lambda k: k.name)
@pytest.mark.parametrize('who', ['student', 'tutor'])
def test_every_template_escapes_and_leaks_nothing(kind, who, hostile_lesson):
    student, tutor, booking = hostile_lesson
    user = student if who == 'student' else tutor
    rendered = kind.render(user, kind.example(booking), booking)
    for field in (rendered.subject, rendered.title):
        assert '\r' not in field and '\n' not in field, kind.name
        assert len(field) <= 200
    assert '<script' not in rendered.html and '<img' not in rendered.html and '<b>' not in rendered.html
    for value in (rendered.subject, rendered.html, rendered.text, rendered.title, rendered.body):
        for secret in SECRETS:
            assert secret not in value, (kind.name, secret)
    assert rendered.text and rendered.html and rendered.subject


@pytest.mark.django_db
def test_sample_kind_names_the_other_party_escaped_in_the_recipients_zone(hostile_lesson):
    student, tutor, booking = hostile_lesson
    kind = registry.get('sample_lesson_notice')
    for_student = kind.render(student, kind.example(booking), booking)
    assert '&lt;img src=x onerror=alert(2)&gt;' in for_student.html
    assert '16:00' in for_student.text and 'Asia/Tokyo' in for_student.text        # 07:00 UTC in Tokyo
    for_tutor = kind.render(tutor, kind.example(booking), booking)
    assert '&lt;script&gt;' in for_tutor.html
    assert '09:00' in for_tutor.text and 'Africa/Johannesburg' in for_tutor.text


@pytest.mark.django_db
def test_admin_alert_lists_ids_escaped(hostile_lesson):
    _, _, booking = hostile_lesson
    admin = f.make_admin()
    kind = registry.get('admin_alert')
    rendered = kind.render(admin, {'alert': 'fulfilment_failed', 'booking_id': str(booking.pk),
                                   'step': '<i>room</i>'}, None)
    assert str(booking.pk) in rendered.text and str(booking.pk) in rendered.html
    assert '<i>' not in rendered.html and '&lt;i&gt;' in rendered.html
    assert rendered.subject.startswith('[Sharon admin]')


def test_admin_alert_codes_have_titles():
    from apps.notifications.builtin_kinds import ALERT_TITLES
    assert {'fulfilment_failed', 'fulfilment_needs_attention', 'orphaned_calendar_event',
            'lesson_disputed_without_verdict', 'notification_failed'} <= set(ALERT_TITLES)
