"""
Slice F0, re-review condition C1:
(1) simulated Zoom rooms/status need BOTH ZOOM_SIMULATE_WITHOUT_CREDENTIALS and DEBUG (docker compose runs
    config.settings.local, so a shared/staging compose stack without credentials must not score fake teacher no-shows);
(2) scripts/check_deploy.py reports missing Zoom S2S credentials.
"""
import pytest

from apps.integrations.zoom import ZoomError, zoom_client
from test_refund_deploy_check import _run, load_script

MEETING = '55500011122'
ZOOM_VARS = ('ZOOM_ACCOUNT_ID', 'ZOOM_CLIENT_ID', 'ZOOM_CLIENT_SECRET')


class TestSimulationNeedsDebug:
    @pytest.mark.parametrize('debug,flag', [(False, True), (True, False), (False, False)])
    def test_simulation_is_refused_unless_both_are_on(self, settings, debug, flag):
        settings.DEBUG, settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS = debug, flag
        for call in (lambda: zoom_client.create_meeting('t', '2026-10-05T09:00:00Z'),
                     lambda: zoom_client.get_meeting_status(MEETING), lambda: zoom_client.delete_meeting(MEETING),
                     lambda: zoom_client.get_past_instances(MEETING)):
            with pytest.raises(ZoomError):
                call()

    def test_simulation_with_both_on(self, settings):
        settings.DEBUG, settings.ZOOM_SIMULATE_WITHOUT_CREDENTIALS = True, True
        assert zoom_client.create_meeting('t', '2026-10-05T09:00:00Z')['meeting_id']
        assert zoom_client.get_meeting_status(MEETING)['status'] == 'waiting'


class TestDeployCheckZoomCredentials:
    @pytest.mark.parametrize('missing', ZOOM_VARS)
    def test_each_missing_credential_is_a_problem(self, missing):
        env = {name: 'x' for name in ZOOM_VARS}
        env[missing] = ''
        problems = load_script().zoom_credentials_problems(env)
        assert problems and missing in ' '.join(problems)

    def test_all_present_is_fine(self):
        assert load_script().zoom_credentials_problems({name: 'x' for name in ZOOM_VARS}) == []

    def test_the_throwaway_environment_has_zoom_credentials(self):
        env = load_script().throwaway_environment()
        assert all(env.get(name) for name in ZOOM_VARS)

    def test_a_production_check_fails_without_zoom_credentials(self):
        done = _run({'ZOOM_CLIENT_SECRET': ''})
        assert done.returncode != 0
        assert 'ZOOM_CLIENT_SECRET' in (done.stdout + done.stderr)
