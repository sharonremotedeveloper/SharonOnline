"""The e-mailed code that guards payout bank details (ADR-0003 precondition) and the notices around it."""
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from rest_framework.test import APIClient

import factories as f
from apps.common import clock
from apps.integrations.services.email import EmailResult
from apps.notifications.models import Notification
from apps.payments.models import BankChangeChallenge, TutorPayoutAccount
from apps.payments.services import bank_change_code as codes

pytestmark = pytest.mark.django_db

SETTINGS_URL = '/api/v1/payments/payout-settings/'
CODE_URL = '/api/v1/payments/payout-settings/code/'


@pytest.fixture(autouse=True)
def keys(settings):
    settings.PAYOUT_DATA_KEYS = {'v1': Fernet.generate_key().decode()}
    settings.PAYOUT_DATA_ACTIVE_KEY = 'v1'


@pytest.fixture
def sent(monkeypatch):
    """Capture the one e-mail the service sends so the test can read the code like the tutor would."""
    mails = []

    def fake(to, subject, html, text='', **kwargs):
        mails.append({'to': to, 'text': text, 'html': html, **kwargs})
        return EmailResult('sent')

    monkeypatch.setattr(codes, 'send_email', fake)
    return mails


def body(code, **overrides):
    payload = {'verification_code': code, 'current_password': 'password123', 'account_holder_name': 'T Tutor',
               'account_number': '1234567890', 'bank_name': 'Capitec Bank', 'branch_code': '470010', 'account_type': 'savings'}
    payload.update(overrides)
    return payload


def tutor_client():
    tutor = f.make_teacher_profile()
    client = APIClient()
    client.force_authenticate(tutor.user)
    return tutor, client


def code_from(mails):
    return mails[-1]['text'].split('code is ')[1][:6]


def wrong_code(code):
    return '000000' if code != '000000' else '111111'


class TestRequestingACode:
    def test_the_code_goes_to_the_tutors_own_address_and_only_a_hash_is_stored(self, sent):
        tutor, client = tutor_client()
        assert client.post(CODE_URL).status_code == 202
        assert sent[0]['to'] == tutor.user.email
        code = code_from(sent)
        challenge = BankChangeChallenge.objects.get(user=tutor.user)
        assert code not in challenge.code_hash and len(code) == 6 and challenge.expires_at > clock.now()

    def test_a_new_code_replaces_the_old_one(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        first = code_from(sent)
        client.post(CODE_URL)
        second = code_from(sent)
        if first != second:
            assert not codes.check_code(tutor.user, first)
        assert codes.check_code(tutor.user, second)

    def test_a_failed_email_is_a_503_and_leaves_no_usable_code(self, monkeypatch):
        monkeypatch.setattr(codes, 'send_email', lambda *a, **k: EmailResult('failed', error_code='x'))
        tutor, client = tutor_client()
        assert client.post(CODE_URL).status_code == 503
        assert not BankChangeChallenge.objects.filter(user=tutor.user, used_at__isnull=True).exists()

    def test_only_tutors_may_ask_and_it_is_rate_limited(self, sent, student_user):
        student = APIClient()
        student.force_authenticate(student_user)
        assert student.post(CODE_URL).status_code == 403
        assert APIClient().post(CODE_URL).status_code == 401
        _tutor, client = tutor_client()
        results = [client.post(CODE_URL).status_code for _ in range(6)]
        assert results[:5] == [202] * 5 and results[5] == 429


class TestSavingWithTheCode:
    def test_saving_needs_the_code_and_a_wrong_one_writes_nothing(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        assert client.post(SETTINGS_URL, body(wrong_code(code_from(sent))), format='json').status_code == 400
        missing = body('123456')
        del missing['verification_code']
        assert client.post(SETTINGS_URL, missing, format='json').status_code == 400
        assert not TutorPayoutAccount.objects.filter(tutor=tutor.user).exists()

    def test_the_right_code_saves_once_and_cannot_be_reused(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        code = code_from(sent)
        assert client.post(SETTINGS_URL, body(code), format='json').status_code == 201
        again = client.post(SETTINGS_URL, body(code, account_number='9999888877'), format='json')
        assert again.status_code == 400
        assert TutorPayoutAccount.objects.get(tutor=tutor.user).account_last_four == '7890'

    def test_a_wrong_password_does_not_burn_the_code(self, sent):
        _tutor, client = tutor_client()
        client.post(CODE_URL)
        code = code_from(sent)
        assert client.post(SETTINGS_URL, body(code, current_password='nope'), format='json').status_code == 400
        assert client.post(SETTINGS_URL, body(code), format='json').status_code == 201

    def test_five_wrong_guesses_lock_the_code_even_for_the_right_value(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        code = code_from(sent)
        for _ in range(codes.MAX_ATTEMPTS):
            assert not codes.check_code(tutor.user, wrong_code(code))
        assert not codes.check_code(tutor.user, code)

    def test_an_expired_code_is_refused(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        BankChangeChallenge.objects.filter(user=tutor.user).update(expires_at=clock.now() - timedelta(seconds=1))
        assert not codes.check_code(tutor.user, code_from(sent))

    def test_one_tutors_code_is_useless_for_another(self, sent):
        _a, client_a = tutor_client()
        client_a.post(CODE_URL)
        code = code_from(sent)
        other, client_b = tutor_client()
        assert client_b.post(SETTINGS_URL, body(code), format='json').status_code == 400
        assert not TutorPayoutAccount.objects.filter(tutor=other.user).exists()

    def test_a_saved_change_sends_the_tutor_a_mandatory_notice_without_bank_numbers(self, sent):
        tutor, client = tutor_client()
        client.post(CODE_URL)
        client.post(SETTINGS_URL, body(code_from(sent)), format='json')
        note = Notification.objects.get(user=tutor.user, kind='bank_details_changed')
        assert '1234567890' not in note.body and '7890' not in note.body
        assert note.payload == {'tutor_id': str(tutor.user.pk)}
