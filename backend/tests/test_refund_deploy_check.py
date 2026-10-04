"""Task 10.7: a production check must fail while refunds would go to the manual (money-less) backend."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / 'scripts' / 'check_deploy.py'


def load_script():
    spec = importlib.util.spec_from_file_location('check_deploy_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestRefundBackendProblems:
    @pytest.mark.parametrize('backend', [
        'apps.payments.services.refunds.ManualSandboxRefundGateway',
        'apps.payments.services.refund_gateways.ManualSandboxRefundGateway',
        'some.other.module.ManualSandboxRefundGateway',
        '',
    ])
    def test_the_manual_backend_is_a_problem(self, backend):
        assert load_script().refund_backend_problems(backend)

    def test_the_routing_backend_is_fine(self):
        assert load_script().refund_backend_problems('apps.payments.services.refund_gateways.RoutingRefundGateway') == []

    def test_the_throwaway_environment_selects_the_routing_backend(self):
        env = load_script().throwaway_environment()
        assert env['REFUND_GATEWAY_BACKEND'].endswith('RoutingRefundGateway')


def _run(extra_env):
    env = {k: v for k, v in os.environ.items() if k != 'REFUND_GATEWAY_BACKEND'}
    env.update(extra_env)
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180)


class TestCheckDeployScript:
    def test_a_production_check_fails_while_the_backend_is_manual(self):
        done = _run({'REFUND_GATEWAY_BACKEND': 'apps.payments.services.refunds.ManualSandboxRefundGateway'})
        assert done.returncode != 0
        assert 'REFUND_GATEWAY_BACKEND' in (done.stdout + done.stderr)
        assert 'Unsafe production configuration' in done.stderr      # refused by the boot guard itself, not only by this script

    def test_a_production_check_passes_with_the_routing_backend(self):
        done = _run({})
        assert done.returncode == 0, done.stdout + done.stderr
