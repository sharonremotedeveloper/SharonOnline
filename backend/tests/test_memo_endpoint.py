"""Task 9.9: the post-lesson memo endpoint - validated input, only the lesson's tutor, only finished lessons, honest flashcards."""
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatusChange, LessonMemo
from apps.srs.models import StudentFlashcard

S = Booking.Status
User = get_user_model()


def finished_lesson(teacher, student, status=S.COMPLETED_PENDING_MEMO):
    start = timezone.now() - timedelta(hours=2)
    return Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                  end_time_utc=start + timedelta(minutes=25), status=status)


def post(user, booking, body=None):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c.post(f'/api/v1/bookings/{booking.id}/memo/', body if body is not None else VALID, format='json')


VALID = {
    'feedback_text': 'Good lesson. Work on past tense.',
    'vocabulary_words': [{'word': 'resilience', 'definition': 'ability to recover'}, 'deadlock'],
    'pronunciation_notes': 'Vowel length',
    'grammar_notes': 'Third conditional: If I had known, I would have called.',
    'homework': 'Write 5 sentences',
}


# ------------------------------------------------------------------ happy path + persistence
@pytest.mark.django_db
class TestSubmit:
    def test_valid_memo_is_saved_in_full_and_completes_the_lesson(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        res = post(teacher_user.user, b)
        assert res.status_code == 200
        memo = LessonMemo.objects.get(booking=b)
        assert memo.grammar_notes == VALID['grammar_notes']            # was silently dropped before
        assert memo.homework == 'Write 5 sentences'
        assert Booking.objects.get(pk=b.pk).status == S.COMPLETED
        assert res.json()['grammar_notes'] == VALID['grammar_notes']

    def test_vocabulary_is_normalised_and_unknown_keys_are_dropped(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        body = {**VALID, 'vocabulary_words': [{'id': 'client-1', 'word': '  Resilience ', 'definition': 'x', 'evil': '<b>', 'phonetic': '/r/'},
                                              'deadlock']}
        assert post(teacher_user.user, b, body).status_code == 200
        assert LessonMemo.objects.get(booking=b).vocabulary_words == [
            {'word': 'Resilience', 'definition': 'x', 'phonetic': '/r/', 'part_of_speech': ''},
            {'word': 'deadlock', 'definition': '', 'phonetic': '', 'part_of_speech': ''},
        ]

    def test_repeated_words_make_one_entry_ignoring_case(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        body = {**VALID, 'vocabulary_words': ['Deadlock', 'deadlock ', {'word': 'DEADLOCK'}, 'concession']}
        assert post(teacher_user.user, b, body).status_code == 200
        assert [v['word'] for v in LessonMemo.objects.get(booking=b).vocabulary_words] == ['Deadlock', 'concession']

    def test_optional_fields_may_be_omitted(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        assert post(teacher_user.user, b, {'feedback_text': 'Short but fine.'}).status_code == 200
        memo = LessonMemo.objects.get(booking=b)
        assert (memo.vocabulary_words, memo.homework, memo.grammar_notes) == ([], '', '')

    def test_the_status_change_is_audited_against_the_tutor(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        post(teacher_user.user, b)
        c = BookingStatusChange.objects.get(booking=b)
        assert (c.from_status, c.to_status, c.actor) == (S.COMPLETED_PENDING_MEMO, S.COMPLETED, 'user:test_tutor')


# ------------------------------------------------------------------ input validation
@pytest.mark.django_db
class TestValidation:
    def bad(self, teacher_user, student_user, body, field):
        b = finished_lesson(teacher_user, student_user)
        res = post(teacher_user.user, b, body)
        assert res.status_code == 400, res.json()
        assert field in res.json(), res.json()
        assert not LessonMemo.objects.exists() and not StudentFlashcard.objects.exists()
        assert Booking.objects.get(pk=b.pk).status == S.COMPLETED_PENDING_MEMO   # nothing half-applied

    @pytest.mark.parametrize('feedback', [None, '', '   ', 'x' * 5001, 'a\u0000b'])
    def test_feedback_text(self, teacher_user, student_user, feedback):
        body = {**VALID}
        if feedback is None:
            body.pop('feedback_text')
        else:
            body['feedback_text'] = feedback
        self.bad(teacher_user, student_user, body, 'feedback_text')

    @pytest.mark.parametrize('field,value', [('homework', 'x' * 5001), ('grammar_notes', 'x' * 5001), ('pronunciation_notes', 'x' * 5001),
                                             ('homework', 'a\u0000'), ('grammar_notes', 'a\u0000')])
    def test_other_text_fields(self, teacher_user, student_user, field, value):
        self.bad(teacher_user, student_user, {**VALID, field: value}, field)

    @pytest.mark.parametrize('vocab', ['resilience', {'word': 'x'}, 5, [None], [5], [['a']], [{'definition': 'no word'}],
                                       [{'word': ''}], [{'word': '   '}], [{'word': 'x' * 129}], [{'word': 'ok', 'definition': 'd' * 1001}],
                                       [{'word': 'ok', 'phonetic': 'p' * 129}], [{'word': 'ok', 'part_of_speech': 'p' * 65}],
                                       [{'word': 'nul\u0000'}], ['w%d' % i for i in range(31)], [{'word': {'nested': 1}}]])
    def test_vocabulary_words(self, teacher_user, student_user, vocab):
        self.bad(teacher_user, student_user, {**VALID, 'vocabulary_words': vocab}, 'vocabulary_words')

    def test_non_object_body(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        assert post(teacher_user.user, b, ['not', 'an', 'object']).status_code == 400


# ------------------------------------------------------------------ who may write it, and when
@pytest.mark.django_db
class TestAccess:
    def test_only_the_lessons_own_tutor(self, teacher_user, student_user, admin_user):
        from apps.teachers.models import TeacherProfile
        other_user = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        TeacherProfile.objects.create(user=other_user, headline='x', price_per_25min_usd=9, status='approved')
        b = finished_lesson(teacher_user, student_user)
        assert post(None, b).status_code == 401
        assert post(student_user, b).status_code == 403
        assert post(other_user, b).status_code == 403
        assert post(admin_user, b).status_code == 403          # staff cannot impersonate the tutor
        assert not LessonMemo.objects.exists()
        assert post(teacher_user.user, b).status_code == 200

    def test_unknown_booking(self, teacher_user):
        import uuid
        c = APIClient(); c.force_authenticate(user=teacher_user.user)
        assert c.post(f'/api/v1/bookings/{uuid.uuid4()}/memo/', VALID, format='json').status_code == 404

    @pytest.mark.parametrize('status', [S.PENDING_PAYMENT, S.CANCELLED, S.CONFIRMED, S.IN_PROGRESS, S.DISPUTED,
                                        S.INTERRUPTED_POWER, S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW])
    def test_only_finished_lessons_can_have_a_memo(self, teacher_user, student_user, status):
        b = finished_lesson(teacher_user, student_user, status)
        res = post(teacher_user.user, b)
        assert res.status_code == 409
        assert not LessonMemo.objects.exists() and Booking.objects.get(pk=b.pk).status == status

    @pytest.mark.parametrize('status', [S.COMPLETED_PENDING_MEMO, S.COMPLETED_MEMO_FORFEITED, S.COMPLETED])
    def test_finished_lessons_accept_one(self, teacher_user, student_user, status):
        b = finished_lesson(teacher_user, student_user, status)
        assert post(teacher_user.user, b).status_code == 200
        assert Booking.objects.get(pk=b.pk).status == S.COMPLETED

    def test_a_memo_can_be_corrected_later(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        post(teacher_user.user, b)
        assert post(teacher_user.user, b, {**VALID, 'feedback_text': 'Corrected.'}).status_code == 200
        assert LessonMemo.objects.get(booking=b).feedback_text == 'Corrected.' and LessonMemo.objects.count() == 1


# ------------------------------------------------------------------ flashcards
@pytest.mark.django_db
class TestFlashcards:
    def test_each_distinct_word_becomes_one_card_for_the_student(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        post(teacher_user.user, b)
        cards = StudentFlashcard.objects.filter(student=student_user)
        assert sorted(cards.values_list('word', flat=True)) == ['deadlock', 'resilience']
        assert cards.get(word='resilience').definition == 'ability to recover'
        assert cards.get(word='deadlock').definition == 'Practiced during lesson'

    def test_correcting_a_memo_does_not_wipe_the_students_progress(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        post(teacher_user.user, b)
        card = StudentFlashcard.objects.get(student=student_user, word='resilience')
        later = timezone.now().date() + timedelta(days=9)
        StudentFlashcard.objects.filter(pk=card.pk).update(mastery='mastered', review_count=7, next_review_due=later)
        post(teacher_user.user, b, {**VALID, 'feedback_text': 'Edited'})
        card.refresh_from_db()
        assert (card.mastery, card.review_count, card.next_review_due) == ('mastered', 7, later)
        assert StudentFlashcard.objects.filter(student=student_user).count() == 2

    def test_a_flashcard_failure_is_not_swallowed_and_rolls_the_memo_back(self, teacher_user, student_user):
        b = finished_lesson(teacher_user, student_user)
        with mock.patch('apps.srs.models.StudentFlashcard.objects.get_or_create', side_effect=RuntimeError('db down')):
            with pytest.raises(RuntimeError):
                post(teacher_user.user, b)
        assert not LessonMemo.objects.exists()
        assert Booking.objects.get(pk=b.pk).status == S.COMPLETED_PENDING_MEMO   # tutor can simply retry


# ------------------------------------------------------------------ what the student sees
@pytest.mark.django_db
def test_student_sees_the_tutors_real_grammar_notes_not_a_placeholder(teacher_user, student_user):
    b = finished_lesson(teacher_user, student_user)
    post(teacher_user.user, b, {**VALID, 'homework': 'HW only'})
    c = APIClient(); c.force_authenticate(user=student_user)
    memo = c.get('/api/v1/student/lessons/').json()[0]['memo']
    assert memo['grammar_notes'] == VALID['grammar_notes'] and memo['homework'] == 'HW only'

    b2 = finished_lesson(teacher_user, student_user)
    Booking.objects.filter(pk=b2.pk).update(start_time_utc=timezone.now() - timedelta(hours=5), end_time_utc=timezone.now() - timedelta(hours=4))
    post(teacher_user.user, b2, {'feedback_text': 'No grammar notes this time', 'homework': 'only homework'})
    memos = [l['memo'] for l in c.get('/api/v1/student/lessons/').json() if l['memo']['feedback_text'].startswith('No grammar')]
    assert memos[0]['grammar_notes'] == ''          # empty stays empty; never a made-up sentence
