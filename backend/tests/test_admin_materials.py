"""Wave 2: admins manage lesson materials (/api/v1/admin/materials/*, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md section 5).

Decisions under test: only platform admins write; Draft -> Published, new materials start as drafts and only published
ones are public; lesson HTML is cleaned on every save and again when it is served."""
import pytest
from rest_framework.test import APIClient

from apps.materials.models import Material
from apps.materials.sanitize import clean_lesson_html

pytestmark = pytest.mark.django_db

LIST = '/api/v1/admin/materials/'


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def material(slug='cafe-talk', *, published=True, **fields):
    fields.setdefault('title', slug.replace('-', ' ').title())
    return Material.objects.create(slug=slug, category='freetalk', cefr_level='A2', is_published=published, **fields)


def detail(m):
    return f'{LIST}{m.pk}/'


VALID = {'title': 'Ordering coffee', 'slug': 'ordering-coffee', 'category': 'freetalk', 'cefr_level': 'A2',
         'description': 'Cafe phrases', 'content_html': '<h3>Phrases</h3><ul><li>A flat white, please.</li></ul>'}


# ------------------------------------------------------------------ sanitizing (risk 1)
@pytest.mark.parametrize('dirty, clean', [
    ('<p>Hi<script>alert(1)</script></p>', '<p>Hi</p>'),
    ('<p onclick="steal()">Hi</p>', '<p>Hi</p>'),
    ('<a href="javascript:alert(1)">x</a>', '<a rel="noopener noreferrer nofollow">x</a>'),
    ('<img src="https://tracker.example/p.gif" onerror="x()">', ''),
    ('<iframe src="https://evil.example"></iframe><p>ok</p>', '<p>ok</p>'),
    ('<style>body{display:none}</style><p style="color:red">ok</p>', '<p>ok</p>'),
    ('<form action="https://evil.example"><input name="pw"></form>', ''),
    ('<!-- note --><p>ok</p>', '<p>ok</p>'),
    ('<svg><script>alert(1)</script></svg>', ''),
])
def test_dangerous_html_is_removed(dirty, clean):
    assert clean_lesson_html(dirty) == clean


def test_lesson_formatting_survives():
    html = ('<h2>Title</h2><h3>Vocabulary</h3><p><strong>Asynchronous:</strong> <em>not</em> live.</p>'
            '<ol start="2"><li>One</li></ol><blockquote>Quote</blockquote>'
            '<table><thead><tr><th scope="col">Word</th></tr></thead><tbody><tr><td>Hello</td></tr></tbody></table>')
    assert clean_lesson_html(html) == html
    assert clean_lesson_html('<a href="https://bbc.co.uk/news">BBC</a>') == (
        '<a href="https://bbc.co.uk/news" rel="noopener noreferrer nofollow">BBC</a>')


def test_empty_paragraphs_left_by_browser_editors_are_dropped():
    assert clean_lesson_html('<h3>A</h3><p><ul><li>x</li></ul></p><p> <br></p><p>ok</p>') == '<h3>A</h3><ul><li>x</li></ul><p>ok</p>'


def test_every_save_path_stores_clean_html():
    m = material(content_html='<p>ok</p><script>x()</script>')
    assert Material.objects.get(pk=m.pk).content_html == '<p>ok</p>'


def test_rows_written_before_cleaning_are_cleaned_when_served():
    m = material()
    Material.objects.filter(pk=m.pk).update(content_html='<p>old</p><script>x()</script>')   # bypasses save()
    assert APIClient().get(f'/api/v1/materials/{m.slug}/').json()['content_html'] == '<p>old</p>'


# ------------------------------------------------------------------ Draft -> Published (decision 3)
def test_a_new_row_is_a_draft_by_default():
    m = Material.objects.create(title='T', slug='t', category='freetalk', cefr_level='A2')
    assert m.is_published is False


