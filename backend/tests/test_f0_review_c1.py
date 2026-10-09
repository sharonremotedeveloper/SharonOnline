"""
Slice F0, re-review condition C1, on Daily.co (D5):
(1) a simulated Daily client (no credentials) is never evidence for a no-show verdict: docker compose runs
    config.settings.local, so a shared/staging stack without credentials must not score fake teacher no-shows;
(2) scripts/check_deploy.py reports missing Daily credentials.
"""
import pytest

import factories as f
from apps.bookings.services.attendance_probe import probe_room
from test_refund_deploy_check import _run, load_script

DAILY_VARS = ('DAILY_API_KEY', 'DAILY_DOMAIN', 'DAILY_WEBHOOK_SECRET')


@pytest.mark.django_db
class TestSimulationNeverScores:
    @pytest.mark.parametrize('debug,flag', [(False, True), (True, False), (True, True), (False, False)])
    def test_a_simulated_roster_is_unknown_whatever_the_flags(self, settings, debug, flag):
        settings.DEBUG, settings.DAILY_SIMULATE_WITHOUT_CREDENTIALS, settings.DAILY_API_KEY = debug, flag, ''
        assert probe_room(f.make_booking()) == 'unknown'


class TestDeployCheckDailyCredentials:
    @pytest.mark.parametrize('missing', DAILY_VARS)
    def test_each_missing_credential_is_a_problem(self, missing):
        env = {'DAILY_API_KEY': 'k' * 20, 'DAILY_DOMAIN': 'sharon.daily.co', 'DAILY_WEBHOOK_SECRET': 's' * 20}
        env[missing] = ''
        problems = load_script().daily_credentials_problems(env)
        assert problems and missing in ' '.join(problems)

    def test_the_throwaway_environment_has_daily_credentials(self):
        env = load_script().throwaway_environment()
        assert all(env.get(name) for name in DAILY_VARS)

    def test_a_production_check_fails_without_daily_credentials(self):
        done = _run({'DAILY_API_KEY': ''})
        assert done.returncode != 0
        assert 'DAILY_API_KEY' in (done.stdout + done.stderr)
