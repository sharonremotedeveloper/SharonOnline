"""Tasks 8.5 + 8.6: password reset, password change, e-mail verification, login by e-mail."""
import re
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.integrations.email import EmailDeliveryError, send_email
from apps.users.models import User
from apps.users.tasks import build_message, KIND_PASSWORD_RESET, KIND_VERIFY_EMAIL

BASE = '/api/v1/auth'
OLD_PW = 'Old-pass-12345'
NEW_PW = 'Brand-new-pass-987'


@pytest.fixture
def outbox(monkeypatch):
    """Captures what the Celery task would hand to Resend."""
    sent = []
    monkeypatch.setattr('apps.users.tasks.send_email', lambda to, subject, html, text='': sent.append(
        {'to': to, 'subject': subject, 'html': html, 'text': text}))
    return sent


@pytest.fixture
def run_commit(django_capture_on_commit_callbacks):
    return django_capture_on_commit_callbacks


@pytest.fixture
def user(db):
    return User.objects.create_user(username='aiko', email='Aiko@Example.com', password=OLD_PW, first_name='Aiko')


def _link_params(message):
    url = re.search(r'https?://\S+', message['text']).group(0)
    parsed = urlparse(url)
    return parsed, {k: v[0] for k, v in parse_qs(parsed.query).items()}


def _reset_link(user, outbox, run_commit):
    with run_commit(execute=True):
        assert APIClient().post(f'{BASE}/password-reset/', {'email': user.email}, format='json').status_code == 202
    return _link_params(outbox[-1])[1]


def _confirm(client, params, pw=NEW_PW, **over):
    body = {'uid': params['uid'], 'token': params['token'], 'new_password': pw, 'new_password_confirm': pw}
    body.update(over)
    return client.post(f'{BASE}/password-reset/confirm/', body, format='json')


def _login(ident, pw):
    return APIClient().post(f'{BASE}/token/', {'username': ident, 'password': pw}, format='json')


# ---------------------------------------------------------------- reset request
@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_existing_account_gets_one_email_with_a_link_on_our_frontend(self, user, outbox, run_commit, settings):
        settings.FRONTEND_BASE_URL = 'https://sharonesl.com'
        with run_commit(execute=True):
            res = APIClient().post(f'{BASE}/password-reset/', {'email': 'aiko@example.com'}, format='json')
        assert res.status_code == 202
        assert len(outbox) == 1 and outbox[0]['to'] == 'Aiko@example.com'
        parsed, params = _link_params(outbox[0])
        assert (parsed.scheme, parsed.netloc, parsed.path) == ('https', 'sharonesl.com', '/reset-password')
        assert set(params) == {'uid', 'token'}

    def test_link_is_never_built_from_the_request_host(self, user, outbox, run_commit, settings):
        settings.ALLOWED_HOSTS = ['*']  # let the poisoned Host reach the view, otherwise Django would reject it first
        settings.FRONTEND_BASE_URL = 'https://sharonesl.com'
        with run_commit(execute=True):
            APIClient().post(f'{BASE}/password-reset/', {'email': user.email}, format='json', HTTP_HOST='evil.example',
                             HTTP_X_FORWARDED_HOST='evil.example', HTTP_ORIGIN='https://evil.example')
        assert 'evil.example' not in outbox[0]['text'] and 'evil.example' not in outbox[0]['html']

    def test_unknown_address_gets_the_identical_answer_and_no_mail(self, user, outbox, run_commit):
        with run_commit(execute=True):
            known = APIClient().post(f'{BASE}/password-reset/', {'email': user.email}, format='json')
            unknown = APIClient().post(f'{BASE}/password-reset/', {'email': 'nobody@example.com'}, format='json')
        assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
        assert len(outbox) == 1

    def test_inactive_and_passwordless_accounts_get_nothing(self, user, outbox, run_commit):
        ghost = User.objects.create_user(username='ghost', email='ghost@example.com', password=OLD_PW, is_active=False)
        sso = User.objects.create_user(username='sso', email='sso@example.com')  # unusable password
        with run_commit(execute=True):
            for u in (ghost, sso):
                assert APIClient().post(f'{BASE}/password-reset/', {'email': u.email}, format='json').status_code == 202
        assert outbox == []

    def test_malformed_address_is_a_400(self, db):
        assert APIClient().post(f'{BASE}/password-reset/', {'email': 'not-an-email'}, format='json').status_code == 400
        assert APIClient().post(f'{BASE}/password-reset/', {}, format='json').status_code == 400

    def test_one_inbox_cannot_be_mail_bombed_even_from_many_ips(self, user, outbox, run_commit):
        codes = []
        with run_commit(execute=True):
            for i in range(5):
                codes.append(APIClient().post(f'{BASE}/password-reset/', {'email': user.email}, format='json',
                                              REMOTE_ADDR=f'10.0.0.{i + 1}').status_code)
        assert codes == [202, 202, 202, 429, 429]
        assert len(outbox) == 3

    def test_per_ip_limit(self, db, outbox):
        codes = [APIClient().post(f'{BASE}/password-reset/', {'email': f'u{i}@example.com'}, format='json').status_code for i in range(7)]
        assert codes[:5] == [202] * 5 and codes[5] == 429


