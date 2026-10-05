"""
Slice T1c (PRP 11.1): tutor profile at signup, `GET|PATCH /api/v1/teachers/me/`, `/auth/me` tutor status, admin
serializer fake-data removal, price deprecation. Contract: docs/TUTOR_STATUS_MACHINE.md §8.
"""
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings as dj_settings
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

import factories as f
from apps.payments.models import LessonPrice
from apps.teachers.models import TeacherProfile, TeacherStatusChange
from apps.users.models import User

REGISTER = '/api/v1/auth/register/'
AUTH_ME = '/api/v1/auth/me/'
ME = '/api/v1/teachers/me/'
LIST = '/api/v1/teachers/'
BACKEND = Path(__file__).resolve().parents[1]


def _payload(**overrides):
    data = {'username': 'newtutor', 'email': 'newtutor@example.test', 'password': 'Str0ng-pass-123',
            'password_confirm': 'Str0ng-pass-123', 'first_name': 'Thandi', 'last_name': 'M', 'role': 'teacher',
            'country': 'ZA', 'timezone': 'Africa/Johannesburg'}
    data.update(overrides)
    return data


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


# ------------------------------------------------------------------ 1. registration creates the profile
@pytest.mark.django_db
class TestRegistrationAutoProfile:
    def test_teacher_signup_creates_an_applied_profile_with_a_baseline_audit_row(self):
        res = APIClient().post(REGISTER, _payload(), format='json')
        assert res.status_code == 201, res.content
        user = User.objects.get(username='newtutor')
        profile = TeacherProfile.objects.get(user=user)
        assert (profile.status, profile.is_verified, profile.is_active) == ('applied', False, True)
        change = TeacherStatusChange.objects.get(teacher=profile)
        assert (change.from_status, change.to_status, change.actor_user_id) == ('', 'applied', user.pk)
        assert change.actor == 'user:newtutor'

    def test_student_signup_creates_no_tutor_profile(self):
        assert APIClient().post(REGISTER, _payload(role='student'), format='json').status_code == 201
        assert not TeacherProfile.objects.filter(user__username='newtutor').exists()

    def test_profile_creation_failure_rolls_the_user_back(self):
        with mock.patch('apps.teachers.vetting.create_teacher_profile', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                APIClient().post(REGISTER, _payload(), format='json')
        assert not User.objects.filter(username='newtutor').exists()

    def test_signup_goes_through_the_service_as_the_tutor_themself(self):
        from apps.teachers import vetting
        with mock.patch('apps.teachers.vetting.create_teacher_profile', wraps=vetting.create_teacher_profile) as spy:
            APIClient().post(REGISTER, _payload(), format='json')
        user = User.objects.get(username='newtutor')
        spy.assert_called_once()
        args, kwargs = spy.call_args
        assert args[0] == user and kwargs['actor'] == user and kwargs.get('status', 'applied') == 'applied'

    def test_a_new_tutor_is_not_listed_publicly(self):
        APIClient().post(REGISTER, _payload(), format='json')
        ids = [t['id'] for t in APIClient().get(LIST).json()['results']]
        assert str(TeacherProfile.objects.get(user__username='newtutor').id) not in ids


# ------------------------------------------------------------------ 2. GET /teachers/me/
@pytest.mark.django_db
class TestOwnProfileRead:
    def test_tutor_reads_own_profile_with_status(self):
        profile = f.make_teacher_profile(status='applied', headline='Hi', bio='About me', specialties=['TOEIC'])
        body = _client(profile.user).get(ME).json()
        assert body['id'] == str(profile.id)
        assert (body['status'], body['headline'], body['bio'], body['specialties']) == ('applied', 'Hi', 'About me', ['TOEIC'])
        assert body['is_verified'] is False and body['accent'] == 'ZA'

    def test_private_document_locations_are_never_returned(self):
        profile = f.make_teacher_profile(status='applied', tefl_certificate_url='https://private.example.test/cert.pdf')
        body = _client(profile.user).get(ME).json()
        assert 'tefl_certificate_url' not in body and 'tefl_certificate_file' not in body
        assert body['has_tefl_certificate'] is True
        assert 'private.example.test' not in str(body)

    def test_student_is_forbidden(self):
        assert _client(f.make_student()).get(ME).status_code == 403

    def test_admin_without_profile_is_forbidden(self):
        assert _client(f.make_admin()).get(ME).status_code == 403

    def test_anonymous_is_unauthorised(self):
        assert APIClient().get(ME).status_code == 401

    def test_tutor_account_without_profile_gets_404(self):
        assert _client(f.make_user(role='teacher')).get(ME).status_code == 404

    def test_put_is_not_offered(self):
        profile = f.make_teacher_profile(status='applied')
        assert _client(profile.user).put(ME, {'headline': 'x'}, format='json').status_code == 405

    def test_each_tutor_only_ever_sees_their_own_row(self):
        mine = f.make_teacher_profile(status='applied', headline='mine')
        f.make_teacher_profile(status='approved', headline='theirs')
        assert _client(mine.user).get(ME).json()['headline'] == 'mine'


# ------------------------------------------------------------------ 3. PATCH /teachers/me/ (field whitelist)
@pytest.mark.django_db
class TestOwnProfileUpdate:
    def test_whitelisted_fields_are_saved(self):
        profile = f.make_teacher_profile(status='applied')
        res = _client(profile.user).patch(ME, {'headline': ' New headline ', 'bio': 'Bio', 'specialties': ['TOEIC', 'Business English']},
                                          format='json')
        assert res.status_code == 200, res.content
        profile.refresh_from_db()
        assert (profile.headline, profile.bio, profile.specialties) == ('New headline', 'Bio', ['TOEIC', 'Business English'])
        assert res.json()['headline'] == 'New headline'

    @pytest.mark.parametrize('field,value', [
        ('accent', 'UK'), ('intro_video_url', 'https://x.test/v.mp4'), ('intro_video_thumbnail', 'https://x.test/t.png'),
        ('intro_audio_url', 'https://x.test/a.mp3'), ('tefl_certificate_url', 'https://x.test/c.pdf'),
        ('avatar_url', 'https://x.test/a.png'),
    ])
    def test_vetted_or_upload_managed_fields_are_rejected(self, field, value):
        profile = f.make_teacher_profile(status='approved')
        before = getattr(profile, field)
        res = _client(profile.user).patch(ME, {field: value, 'headline': 'ok'}, format='json')
        assert res.status_code == 400 and field in res.json()
        profile.refresh_from_db()
        assert getattr(profile, field) == before and profile.headline == 'TEFL Tutor'
        assert profile.status == 'approved'      # nothing changed, so no re-vet either

    @pytest.mark.parametrize('field,value', [
        ('status', 'approved'), ('is_verified', True), ('is_active', True), ('sla_strikes', 0), ('rating_avg', '5.00'),
        ('rating_count', 99), ('price_per_25min_usd', '1.00'), ('training_completed_at', '2026-01-01T00:00:00Z'),
        ('eskom_area_id', 'area-x'), ('user', 'x'), ('id', 'x'), ('nonsense', 1),
    ])
    def test_service_owned_and_unknown_fields_are_rejected(self, field, value):
        profile = f.make_teacher_profile(status='applied')
        res = _client(profile.user).patch(ME, {field: value}, format='json')
        assert res.status_code == 400 and field in res.json()
        profile.refresh_from_db()
        assert profile.status == 'applied' and profile.sla_strikes == 0

    def test_save_never_writes_status_or_strikes(self):
        profile = f.make_teacher_profile(status='approved')
        calls = []
        real_save = TeacherProfile.save

        def spy(self, *args, **kwargs):
            calls.append(kwargs.get('update_fields'))
            return real_save(self, *args, **kwargs)

        with mock.patch.object(TeacherProfile, 'save', spy):
            assert _client(profile.user).patch(ME, {'bio': 'x'}, format='json').status_code == 200
        assert calls and all(c is not None for c in calls)
        assert all(not {'status', 'sla_strikes'} & set(c) for c in calls)
        assert set(calls[0]) == {'bio', 'updated_at'}

    def test_a_suspension_racing_the_edit_is_not_undone(self):
        profile = f.make_teacher_profile(status='approved')
        from apps.teachers import views as tviews
        real = tviews.TeacherOwnProfileView.get_object

        def get_then_suspend(view):
            obj = real(view)
            f.advance_teacher(TeacherProfile.objects.get(pk=profile.pk), 'suspended')
            return obj                                   # the view now holds a stale 'approved' copy

        with mock.patch.object(tviews.TeacherOwnProfileView, 'get_object', get_then_suspend):
            res = _client(profile.user).patch(ME, {'headline': 'edited'}, format='json')
        assert res.status_code == 200
        assert (res.json()['status'], res.json()['is_active']) == ('suspended', False)   # the live value, not the stale copy
        profile.refresh_from_db()
        assert (profile.status, profile.headline) == ('suspended', 'edited')

    def test_unchanged_values_do_not_touch_the_row(self):
        profile = f.make_teacher_profile(status='applied', headline='Same')
        before = TeacherProfile.objects.get(pk=profile.pk).updated_at
        assert _client(profile.user).patch(ME, {'headline': 'Same'}, format='json').status_code == 200
        assert TeacherProfile.objects.get(pk=profile.pk).updated_at == before

    def test_approved_tutor_editing_non_vetted_fields_stays_approved(self):
        profile = f.make_teacher_profile(status='approved')
        assert _client(profile.user).patch(ME, {'bio': 'Updated bio'}, format='json').status_code == 200
        profile.refresh_from_db()
        assert profile.status == 'approved' and not TeacherStatusChange.objects.filter(teacher=profile).exists()

    @pytest.mark.parametrize('value', ['TOEIC', [1, 2], ['ok', ''], ['x' * 41], [f's{i}' for i in range(11)], {'a': 1}])
    def test_specialties_must_be_a_short_list_of_short_tags(self, value):
        profile = f.make_teacher_profile(status='applied')
        res = _client(profile.user).patch(ME, {'specialties': value}, format='json')
        assert res.status_code == 400 and 'specialties' in res.json()

    def test_specialties_are_trimmed_and_deduplicated_and_may_be_empty(self):
        profile = f.make_teacher_profile(status='applied', specialties=['A'])
        res = _client(profile.user).patch(ME, {'specialties': [' TOEIC ', 'TOEIC', 'Business']}, format='json')
        assert res.status_code == 200 and res.json()['specialties'] == ['TOEIC', 'Business']
        assert _client(profile.user).patch(ME, {'specialties': []}, format='json').json()['specialties'] == []

    @pytest.mark.parametrize('field,size', [('headline', 256), ('bio', 5001)])
    def test_text_lengths_are_capped(self, field, size):
        profile = f.make_teacher_profile(status='applied')
        assert _client(profile.user).patch(ME, {field: 'x' * size}, format='json').status_code == 400

    def test_patch_is_throttled_on_its_own_scope(self):
        from apps.teachers.views import TeacherOwnProfileView
        assert TeacherOwnProfileView.throttle_scope == 'teacher_profile'
        assert 'teacher_profile' in dj_settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']

    def test_patch_rate_limit_answers_429(self, settings):
        from django.core.cache import cache
        cache.clear()
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK,
                                   'DEFAULT_THROTTLE_RATES': {**settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
                                                              'teacher_profile': '2/hour'}}
        from rest_framework.throttling import ScopedRateThrottle
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']):
            profile = f.make_teacher_profile(status='applied')
            c = _client(profile.user)
            codes = [c.patch(ME, {'bio': str(i)}, format='json').status_code for i in range(3)]
            assert codes == [200, 200, 429]
            assert c.get(ME).status_code == 200      # reading is not limited by the write scope
        cache.clear()


