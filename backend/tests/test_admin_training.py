"""Wave 2: admins manage tutor training (/api/v1/admin/training/*, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md section 5).

Decisions under test: only platform admins write; a training video is a YouTube link reduced to its id; publishing a
required module takes the training date away from EVERY tutor who has not completed it (no grace period), after staff
confirm the number; lessons already booked are untouched because only `bookable()` reads the date."""
import pytest
from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory
from rest_framework.test import APIClient

import factories as f
from apps.notifications.models import Notification
from apps.teachers import training
from apps.teachers.models import TeacherProfile, TrainingModule, TrainingProgress

pytestmark = pytest.mark.django_db

LIST = '/api/v1/admin/training/modules/'


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def detail(module):
    return f'{LIST}{module.pk}/'


def module(slug, position=1, *, required=True, published=True):
    return TrainingModule.objects.create(slug=slug, title=slug.title(), body=f'# {slug}', position=position,
                                         is_required=required, is_published=published)


def trained_tutor(*modules):
    tutor = f.make_teacher_profile(training_completed_at=None)
    for m in modules:
        training.complete_module(tutor, m)
    tutor.refresh_from_db()
    assert tutor.training_completed_at is not None
    return tutor


def date_of(tutor):
    return TeacherProfile.objects.get(pk=tutor.pk).training_completed_at


# ------------------------------------------------------------------ YouTube links
@pytest.mark.parametrize('link', [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s',
    'https://m.youtube.com/watch?feature=share&v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ?si=abc',
    'youtu.be/dQw4w9WgXcQ',
    'https://www.youtube.com/embed/dQw4w9WgXcQ',
    'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ',
    'https://www.youtube.com/shorts/dQw4w9WgXcQ',
    'dQw4w9WgXcQ',
])
def test_youtube_links_reduce_to_the_video_id(link):
    assert training.parse_youtube_id(link) == 'dQw4w9WgXcQ'


@pytest.mark.parametrize('link', [
    'https://vimeo.com/123456',
    'https://evil.example/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ',
    'javascript:alert(1)',
    'https://www.youtube.com/watch?v=short',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ"><script>',
    '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>',
    'ftp://youtu.be/dQw4w9WgXcQ',
])
def test_anything_else_is_refused(link):
    with pytest.raises(training.InvalidVideoLink):
        training.parse_youtube_id(link)


def test_an_empty_link_clears_the_video():
    assert training.parse_youtube_id('  ') == ''


# ------------------------------------------------------------------ access
@pytest.mark.parametrize('who', ['anonymous', 'student', 'teacher'])
def test_only_platform_admins_may_use_the_api(who, student_user, teacher_user):
    user = {'anonymous': None, 'student': student_user, 'teacher': teacher_user.user}[who]
    m = module('a')
    for method, url in (('get', LIST), ('post', LIST), ('get', detail(m)), ('patch', detail(m)),
                        ('post', '/api/v1/admin/training/reorder/')):
        assert getattr(api(user), method)(url, {}, format='json').status_code in (401, 403)


# ------------------------------------------------------------------ list / create / edit
def test_list_shows_drafts_counts_and_the_gate(admin_user, settings):
    settings.TUTOR_TRAINING_GATE_ENABLED = False
    a = module('a')
    module('draft', 2, published=False)
    trained_tutor(a)
    f.make_teacher_profile(training_completed_at=None)
    body = api(admin_user).get(LIST).json()
    assert [m['slug'] for m in body['modules']] == ['a', 'draft']
    assert body['modules'][0]['completed_count'] == 1 and body['modules'][1]['completed_count'] == 0
    assert body['approved_tutors'] == 2 and body['trained_tutors'] == 1 and body['gate_enabled'] is False
    assert 'body' not in body['modules'][0]