# ---------------------------------------------------------------- reset confirm
@pytest.mark.django_db
class TestPasswordResetConfirm:
    def test_happy_path_changes_password_verifies_email_and_kills_old_sessions(self, user, outbox, run_commit):
        refresh = str(RefreshToken.for_user(user))
        params = _reset_link(user, outbox, run_commit)
        res = _confirm(APIClient(), params)
        assert res.status_code == 200
        assert _login(user.username, NEW_PW).status_code == 200
        assert _login(user.username, OLD_PW).status_code == 401
        user.refresh_from_db()
        assert user.email_verified is True
        assert APIClient().post(f'{BASE}/token/refresh/', {'refresh': refresh}, format='json').status_code == 401

    def test_token_is_single_use(self, user, outbox, run_commit):
        params = _reset_link(user, outbox, run_commit)
        assert _confirm(APIClient(), params).status_code == 200
        again = _confirm(APIClient(), params, pw='Another-pass-5551')
        assert again.status_code == 400
        assert _login(user.username, NEW_PW).status_code == 200  # the replay changed nothing

    def test_expired_token_rejected(self, user, outbox, run_commit, settings):
        params = _reset_link(user, outbox, run_commit)
        settings.PASSWORD_RESET_TIMEOUT = -1
        assert _confirm(APIClient(), params).status_code == 400
        assert _login(user.username, OLD_PW).status_code == 200

    def test_token_dies_if_password_changed_another_way(self, user, outbox, run_commit):
        params = _reset_link(user, outbox, run_commit)
        user.set_password('Changed-elsewhere-77'); user.save()
        assert _confirm(APIClient(), params).status_code == 400

    @pytest.mark.parametrize('mutate', [
        lambda p: {**p, 'token': p['token'][:-2] + ('aa' if not p['token'].endswith('aa') else 'bb')},
        lambda p: {**p, 'token': 'garbage'},
        lambda p: {**p, 'uid': 'zzzz'},
        lambda p: {**p, 'uid': ''},
        lambda p: {**p, 'token': 'x' * 5000},
    ])
    def test_forged_inputs_all_get_the_same_generic_400(self, user, outbox, run_commit, mutate):
        params = mutate(_reset_link(user, outbox, run_commit))
        res = _confirm(APIClient(), params)
        assert res.status_code == 400
        assert 'token' in res.json() or 'uid' in res.json()
        assert _login(user.username, OLD_PW).status_code == 200

    def test_a_token_for_one_user_does_not_work_on_another(self, user, outbox, run_commit):
        other = User.objects.create_user(username='other', email='other@example.com', password=OLD_PW)
        params = _reset_link(user, outbox, run_commit)
        from apps.users.tokens import encode_uid
        assert _confirm(APIClient(), {**params, 'uid': encode_uid(other)}).status_code == 400
        assert _login('other', OLD_PW).status_code == 200

    def test_password_rules_apply(self, user, outbox, run_commit):
        params = _reset_link(user, outbox, run_commit)
        assert 'new_password' in _confirm(APIClient(), params, pw='short1').json()
        assert 'new_password' in _confirm(APIClient(), params, pw='12345678901234').json()
        assert 'new_password' in _confirm(APIClient(), params, pw='Aiko@example.com1').json()  # too similar to the e-mail
        mismatch = _confirm(APIClient(), params, new_password_confirm='Different-pass-1')
        assert mismatch.status_code == 400 and 'new_password_confirm' in mismatch.json()
        assert _login(user.username, OLD_PW).status_code == 200  # failed attempts did not burn the token
        assert _confirm(APIClient(), params).status_code == 200

    def test_deactivated_account_cannot_reset(self, user, outbox, run_commit):
        params = _reset_link(user, outbox, run_commit)
        user.is_active = False; user.save()
        assert _confirm(APIClient(), params).status_code == 400

    def test_confirm_is_throttled(self, db):
        codes = [APIClient().post(f'{BASE}/password-reset/confirm/', {'uid': 'a', 'token': 'b', 'new_password': 'x', 'new_password_confirm': 'x'},
                                  format='json').status_code for _ in range(12)]
        assert codes[:10] == [400] * 10 and 429 in codes[10:]


