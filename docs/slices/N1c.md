# Slice N1c - unified `send_email` (PRP 12.2 / 12.3 partial)

Branch `feature/n1c-unified-send-email` (Claude). Plan: `docs/PHASE_11_12_EXECUTION_PLAN.md` §3.2, §4 (N1c row), §5.

## Status
- Done: red tests committed (step 1).
- Remaining: service module, settings + guard + check_deploy, booking confirmation on `send_email`, legacy wrapper, docs, mutation table, full gate.
- Next command (from `backend/`): `venv python -m pytest tests/test_send_email.py tests/test_account_recovery.py -q`

## Red run (first commit, tests only)
```
tests/test_send_email.py
E   ImportError: cannot import name 'email' from 'apps.integrations.services' (unknown location)
ERROR tests/test_send_email.py
1 error in 1.09s

tests/test_account_recovery.py -k TestMailPlumbing
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_console_mode_never_logs_links_or_addresses
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_provider_failure_raises_instead_of_being_swallowed
FAILED tests/test_account_recovery.py::TestMailPlumbing::test_success_sends_to_the_given_address_only
3 failed, 1 passed, 41 deselected in 8.61s
```