def test_create_starts_as_a_draft_at_the_end_with_the_video_id(admin_user):
    module('a', 4)
    r = api(admin_user).post(LIST, {'slug': 'safety', 'title': ' Safety ', 'body': '# Hi',
                                    'video_url': 'https://youtu.be/dQw4w9WgXcQ'}, format='json')
    assert r.status_code == 201, r.json()
    created = TrainingModule.objects.get(slug='safety')
    assert (created.title, created.position, created.is_published, created.is_required) == ('Safety', 5, False, True)
    assert created.video_youtube_id == 'dQw4w9WgXcQ' and r.json()['body'] == '# Hi'


@pytest.mark.parametrize('payload, field', [
    ({'slug': 'a', 'title': 'Dup'}, 'slug'),
    ({'slug': 'Not A Slug', 'title': 'x'}, 'slug'),
    ({'slug': 'ok', 'title': '   '}, 'title'),
    ({'slug': 'ok', 'title': 'x', 'video_url': 'https://vimeo.com/1'}, 'video_url'),
    ({'slug': 'ok', 'title': 'x', 'estimated_minutes': 0}, 'estimated_minutes'),
])
def test_create_validates(admin_user, payload, field):
    module('a')
    r = api(admin_user).post(LIST, payload, format='json')
    assert r.status_code == 400 and field in r.json()


def test_edit_keeps_its_own_slug_and_can_clear_the_video(admin_user):
    m = module('a')
    TrainingModule.objects.filter(pk=m.pk).update(video_youtube_id='dQw4w9WgXcQ')
    r = api(admin_user).patch(detail(m), {'slug': 'a', 'summary': 'new', 'video_url': ''}, format='json')
    assert r.status_code == 200
    m.refresh_from_db()
    assert (m.summary, m.video_youtube_id, m.title) == ('new', '', 'A')


def test_the_tutor_sees_the_video_id(teacher_user):
    m = module('a')
    TrainingModule.objects.filter(pk=m.pk).update(video_youtube_id='dQw4w9WgXcQ')
    body = api(teacher_user.user).get('/api/v1/teachers/me/training/a/').json()
    assert body['video_youtube_id'] == 'dQw4w9WgXcQ'


