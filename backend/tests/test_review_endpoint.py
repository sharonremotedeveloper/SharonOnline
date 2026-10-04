"""Task 9.10: one review endpoint - finished lessons only, one review per lesson, private text, honest aggregates."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile

S = Booking.Status
User = get_user_model()
CANONICAL = '/api/v1/student/bookings/{}/review/'
ALIAS = '/api/v1/bookings/{}/review/'      # kept so old clients keep working; same view underneath


def lesson(teacher, student, status=S.COMPLETED, hours_ago=3):
    start = timezone.now() - timedelta(hours=hours_ago)
    return Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                  end_time_utc=start + timedelta(minutes=25), status=status)


def client(user=None):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c


def review(user, booking, body=None, url=CANONICAL):
    body = {'rating': 5, 'tags': ['Clear Pronunciation'], 'private_notes': 'Loved it'} if body is None else body
    return client(user).post(url.format(booking.id), body, format='json')


def new_student(n):
    return User.objects.create_user(username=f'stu{n}', email=f'stu{n}@x.com', password='x-pass-12345', role='student')


# ------------------------------------------------------------------ one endpoint, two URLs
@pytest.mark.django_db
class TestSubmit:
    @pytest.mark.parametrize('url', [CANONICAL, ALIAS])
    def test_review_is_stored_with_rating_tags_text_and_time(self, teacher_user, student_user, url):
        b = lesson(teacher_user, student_user)
        res = review(student_user, b, url=url)
        assert res.status_code == 200 and res.json()['success'] is True
        b.refresh_from_db()
        assert (b.student_rating, b.student_review_tags, b.student_review) == (5, ['Clear Pronunciation'], 'Loved it')
        assert b.reviewed_at is not None

    def test_the_legacy_review_field_is_still_understood(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user)
        assert review(student_user, b, {'rating': 4, 'review': 'old client text'}, url=ALIAS).status_code == 200
        assert Booking.objects.get(pk=b.pk).student_review == 'old client text'

    def test_tags_and_text_are_optional(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user)
        assert review(student_user, b, {'rating': 3}).status_code == 200
        b.refresh_from_db()
        assert (b.student_review_tags, b.student_review) == ([], '')

    def test_duplicate_tags_collapse(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user)
        review(student_user, b, {'rating': 5, 'tags': ['Ideal Pacing', 'Ideal Pacing', 'Helpful Examples']})
        assert Booking.objects.get(pk=b.pk).student_review_tags == ['Ideal Pacing', 'Helpful Examples']

    @pytest.mark.parametrize('first,second', [(CANONICAL, CANONICAL), (CANONICAL, ALIAS), (ALIAS, CANONICAL)])
    def test_a_lesson_can_be_reviewed_once_whichever_url_is_used(self, teacher_user, student_user, first, second):
        b = lesson(teacher_user, student_user)
        assert review(student_user, b, {'rating': 5}, url=first).status_code == 200
        again = review(student_user, b, {'rating': 1, 'private_notes': 'changed my mind'}, url=second)
        assert again.status_code == 409
        b.refresh_from_db()
        assert (b.student_rating, b.student_review) == (5, '')            # the first review stands


# ------------------------------------------------------------------ only lessons that happened
@pytest.mark.django_db
class TestEligibility:
    @pytest.mark.parametrize('status', [S.PENDING_PAYMENT, S.CONFIRMED, S.IN_PROGRESS, S.CANCELLED, S.DISPUTED,
                                        S.INTERRUPTED_POWER, S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW])
    def test_lessons_that_did_not_happen_cannot_be_reviewed(self, teacher_user, student_user, status):
        b = lesson(teacher_user, student_user, status)
        assert review(student_user, b).status_code == 409
        b.refresh_from_db(); teacher_user.refresh_from_db()
        assert b.student_rating is None and teacher_user.rating_count == 0

    @pytest.mark.parametrize('status', [S.COMPLETED_PENDING_MEMO, S.COMPLETED, S.COMPLETED_MEMO_FORFEITED])
    def test_lessons_that_happened_can(self, teacher_user, student_user, status):
        assert review(student_user, lesson(teacher_user, student_user, status)).status_code == 200

    def test_only_the_lessons_own_student(self, teacher_user, student_user, admin_user):
        b = lesson(teacher_user, student_user)
        assert review(None, b).status_code == 401
        assert review(new_student(1), b).status_code == 404          # not their lesson: it does not exist for them
        assert review(teacher_user.user, b).status_code == 403       # tutors do not rate themselves
        assert review(admin_user, b).status_code == 403
        assert Booking.objects.get(pk=b.pk).student_rating is None

    def test_unknown_booking(self, student_user):
        import uuid
        assert client(student_user).post(CANONICAL.format(uuid.uuid4()), {'rating': 5}, format='json').status_code == 404


# ------------------------------------------------------------------ input validation
@pytest.mark.django_db
class TestValidation:
    @pytest.mark.parametrize('body,field', [
        ({}, 'rating'), ({'rating': 0}, 'rating'), ({'rating': 6}, 'rating'), ({'rating': 'five'}, 'rating'),
        ({'rating': 2.5}, 'rating'), ({'rating': None}, 'rating'), ({'rating': True}, 'rating'),
        ({'rating': 5, 'tags': 'Ideal Pacing'}, 'tags'), ({'rating': 5, 'tags': ['Made Up Tag']}, 'tags'),
        ({'rating': 5, 'tags': [5]}, 'tags'), ({'rating': 5, 'tags': ['Ideal Pacing'] * 3 + ['Helpful Examples'] * 3 + ['x'] * 5}, 'tags'),
        ({'rating': 5, 'private_notes': 'x' * 2001}, 'private_notes'), ({'rating': 5, 'private_notes': 'a\u0000b'}, 'private_notes'),
    ])
    def test_bad_input_is_a_400_and_does_not_use_up_the_review(self, teacher_user, student_user, body, field):
        b = lesson(teacher_user, student_user)
        res = review(student_user, b, body)
        assert res.status_code == 400 and field in res.json(), res.json()
        assert Booking.objects.get(pk=b.pk).student_rating is None
        assert review(student_user, b, {'rating': 4}).status_code == 200      # a corrected submission still works

    def test_non_object_body(self, teacher_user, student_user):
        assert review(student_user, lesson(teacher_user, student_user), ['x']).status_code == 400


# ------------------------------------------------------------------ the tutor's public rating
@pytest.mark.django_db
class TestAggregates:
    def test_average_and_count_come_from_the_database(self, teacher_user):
        for n, stars in enumerate([5, 4, 3], start=1):
            s = new_student(n)
            assert review(s, lesson(teacher_user, s), {'rating': stars}).status_code == 200
        teacher_user.refresh_from_db()
        assert (teacher_user.rating_avg, teacher_user.rating_count) == (Decimal('4.00'), 3)

    def test_other_tutors_are_unaffected(self, teacher_user, student_user):
        other_user = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        other = TeacherProfile.objects.create(user=other_user, headline='x', price_per_25min_usd=9, status='approved',
                                              rating_avg=Decimal('4.50'), rating_count=10)
        review(student_user, lesson(teacher_user, student_user), {'rating': 1})
        other.refresh_from_db()
        assert (other.rating_avg, other.rating_count) == (Decimal('4.50'), 10)

    def test_a_review_never_rewrites_the_rest_of_the_tutor_row(self, teacher_user, student_user):
        """A full-row save from a stale copy could undo a concurrent deactivation / strike. Only the two rating columns change."""
        b = lesson(teacher_user, student_user)
        with mock.patch.object(TeacherProfile, 'save', side_effect=AssertionError('whole-row save')):
            assert review(student_user, b).status_code == 200
        teacher_user.refresh_from_db()
        assert teacher_user.rating_count == 1


# ------------------------------------------------------------------ privacy
@pytest.mark.django_db
class TestPrivacy:
    SECRET = 'the tutor was rude about my accent'

    def posted(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user)
        assert review(student_user, b, {'rating': 2, 'tags': ['Ideal Pacing'], 'private_notes': self.SECRET}).status_code == 200
        b.refresh_from_db()
        assert b.student_review == self.SECRET      # it IS stored - the tests below prove who may read it
        return b

    def test_neither_the_tutor_nor_the_student_can_read_the_written_text(self, teacher_user, student_user):
        b = self.posted(teacher_user, student_user)
        for user in (teacher_user.user, student_user):
            res = client(user).get(f'/api/v1/bookings/{b.id}/')
            assert res.status_code == 200, user
            assert self.SECRET not in res.content.decode() and 'student_review' not in res.json()

    def test_staff_do_get_it(self, teacher_user, student_user, admin_user):
        from rest_framework.test import APIRequestFactory
        from apps.bookings.serializers import BookingDetailSerializer
        b = self.posted(teacher_user, student_user)
        from rest_framework.request import Request
        req = Request(APIRequestFactory().get('/')); req.user = admin_user
        assert BookingDetailSerializer(b, context={'request': req}).data['student_review'] == self.SECRET

    def test_the_students_lesson_archive_shows_only_rating_tags_and_time(self, teacher_user, student_user):
        b = self.posted(teacher_user, student_user)
        archive = client(student_user).get('/api/v1/student/lessons/').json()
        r = next(l for l in archive if l['id'] == str(b.id))['review']
        assert r['rating'] == 2 and r['tags'] == ['Ideal Pacing'] and r['submitted_at']
        assert self.SECRET not in str(archive) and 'private_notes' not in r

    def test_unreviewed_lessons_show_no_review_and_no_invented_tags(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user)
        archive = client(student_user).get('/api/v1/student/lessons/').json()
        assert next(l for l in archive if l['id'] == str(b.id))['review'] is None

    def test_django_admin_cannot_rewrite_a_review(self):
        from django.contrib import admin
        from apps.bookings.admin import BookingAdmin
        ro = admin.site._registry[Booking].readonly_fields
        assert {'student_rating', 'student_review', 'student_review_tags', 'reviewed_at'} <= set(ro)
