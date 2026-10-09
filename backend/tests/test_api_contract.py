"""Task 8.8: /auth/me/ and wallet contracts, OpenAPI schema health + drift guard."""
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.payments.models import CreditBundle

ME = '/api/v1/auth/me/'
WALLET = '/api/v1/payments/credits/'
COMMITTED_SCHEMA = Path(__file__).resolve().parents[2] / 'docs' / 'api' / 'openapi.yaml'


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


def _bundle(user, total=5, remaining=5, name='5-Lesson Pack'):
    return CreditBundle.objects.create(user=user, pack_name=name, total_credits=total, remaining_credits=remaining,
                                       amount_paid=Decimal('40.00'))


@pytest.mark.django_db
class TestMeContract:
    def test_student_sees_summed_remaining_credits(self, student_user):
        _bundle(student_user, 5, 3)
        _bundle(student_user, 10, 10, '10-Lesson Pack')
        body = _client(student_user).get(ME).json()
        assert body['credits'] == 13
        assert body['avatar_url'] == '' and body['is_verified'] is None

    def test_student_with_no_bundles_has_zero_not_null(self, student_user):
        assert _client(student_user).get(ME).json()['credits'] == 0

    def test_credits_are_per_user(self, student_user, admin_user):
        _bundle(admin_user, 5, 5)
        assert _client(student_user).get(ME).json()['credits'] == 0

    def test_teacher_sees_avatar_and_verification_but_no_credits(self, teacher_user):
        teacher_user.avatar_url = 'https://assets.sharonesl.com/a.jpg'
        teacher_user.save()
        body = _client(teacher_user.user).get(ME).json()
        assert body['avatar_url'] == 'https://assets.sharonesl.com/a.jpg'
        assert body['is_verified'] is True and body['credits'] is None

    def test_admin_gets_neutral_values(self, admin_user):
        body = _client(admin_user).get(ME).json()
        assert (body['credits'], body['avatar_url'], body['is_verified']) == (None, '', None)

    def test_the_derived_fields_cannot_be_written(self, student_user):
        res = _client(student_user).patch(ME, {'credits': 999, 'is_verified': True, 'avatar_url': 'https://x.test/a.png'}, format='json')
        assert res.status_code == 200
        body = res.json()
        assert (body['credits'], body['is_verified'], body['avatar_url']) == (0, None, '')

    def test_me_does_not_cost_a_query_per_bundle(self, student_user, django_assert_max_num_queries):
        for _ in range(8):
            _bundle(student_user)
        with django_assert_max_num_queries(6):
            _client(student_user).get(ME)


@pytest.mark.django_db
class TestWalletContract:
    def test_shape_matches_what_the_frontend_types_expect(self, student_user):
        _bundle(student_user, 5, 4)
        body = _client(student_user).get(WALLET).json()
        assert set(body) == {'total_credits', 'ledger', 'bundles'}
        assert body['total_credits'] == 4
        entry = body['ledger'][0]
        assert set(entry) == {'id', 'description', 'credits_delta', 'date', 'type'}
        assert (entry['credits_delta'], entry['type']) == (4, 'opening')
        assert set(body['bundles'][0]) == {'pack_name', 'remaining', 'total', 'purchased_at', 'expires_at'}

    def test_empty_wallet(self, student_user):
        assert _client(student_user).get(WALLET).json() == {'total_credits': 0, 'ledger': [], 'bundles': []}

    def test_only_own_bundles(self, student_user, admin_user):
        _bundle(admin_user)
        assert _client(student_user).get(WALLET).json()['bundles'] == []


def _schema_text(tmp_path):
    target = tmp_path / 'schema.yaml'
    call_command('spectacular', '--validate', '--fail-on-warn', '--file', str(target))
    return target.read_text(encoding='utf-8')


class TestOpenApiSchema:
    def test_generates_without_errors_or_warnings(self, tmp_path):
        text = _schema_text(tmp_path)  # --fail-on-warn raises on any unresolved serializer / type hint
        assert 'openapi: 3.0' in text or 'openapi: 3.1' in text

    def test_webhooks_are_not_published_but_client_endpoints_are(self, tmp_path):
        text = _schema_text(tmp_path)
        assert '/webhook' not in text and '/daily/' not in text.lower().split('paths:')[1].split('components:')[0]
        for path in ('/api/v1/auth/me/', '/api/v1/payments/credits/', '/api/v1/auth/password-reset/', '/api/v1/bookings/reserve/'):
            assert path in text, path

    def test_committed_schema_is_current(self, tmp_path):
        """Regenerate with:  python manage.py spectacular --file ../docs/api/openapi.yaml   (then `npm run gen:api` in frontend)."""
        assert COMMITTED_SCHEMA.exists(), 'docs/api/openapi.yaml is missing'
        norm = lambda t: t.replace('\r\n', '\n').strip()
        assert norm(COMMITTED_SCHEMA.read_text(encoding='utf-8')) == norm(_schema_text(tmp_path)), \
            'API changed but docs/api/openapi.yaml was not regenerated'

    @pytest.mark.django_db
    def test_served_schema_is_admin_only(self, student_user, admin_user):
        assert APIClient().get('/api/schema/').status_code == 401
        assert _client(student_user).get('/api/schema/').status_code == 403
        assert _client(admin_user).get('/api/schema/').status_code == 200