# ------------------------------------------------------------------ 3b. service + re-vet hook for T3
@pytest.mark.django_db
class TestRevetHook:
    @pytest.mark.parametrize('field', ['status', 'accent', 'sla_strikes'])
    def test_service_refuses_non_whitelisted_fields_even_without_the_serializer(self, field):
        from apps.teachers.profile import update_own_profile
        profile = f.make_teacher_profile(status='applied')
        with pytest.raises(ValueError):
            update_own_profile(profile, {'headline': 'x', field: 'approved'})
        profile.refresh_from_db()
        assert (profile.headline, profile.status) == ('TEFL Tutor', 'applied')

    def test_approved_tutor_goes_back_to_review(self):
        from apps.teachers.profile import revet_after_vetted_change
        profile = f.make_teacher_profile(status='approved')
        result = revet_after_vetted_change(profile, actor=profile.user, fields=['intro_video_url'])
        assert result is not None and result.changed
        profile.refresh_from_db()
        assert profile.status == 'in_review'
        change = TeacherStatusChange.objects.get(teacher=profile)
        assert (change.from_status, change.to_status, change.actor_user) == ('approved', 'in_review', profile.user)
        assert 'intro_video_url' in change.reason

    @pytest.mark.parametrize('status', ['applied', 'changes_requested', 'submitted', 'in_review'])
    def test_not_yet_live_tutor_is_left_alone(self, status):
        from apps.teachers.profile import revet_after_vetted_change
        profile = f.make_teacher_profile(status=status)
        assert revet_after_vetted_change(profile, actor=profile.user, fields=['accent']) is None
        profile.refresh_from_db()
        assert profile.status == status

    def test_vetted_field_list_covers_video_accent_and_documents(self):
        from apps.teachers.profile import VETTED_FIELDS, WRITABLE_FIELDS
        assert {'accent', 'intro_video_url', 'intro_audio_file', 'tefl_certificate_file'} <= set(VETTED_FIELDS)
        assert not set(VETTED_FIELDS) & set(WRITABLE_FIELDS)
        assert set(WRITABLE_FIELDS) == {'headline', 'bio', 'specialties'}