def test_drafts_are_not_public():
    material('live')
    material('secret', published=False)
    public = APIClient()
    body = public.get('/api/v1/materials/').json()
    rows = body['results'] if isinstance(body, dict) else body
    assert [r['slug'] for r in rows] == ['live']
    assert public.get('/api/v1/materials/secret/').status_code == 404


# ------------------------------------------------------------------ access
@pytest.mark.parametrize('who', ['anonymous', 'student', 'teacher'])
def test_only_platform_admins_may_use_the_api(who, student_user, teacher_user):
    user = {'anonymous': None, 'student': student_user, 'teacher': teacher_user.user}[who]
    m = material()
    for method, url in (('get', LIST), ('post', LIST), ('get', detail(m)), ('patch', detail(m)), ('delete', detail(m))):
        assert getattr(api(user), method)(url, {}, format='json').status_code in (401, 403)
    assert Material.objects.filter(pk=m.pk).exists()


# ------------------------------------------------------------------ list / create / edit / delete
def test_list_shows_drafts_with_counts_and_filters(admin_user):
    material('live')
    material('draft-one', published=False, description='needle')
    body = api(admin_user).get(LIST).json()
    assert {m['slug'] for m in body['materials']} == {'live', 'draft-one'}
    assert (body['published'], body['drafts']) == (1, 1)
    assert [m['slug'] for m in api(admin_user).get(LIST, {'status': 'draft'}).json()['materials']] == ['draft-one']
    assert [m['slug'] for m in api(admin_user).get(LIST, {'search': 'needle'}).json()['materials']] == ['draft-one']
    assert 'content_html' not in body['materials'][0]


def test_create_is_a_draft_with_clean_html(admin_user):
    r = api(admin_user).post(LIST, {**VALID, 'content_html': VALID['content_html'] + '<script>x()</script>'}, format='json')
    assert r.status_code == 201, r.json()
    created = Material.objects.get(slug='ordering-coffee')
    assert created.is_published is False
    assert created.content_html == VALID['content_html'] == r.json()['content_html']
    assert APIClient().get('/api/v1/materials/ordering-coffee/').status_code == 404


@pytest.mark.parametrize('change, field', [
    ({'slug': 'taken'}, 'slug'), ({'slug': 'Bad Slug'}, 'slug'), ({'category': 'nope'}, 'category'),
    ({'cefr_level': 'D1'}, 'cefr_level'), ({'title': '  '}, 'title'),
])
def test_create_validates(admin_user, change, field):
    material('taken')
    r = api(admin_user).post(LIST, {**VALID, **change}, format='json')
    assert r.status_code == 400 and field in r.json()


def test_publish_and_unpublish(admin_user):
    m = material('lesson', published=False)
    assert api(admin_user).patch(detail(m), {'is_published': True}, format='json').status_code == 200
    assert APIClient().get('/api/v1/materials/lesson/').status_code == 200
    assert api(admin_user).patch(detail(m), {'is_published': False}, format='json').status_code == 200
    assert APIClient().get('/api/v1/materials/lesson/').status_code == 404


def test_edit_keeps_its_own_slug_and_can_detach_files(admin_user):
    m = material('lesson', pdf_file_url='https://assets.example/w.pdf', audio_snippet_url='https://assets.example/a.mp3')
    r = api(admin_user).patch(detail(m), {'slug': 'lesson', 'title': 'Renamed', 'remove_pdf': True}, format='json')
    assert r.status_code == 200
    m.refresh_from_db()
    assert (m.title, m.resolved_pdf_url, m.resolved_audio_url) == ('Renamed', '', 'https://assets.example/a.mp3')
    assert r.json()['pdf_url'] == '' and r.json()['audio_url'] == 'https://assets.example/a.mp3'


def test_only_drafts_can_be_deleted(admin_user):
    live, draft = material('live'), material('draft', published=False)
    r = api(admin_user).delete(detail(live))
    assert r.status_code == 409 and r.json()['code'] == 'material_published'
    assert api(admin_user).delete(detail(draft)).status_code == 204
    assert list(Material.objects.values_list('slug', flat=True)) == ['live']