# ------------------------------------------------------------------ re-gating (decision 4)
class TestRegate:
    def test_publishing_a_required_module_needs_confirmation_then_regates_everyone_without_it(self, admin_user, settings):
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        a = module('a')
        old_hand, also_trained = trained_tutor(a), trained_tutor(a)
        new = module('new', 2, published=False)
        already_did_it = trained_tutor(a)
        TrainingProgress.objects.create(teacher=already_did_it, module=new)    # e.g. completed before an unpublish

        r = api(admin_user).patch(detail(new), {'is_published': True}, format='json')
        assert r.status_code == 409
        assert r.json()['code'] == 'regate_confirmation_required' and r.json()['tutors_affected'] == 2
        assert TrainingModule.objects.get(pk=new.pk).is_published is False      # nothing saved
        assert date_of(old_hand) is not None

        r = api(admin_user).patch(detail(new), {'is_published': True, 'confirm_regate': True}, format='json')
        assert r.status_code == 200
        assert date_of(old_hand) is None and date_of(also_trained) is None
        assert date_of(already_did_it) is not None
        bookable = set(TeacherProfile.objects.bookable().values_list('pk', flat=True))
        assert old_hand.pk not in bookable and already_did_it.pk in bookable

        new.refresh_from_db()
        training.complete_module(old_hand, new)                                # finishing it restores the date
        assert date_of(old_hand) is not None

    def test_tutors_are_told(self, admin_user, django_capture_on_commit_callbacks):
        a = module('a')
        tutor = trained_tutor(a)
        new = module('new', 2, published=False)
        with django_capture_on_commit_callbacks(execute=True):
            api(admin_user).patch(detail(new), {'is_published': True, 'confirm_regate': True}, format='json')
        sent = Notification.objects.filter(user=tutor.user, kind='training_required')
        assert sent.count() == 1 and 'New' in sent.get().body

    def test_creating_a_published_required_module_also_regates(self, admin_user):
        tutor = trained_tutor(module('a'))
        r = api(admin_user).post(LIST, {'slug': 'b', 'title': 'B', 'is_published': True}, format='json')
        assert r.status_code == 409 and r.json()['tutors_affected'] == 1
        r = api(admin_user).post(LIST, {'slug': 'b', 'title': 'B', 'is_published': True, 'confirm_regate': True},
                                 format='json')
        assert r.status_code == 201 and date_of(tutor) is None

    def test_making_a_published_optional_module_required_regates(self, admin_user):
        tutor = trained_tutor(module('a'))
        opt = module('opt', 2, required=False)
        r = api(admin_user).patch(detail(opt), {'is_required': True, 'confirm_regate': True}, format='json')
        assert r.status_code == 200 and date_of(tutor) is None

    @pytest.mark.parametrize('change', [{'is_published': True, 'is_required': False}, {'title': 'Renamed'}])
    def test_changes_that_do_not_newly_gate_need_no_confirmation(self, admin_user, change):
        a = module('a')
        tutor = trained_tutor(a)
        target = module('x', 2, published=False) if 'is_published' in change else a
        assert api(admin_user).patch(detail(target), change, format='json').status_code == 200
        assert date_of(tutor) is not None

    @pytest.mark.parametrize('change', [{'is_published': False}, {'is_required': False}])
    def test_unpublishing_or_making_optional_never_takes_anything_away(self, admin_user, change):
        a, b = module('a'), module('b', 2)
        tutor = trained_tutor(a, b)
        assert api(admin_user).patch(detail(b), change, format='json').status_code == 200
        assert date_of(tutor) is not None

    def test_with_nobody_affected_publishing_needs_no_confirmation(self, admin_user):
        new = module('new', published=False)
        f.make_teacher_profile(training_completed_at=None)
        assert api(admin_user).patch(detail(new), {'is_published': True}, format='json').status_code == 200

    def test_django_admin_saves_regate_too(self, admin_user):
        a = module('a')
        tutor = trained_tutor(a)
        new = module('new', 2, published=False)
        model_admin = admin_site._registry[TrainingModule]
        request = RequestFactory().post('/admin/')
        request.user = admin_user
        request._messages = _Messages()
        form_class = model_admin.get_form(request, new)
        form = form_class(instance=new, data={'slug': 'new', 'title': 'New', 'summary': '', 'body': 'x',
                                              'video_youtube_id': '', 'position': 2, 'estimated_minutes': 10,
                                              'is_required': 'on', 'is_published': 'on'})
        assert form.is_valid(), form.errors
        obj = form.save(commit=False)
        model_admin.save_model(request, obj, form, change=True)
        assert TrainingModule.objects.get(pk=new.pk).is_published and date_of(tutor) is None
        assert request._messages.added


class _Messages:
    def __init__(self):
        self.added = []

    def add(self, level, message, extra_tags=''):
        self.added.append(message)


# ------------------------------------------------------------------ reorder
def test_reorder_sets_positions_and_requires_every_module_once(admin_user):
    a, b, c = module('a', 1), module('b', 2), module('c', 3)
    url = '/api/v1/admin/training/reorder/'
    assert api(admin_user).post(url, {'ids': [str(c.pk), str(a.pk)]}, format='json').status_code == 400
    assert api(admin_user).post(url, {'ids': [str(c.pk), str(a.pk), str(a.pk)]}, format='json').status_code == 400
    assert api(admin_user).post(url, {'ids': 'nope'}, format='json').status_code == 400
    r = api(admin_user).post(url, {'ids': [str(c.pk), str(a.pk), str(b.pk)]}, format='json')
    assert r.status_code == 200
    assert [m['slug'] for m in r.json()['modules']] == ['c', 'a', 'b']