# ---------------------------------------------------------------- change password
@pytest.mark.django_db
class TestPasswordChange:
    def _client(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return c

    def _body(self, **over):
        body = {'old_password': OLD_PW, 'new_password': NEW_PW, 'new_password_confirm': NEW_PW}
        body.update(over)
        return body

    def test_requires_authentication(self, db):
        assert APIClient().post(f'{BASE}/password-change/', self._body(), format='json').status_code == 401

    def test_success_changes_password_and_revokes_refresh_tokens(self, user):
        refresh = str(RefreshToken.for_user(user))
        res = self._client(user).post(f'{BASE}/password-change/', self._body(), format='json')
        assert res.status_code == 200
        assert _login(user.username, NEW_PW).status_code == 200
        assert _login(user.username, OLD_PW).status_code == 401
        assert APIClient().post(f'{BASE}/token/refresh/', {'refresh': refresh}, format='json').status_code == 401

    def test_wrong_current_password(self, user):
        res = self._client(user).post(f'{BASE}/password-change/', self._body(old_password='nope-nope-12'), format='json')
        assert res.status_code == 400 and 'old_password' in res.json()
        assert _login(user.username, OLD_PW).status_code == 200

    def test_new_password_must_differ_and_pass_validators(self, user):
        c = self._client(user)
        assert 'new_password' in c.post(f'{BASE}/password-change/', self._body(new_password=OLD_PW, new_password_confirm=OLD_PW), format='json').json()
        assert 'new_password' in c.post(f'{BASE}/password-change/', self._body(new_password='short', new_password_confirm='short'), format='json').json()
        assert 'new_password_confirm' in c.post(f'{BASE}/password-change/', self._body(new_password_confirm='Mismatch-pass-1'), format='json').json()

    def test_online_guessing_of_the_current_password_is_throttled(self, user):
        c = self._client(user)
        codes = [c.post(f'{BASE}/password-change/', self._body(old_password=f'guess-{i}-aaaa'), format='json').status_code for i in range(12)]
        assert 429 in codes


# ---------------------------------------------------------------- e-mail verification
@pytest.mark.django_db
class TestEmailVerification:
    def _register(self, **over):
        data = {'username': 'newuser', 'email': 'new@example.com', 'password': 'Str0ng-pass-123', 'password_confirm': 'Str0ng-pass-123'}
        data.update(over)
        return APIClient().post(f'{BASE}/register/', data, format='json')

    def _auth(self, user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return c

    def test_registration_sends_a_verification_mail_and_starts_unverified(self, outbox, run_commit, settings):
        settings.FRONTEND_BASE_URL = 'https://sharonesl.com'
        with run_commit(execute=True):
            assert self._register().status_code == 201
        assert len(outbox) == 1 and outbox[0]['to'] == 'new@example.com'
        parsed, params = _link_params(outbox[0])
        assert parsed.path == '/verify-email' and 'token' in params
        assert User.objects.get(username='newuser').email_verified is False

    def test_failed_registration_sends_nothing(self, outbox, run_commit):
        with run_commit(execute=True):
            assert self._register(password_confirm='different').status_code == 400
        assert outbox == []

    def test_confirm_marks_verified_and_is_idempotent(self, outbox, run_commit):
        with run_commit(execute=True):
            self._register()
        token = _link_params(outbox[0])[1]['token']
        for _ in range(2):
            assert APIClient().post(f'{BASE}/verify-email/confirm/', {'token': token}, format='json').status_code == 200
        assert User.objects.get(username='newuser').email_verified is True

    def test_forged_or_expired_token_rejected(self, outbox, run_commit, settings):
        with run_commit(execute=True):
            self._register()
        token = _link_params(outbox[0])[1]['token']
        for bad in (token + 'x', token[:-3] + 'AAA', 'garbage', '', 'x' * 600):
            assert APIClient().post(f'{BASE}/verify-email/confirm/', {'token': bad}, format='json').status_code == 400
        settings.EMAIL_VERIFY_MAX_AGE = -1
        assert APIClient().post(f'{BASE}/verify-email/confirm/', {'token': token}, format='json').status_code == 400
        assert User.objects.get(username='newuser').email_verified is False

    def test_reset_and_verify_tokens_are_not_interchangeable(self, user, outbox, run_commit):
        params = _reset_link(user, outbox, run_commit)
        assert APIClient().post(f'{BASE}/verify-email/confirm/', {'token': params['token']}, format='json').status_code == 400

    def test_changing_the_address_unverifies_and_invalidates_old_links(self, user, outbox, run_commit):
        from apps.users.tokens import make_verify_token
        user.email_verified = True; user.save()
        old_link = make_verify_token(user)
        with run_commit(execute=True):
            res = self._auth(user).patch(f'{BASE}/me/', {'email': 'aiko.new@example.com'}, format='json')
        assert res.status_code == 200 and res.json()['email_verified'] is False
        assert outbox[-1]['to'] == 'aiko.new@example.com'
        assert APIClient().post(f'{BASE}/verify-email/confirm/', {'token': old_link}, format='json').status_code == 400

    def test_editing_other_fields_keeps_verification_and_sends_nothing(self, user, outbox, run_commit):
        user.email_verified = True; user.save()
        with run_commit(execute=True):
            res = self._auth(user).patch(f'{BASE}/me/', {'first_name': 'Aiko-chan', 'email': user.email.upper()}, format='json')
        assert res.status_code == 200 and res.json()['email_verified'] is True
        assert outbox == []

    def test_client_cannot_set_email_verified(self, user):
        res = self._auth(user).patch(f'{BASE}/me/', {'email_verified': True}, format='json')
        assert res.status_code == 200 and res.json()['email_verified'] is False
        user.refresh_from_db()
        assert user.email_verified is False

    def test_resend_requires_auth_skips_verified_and_is_throttled(self, user, outbox, run_commit):
        assert APIClient().post(f'{BASE}/verify-email/', {}, format='json').status_code == 401
        c = self._auth(user)
        with run_commit(execute=True):
            codes = [c.post(f'{BASE}/verify-email/', {}, format='json').status_code for _ in range(7)]
        assert codes[:5] == [202] * 5 and codes[5] == 429
        assert len(outbox) == 5
        user.email_verified = True; user.save()
        outbox.clear()
        from django.core.cache import cache
        cache.clear()
        with run_commit(execute=True):
            assert c.post(f'{BASE}/verify-email/', {}, format='json').status_code == 202
        assert outbox == []


# ---------------------------------------------------------------- login by e-mail (8.6)
@pytest.mark.django_db
class TestLoginByEmail:
    def test_email_and_username_both_work_case_insensitively(self, user):
        for ident in ('aiko', 'AIKO@example.COM', '  aiko@example.com '):
            res = _login(ident, OLD_PW)
            assert res.status_code == 200, ident
            assert 'access' in res.json()

    def test_failures_look_identical_for_unknown_email_and_wrong_password(self, user):
        wrong = _login('aiko@example.com', 'wrong-pass-123')
        unknown = _login('nobody@example.com', 'wrong-pass-123')
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_ambiguous_email_does_not_log_anyone_in(self, user):
        User.objects.create_user(username='aiko2', email='aiko@example.com', password='Other-pass-4321')
        assert _login('aiko@example.com', OLD_PW).status_code == 401
        assert _login('aiko@example.com', 'Other-pass-4321').status_code == 401
        assert _login('aiko', OLD_PW).status_code == 200  # usernames still work

    def test_inactive_account_cannot_log_in_by_email(self, user):
        user.is_active = False; user.save()
        assert _login('aiko@example.com', OLD_PW).status_code == 401

    def test_guessing_via_email_is_throttled_like_via_username(self, user):
        codes = [_login('aiko@example.com', f'guess-{i}-aaaaaa').status_code for i in range(12)]
        assert codes[:5] == [401] * 5 and 429 in codes

    def test_usernames_with_at_sign_are_refused_at_registration(self, db):
        res = APIClient().post(f'{BASE}/register/', {'username': 'victim@example.com', 'email': 'evil@example.com',
                                                     'password': 'Str0ng-pass-123', 'password_confirm': 'Str0ng-pass-123'}, format='json')
        assert res.status_code == 400 and 'username' in res.json()

    def test_registration_mismatch_is_reported_on_password_confirm(self, db):
        res = APIClient().post(f'{BASE}/register/', {'username': 'x1', 'email': 'x1@example.com',
                                                     'password': 'Str0ng-pass-123', 'password_confirm': 'nope'}, format='json')
        assert res.status_code == 400 and 'password_confirm' in res.json()


# ---------------------------------------------------------------- mail plumbing
class TestMailPlumbing:
    def test_content_is_html_escaped(self, db):
        evil = User.objects.create_user(username='e1', email='e1@example.com', password=OLD_PW, first_name='<script>alert(1)</script>')
        for kind in (KIND_PASSWORD_RESET, KIND_VERIFY_EMAIL):
            _, html, _ = build_message(evil, kind)
            assert '<script>' not in html and '&lt;script&gt;' in html

    def test_dev_mode_never_logs_links_unless_debug(self, caplog, settings, monkeypatch):
        monkeypatch.delenv('RESEND_API_KEY', raising=False)
        settings.DEBUG = False
        with caplog.at_level('INFO'):
            send_email('a@example.com', 'subj', '<p>x</p>', 'https://site/reset?token=SECRET')
        assert 'SECRET' not in caplog.text and 'a@example.com' in caplog.text

    def test_provider_failure_raises_instead_of_being_swallowed(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_live_real')
        with mock.patch('apps.integrations.email.requests.post', return_value=mock.Mock(status_code=500)):
            with pytest.raises(EmailDeliveryError):
                send_email('a@example.com', 's', '<p>x</p>')
        import requests
        with mock.patch('apps.integrations.email.requests.post', side_effect=requests.ConnectionError('down')):
            with pytest.raises(EmailDeliveryError):
                send_email('a@example.com', 's', '<p>x</p>')

    def test_success_sends_to_the_given_address_only(self, monkeypatch):
        monkeypatch.setenv('RESEND_API_KEY', 're_live_real')
        with mock.patch('apps.integrations.email.requests.post', return_value=mock.Mock(status_code=200)) as post:
            send_email('a@example.com', 'subj', '<p>x</p>', 'txt')
        assert post.call_args.kwargs['json']['to'] == ['a@example.com']