# ------------------------------------------------------------------ 4. /auth/me tutor status
@pytest.mark.django_db
class TestAuthMeTutorStatus:
    @pytest.mark.parametrize('status', ['applied', 'submitted', 'approved', 'suspended', 'rejected'])
    def test_tutor_sees_their_status(self, status):
        profile = f.make_teacher_profile(status=status)
        assert _client(profile.user).get(AUTH_ME).json()['tutor_status'] == status

    def test_other_roles_get_null(self):
        assert _client(f.make_student()).get(AUTH_ME).json()['tutor_status'] is None
        assert _client(f.make_admin()).get(AUTH_ME).json()['tutor_status'] is None

    def test_tutor_without_profile_gets_null(self):
        assert _client(f.make_user(role='teacher')).get(AUTH_ME).json()['tutor_status'] is None

    def test_it_cannot_be_written(self):
        profile = f.make_teacher_profile(status='applied')
        res = _client(profile.user).patch(AUTH_ME, {'tutor_status': 'approved'}, format='json')
        assert res.status_code == 200 and res.json()['tutor_status'] == 'applied'
        profile.refresh_from_db()
        assert profile.status == 'applied'


# ------------------------------------------------------------------ 5. admin serializer: no fabricated data
@pytest.mark.django_db
class TestAdminApplicationSerializerHasNoFakeData:
    def test_real_eskom_area_and_inverter_values(self):
        from apps.admin_api.serializers import PendingTeacherApplicationSerializer
        profile = f.make_teacher_profile(status='applied', eskom_area_id='eskde-10-fourways', has_inverter_backup=False)
        data = PendingTeacherApplicationSerializer(profile).data
        assert (data['eskom_area'], data['has_inverter']) == ('eskde-10-fourways', False)

    def test_missing_area_is_null_not_a_placeholder(self):
        from apps.admin_api.serializers import PendingTeacherApplicationSerializer
        data = PendingTeacherApplicationSerializer(f.make_teacher_profile(status='applied')).data
        assert data['eskom_area'] is None and data['has_inverter'] is False

    def test_no_hardcoded_placeholder_remains_in_the_source(self):
        source = (BACKEND / 'apps' / 'admin_api' / 'serializers.py').read_text(encoding='utf-8')
        assert 'Johannesburg Block' not in source
        assert "getattr(obj, 'has_inverter_backup', True)" not in source


