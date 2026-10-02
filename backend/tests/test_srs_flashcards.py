import pytest
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta

from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.bookings.models import Booking
from apps.srs.models import StudentFlashcard

@pytest.mark.django_db
def test_student_lessons_and_flashcards_endpoints(student_user, teacher_user):
    now = timezone.now()
    Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(days=1),
        end_time_utc=now - timedelta(days=1, minutes=-25),
        status=Booking.Status.COMPLETED
    )
    StudentFlashcard.objects.create(
        student=student_user,
        word="equilibrium",
        phonetic="/ˌiː.kwɪˈlɪb.ri.əm/",
        definition="A state in which opposing forces are balanced",
        mastery=StudentFlashcard.Mastery.NEW
    )

    client = APIClient()
    client.force_authenticate(user=student_user)

    # 1. Lessons list
    lessons_res = client.get('/api/v1/student/lessons/')
    assert lessons_res.status_code == 200
    assert len(lessons_res.json()) >= 1
    assert lessons_res.json()[0]['status'] == 'completed'

    # 2. Flashcards list
    cards_res = client.get('/api/v1/student/flashcards/')
    assert cards_res.status_code == 200
    assert len(cards_res.json()) >= 1
    assert cards_res.json()[0]['word'] == 'equilibrium'


@pytest.mark.django_db
def test_spaced_repetition_mastery_intervals(student_user):
    card = StudentFlashcard.objects.create(
        student=student_user,
        word="serendipitous",
        definition="Occurring by chance in a happy way",
        mastery=StudentFlashcard.Mastery.NEW
    )

    client = APIClient()
    client.force_authenticate(user=student_user)
    today = timezone.now().date()

    # 1. Test 'again' (+1 day, status new)
    res_again = client.post(f'/api/v1/student/flashcards/{card.id}/mastery/', {'grade': 'again'}, format='json')
    assert res_again.status_code == 200
    assert res_again.json()['mastery'] == 'new'
    assert res_again.json()['nextReview'] == (today + timedelta(days=1)).strftime('%Y-%m-%d')

    # 2. Test 'good' (+3 days, status learning)
    res_good = client.post(f'/api/v1/student/flashcards/{card.id}/mastery/', {'grade': 'good'}, format='json')
    assert res_good.status_code == 200
    assert res_good.json()['mastery'] == 'learning'
    assert res_good.json()['nextReview'] == (today + timedelta(days=3)).strftime('%Y-%m-%d')

    # 3. Test 'easy' (+7 days, status mastered)
    res_easy = client.post(f'/api/v1/student/flashcards/{card.id}/mastery/', {'grade': 'easy'}, format='json')
    assert res_easy.status_code == 200
    assert res_easy.json()['mastery'] == 'mastered'
    assert res_easy.json()['nextReview'] == (today + timedelta(days=7)).strftime('%Y-%m-%d')


@pytest.mark.django_db
def test_submit_memo_auto_populates_flashcards(teacher_user, student_user):
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now,
        end_time_utc=now + timedelta(minutes=25),
        status=Booking.Status.COMPLETED_PENDING_MEMO  # memos are for lessons that have ended (Task 9.9)
    )

    client = APIClient()
    client.force_authenticate(user=teacher_user.user)

    # Submit memo containing vocabulary words
    memo_payload = {
        "feedback_text": "Excellent vocabulary retention!",
        "vocabulary_words": [
            {
                "word": "deadlock",
                "definition": "A standstill resulting from opposing forces",
                "phonetic": "/ˈded.lɒk/",
                "part_of_speech": "noun"
            },
            {
                "word": "concession",
                "definition": "A thing yielded during negotiations",
                "phonetic": "/kənˈseʃ.ən/",
                "part_of_speech": "noun"
            }
        ],
        "pronunciation_notes": "Pay attention to vowel length",
        "homework": "Practice dialogue 3"
    }

    res = client.post(f'/api/v1/bookings/{booking.id}/memo/', memo_payload, format='json')
    assert res.status_code == 200

    # Verify student flashcards were automatically generated
    cards = StudentFlashcard.objects.filter(student=student_user)
    words = [c.word for c in cards]
    assert "deadlock" in words
    assert "concession" in words


@pytest.mark.django_db
def test_submit_lesson_review_updates_teacher_rating(teacher_user, student_user):
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(days=1),
        end_time_utc=now - timedelta(days=1, minutes=-25),
        status=Booking.Status.COMPLETED
    )

    client = APIClient()
    client.force_authenticate(user=student_user)

    review_res = client.post(
        f'/api/v1/student/bookings/{booking.id}/review/',
        {
            "rating": 5,
            "tags": ["Clear Pronunciation", "Patient"],
            "private_notes": "Loved the conversational examples!"
        },
        format='json'
    )
    assert review_res.status_code == 200

    booking.refresh_from_db()
    teacher_user.refresh_from_db()

    assert booking.student_rating == 5
    assert teacher_user.rating_count >= 1


@pytest.mark.django_db
def test_srs_authorization_and_edge_cases(teacher_user, student_user):
    import uuid
    client = APIClient()

    # 1. Unauthenticated request to flashcards -> 401 or 403
    res_unauth = client.get('/api/v1/student/flashcards/')
    assert res_unauth.status_code in [401, 403]

    # 2. Teacher forbidden on student flashcards
    client.force_authenticate(user=teacher_user.user)
    res_teacher_forbidden = client.get('/api/v1/student/flashcards/')
    assert res_teacher_forbidden.status_code == 403

    # 3. Non-existent flashcard update -> 404
    client.force_authenticate(user=student_user)
    fake_card_id = uuid.uuid4()
    res_card_404 = client.post(
        f'/api/v1/student/flashcards/{fake_card_id}/mastery/',
        {'grade': 'good'},
        format='json'
    )
    assert res_card_404.status_code == 404

    # 4. Invalid grade choice -> 400
    card = StudentFlashcard.objects.create(
        student=student_user,
        word="ubiquitous",
        definition="Present everywhere",
        mastery=StudentFlashcard.Mastery.NEW
    )
    res_invalid_grade = client.post(
        f'/api/v1/student/flashcards/{card.id}/mastery/',
        {'grade': 'super_easy'},
        format='json'
    )
    assert res_invalid_grade.status_code == 400

    # 5. Cross-student flashcard isolation (student 2 cannot modify student 1's card)
    other_student = User.objects.create_user(
        username="other_student",
        email="other@test.com",
        password="password123",
        role=User.Role.STUDENT
    )
    client.force_authenticate(user=other_student)
    res_cross_student = client.post(
        f'/api/v1/student/flashcards/{card.id}/mastery/',
        {'grade': 'easy'},
        format='json'
    )
    assert res_cross_student.status_code == 404

    # 6. Non-existent booking review -> 404
    client.force_authenticate(user=student_user)
    res_nonexistent_booking = client.post(
        f'/api/v1/student/bookings/{uuid.uuid4()}/review/',
        {"rating": 5},
        format='json'
    )
    assert res_nonexistent_booking.status_code == 404

    # 7. Invalid review rating out of bounds (e.g. 10 or 0) on existing booking -> 400
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=timezone.now() - timedelta(days=1),
        end_time_utc=timezone.now() - timedelta(days=1, minutes=-25),
        status=Booking.Status.COMPLETED
    )
    res_invalid_rating = client.post(
        f'/api/v1/student/bookings/{booking.id}/review/',
        {"rating": 10},
        format='json'
    )
    assert res_invalid_rating.status_code == 400