# ------------------------------------------------------------------ 6. price deprecation
@pytest.mark.django_db
class TestPriceDeprecation:
    def test_public_list_reports_the_catalog_price_not_the_tutor_column(self):
        f.make_teacher_profile(status='approved', price_per_25min_usd=Decimal('3.00'))
        LessonPrice.objects.filter(currency='USD').update(amount=Decimal('11.00'))
        tutor = APIClient().get(LIST).json()['results'][0]
        assert tutor['price_per_25min_usd'] == '11.00'

    def test_public_detail_reports_the_catalog_price(self):
        profile = f.make_teacher_profile(status='approved', price_per_25min_usd=Decimal('3.00'))
        LessonPrice.objects.filter(currency='USD').update(amount=Decimal('12.50'))
        assert APIClient().get(f'{LIST}{profile.id}/').json()['price_per_25min_usd'] == '12.50'

    def test_missing_catalog_price_is_null_not_an_error(self):
        f.make_teacher_profile(status='approved')
        LessonPrice.objects.filter(currency='USD').update(is_active=False)
        res = APIClient().get(LIST)
        assert res.status_code == 200 and res.json()['results'][0]['price_per_25min_usd'] is None

    def test_catalog_is_read_once_per_response(self, django_assert_max_num_queries):
        for _ in range(3):
            f.make_teacher_profile(status='approved')
        with mock.patch('apps.teachers.serializers.lesson_price', wraps=__import__(
                'apps.payments.services.pricing', fromlist=['lesson_price']).lesson_price) as spy:
            assert len(APIClient().get(LIST).json()['results']) == 3
        assert spy.call_count == 1

    def test_max_price_filter_is_gone(self):
        f.make_teacher_profile(status='approved', price_per_25min_usd=Decimal('50.00'))
        assert len(APIClient().get(LIST, {'max_price': '1'}).json()['results']) == 1

    def test_openapi_marks_the_field_deprecated(self, tmp_path):
        import yaml
        from django.core.management import call_command
        target = tmp_path / 'schema.yaml'
        call_command('spectacular', '--file', str(target))
        schema = yaml.safe_load(target.read_text(encoding='utf-8'))
        for component in ('TeacherList', 'TeacherDetail'):
            field = schema['components']['schemas'][component]['properties']['price_per_25min_usd']
            assert field.get('deprecated') is True and field.get('readOnly') is True
        params = [p['name'] for p in schema['paths']['/api/v1/teachers/']['get'].get('parameters', [])]
        assert 'max_price' not in params


# ------------------------------------------------------------------ 7. specialties optional (ERR-158 follow-up)
@pytest.mark.django_db
def test_specialties_may_be_blank_on_the_model():
    profile = f.make_teacher_profile(status='applied', specialties=[])
    try:
        profile.full_clean(exclude=['user'])
    except ValidationError as exc:       # pragma: no cover - the assertion below reports it
        pytest.fail(f'specialties=[] should be valid: {exc.message_dict}')
