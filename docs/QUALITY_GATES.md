# Quality gates (slice Q0)

The machinery behind `PHASE_11_12_EXECUTION_PLAN.md` §5. Every Phase 11/12 slice relies on it; it changes no product
behaviour. All commands run from `backend/` with the venv interpreter (`./venv/Scripts/python.exe` on this machine).

## 1. Guard tests (`backend/tests/guards/`)

Source scans (AST, not regex) with a **baseline allowlist** at the top of each file. They run in the normal suite.

| Guard | File | What fails | Baseline (2026-10-04) |
| :--- | :--- | :--- | :--- |
| (a) tutor status writes | `test_guard_teacher_status_writes.py` | `is_verified` / `is_active` / `status` written on a TeacherProfile (attribute incl. tuple targets, `setattr`, `update(...)` kwargs and `**{...}`, `bulk_update` field lists, TeacherProfile `create/get_or_create/update_or_create` kwargs or `defaults`) outside `teachers/vetting.py`. Receiver heuristic below. | Was 4 files, 8 writes (`admin_api/views.py` 2, `teachers/strikes.py` 2, two seed commands 2+2). **Empty since T1a** (2026-10-04); T1a also added a strict detector over `apps/teachers/` (any `status` write outside `vetting.py`). |
| (b) row locks over joins | `test_guard_select_for_update.py` | a queryset chain with `select_for_update()` whose `of=` is missing or does not name `'self'`, plus `select_related(...)`; either order, multi-line, and split across two statements in one function (`qs = X.select_related(...)` then `qs.select_for_update()`) | 4 files, 9 sites (`credits.py` 3, `grace.py` 3, `webhook_handler.py` 2, `integrations/views.py` 1). PaymentTransaction is zero-tolerance (supersedes the Task 10.7 scan). |
| (c) HTTP timeouts | `test_guard_http_timeouts.py` | `requests` / `httpx` verb calls (also through `import requests as r` and `from requests import post`) without `timeout=`, or with `timeout=None` | empty |
| (d) PII in logs | `test_guard_pii_logging.py` | a logging call (`logger`, `log`, `logging`, or any name/attribute ending in `logger` / `_log`, e.g. `self.logger`) that interpolates (f-string, `%`, `.format`, `+` concatenation, lazy `%s` arg, `extra={...}`) an expression whose name ENDS in email / token / password / phone / secret (snake_case and camelCase split into words; `phone_number`, `email_address` too; `token_count` is not flagged) | 3 files, 8 calls (`bookings/tasks.py` 5, `integrations/email.py` 1, `integrations/services/attendance.py` 2) |
| booking status | `tests/test_booking_state_machine.py::TestNoDirectStatusWrites` (pre-existing, extended) | `x.status = Booking.Status...`, `.update(status=Booking.Status...)`, and a Booking `create/get_or_create/update_or_create` in any status other than `PENDING_PAYMENT` | `seed_phase41_data.py` 3 (demo bookings) |
| (e) silent failures | `test_guard_integrations_silent_failures.py` | in `apps/integrations/`: an `except` whose body is only `pass`, or `return ""` | 2 files, 5 sites (`google_calendar.py` 3, `zoom.py` 2) |
| (f) view permissions | `test_guard_view_permissions.py` | a DRF view class in `apps/*/*views*.py` without `permission_classes` in its body or a same-module base; an `@api_view` without `@permission_classes` | empty |
| (g) migration leaves | `test_guard_migration_leaves.py` | `MigrationLoader.detect_conflicts() != {}` (two leaves in one app after parallel merges) | no allowlist |
| (h) `.env.example` | `test_guard_env_example.py` | a key read in `config/settings/*.py` (`os.environ.get/[]`, `os.getenv`, `env.get/[]`, `_env_bool`, `_int`) that has no `KEY=` / `# KEY=` line in `.env.example` | 25 keys (cancellation/strike/credit policy, refund worker tuning, `SUPPORT_TO_EMAIL`, `BEHIND_NO_PROXY`, `PAYPAL_CAPTURE_CONFIRMS`, `LESSON_DELIVERED_MIN_TEACHER_MINUTES`) |
| ruff baseline | `test_guard_ruff_baseline.py` | a ruff violation outside the baseline, a baseline entry that no longer matches, the baseline growing past 69 pairs, or a C901 / S / B count per (file, code) going up (or down without lowering `RUFF_COUNTS`) | see §2 |

**Receiver heuristic of guard (a)** (no types, only the receiver's source text): availability / strike / slot -> other model;
then teacher / profile / tutor -> tutor (so `request.user.teacher_profile` is a tutor); then user / pack / price / bundle /
booking / transaction / refund / purchase -> other; anything else (`locked`, `qs`) -> unknown; `self` -> tutor only inside
`class TeacherProfile`. `is_verified` is flagged everywhere, `is_active` on tutor and unknown receivers, `status` on tutor
receivers only. The guard parser accepts a UTF-8 BOM and a syntax error names the file.

**The ratchet** (`guards/_scan.py::ratchet_errors`): allowlists are `{file: count}` (not line numbers, so moving code does not
break them). A file not listed, or with more sites than allowed, fails ("NEW offender"). A file with **fewer** sites than
allowed also fails ("lower the number"): the allowlist can only shrink, so a fixed site cannot silently come back.

**How to shrink an allowlist:** fix the site, run the guard, and lower (or delete) the number it names. Never raise a number
or add a file; if a new site is genuinely needed, the rule is wrong and the change needs Architect review.

Each guard file also has detector tests on synthetic snippets (what is caught, what is ignored).

Known limits: (a) matches `status` writes only on tutor-looking receivers (T1a adds a stricter guard for its service);
(d) is deliberately conservative (names only); (f) checks `permission_classes` only - the throttle / typed-schema /
pagination rules of plan §5 are follow-ups. Guard (i), `test_guard_notification_kinds.py` (slice N1a): every registered
notification kind has a renderer, an example payload, a known category (mandatory/optional) and a committed golden snapshot
in `tests/golden/notifications/<kind>.txt`; no orphan snapshot files. No allowlist.

## 2. ruff (`backend/ruff.toml`, CI job `lint`, blocking)

`select = F, B, S, C90`, `max-complexity = 12`. Two sections:
- `[lint.per-file-ignores]` - **policy**: tests may `assert` and use fake passwords (S101/S105/S106); settings modules use
  star imports; `scripts/mutate.py` (and its test) run git/pytest subprocesses.
- `[lint.extend-per-file-ignores]` - **baseline**: the rule codes each file violated on 2026-10-04 (173 violations, 53 files,
  69 file/code pairs). Only remove entries. New files must be clean: `ruff check .` must exit 0.
- Because a file-level ignore would hide a second violation of the same code, `test_guard_ruff_baseline.py::RUFF_COUNTS` pins
  the number of C901 and S* / B* violations per (file, code) (42 violations, 26 pairs). A higher count fails ("NEW"); a lower
  count fails until you lower `RUFF_COUNTS` (and delete the ruff.toml entry when it reaches 0). F codes stay per-file.

No `# noqa` sweep (`--add-noqa` is not allowed); a targeted `# noqa: <code> - reason` on one new line is acceptable.
Version pinned in `requirements-dev.txt` (`ruff==0.14.14`).

## 3. No-network fixture (`tests/network_guard.py`, autouse `no_network`)

Blocks `socket.connect` / `connect_ex` / `getaddrinfo` / `gethostbyname` / `gethostbyname_ex` for non-local hosts. Allowed:
Unix sockets, localhost / loopback, and the hosts in `DATABASE_URL`, `REDIS_URL`, `REDIS_TEST_URL` (plus the addresses they
resolve to), so the Postgres and Redis jobs work. A blocked call raises `NetworkBlocked` (a `RuntimeError`, deliberately
not an `OSError`, so `requests` never turns it into a "provider down, retry" path) AND is recorded: the fixture fails the
test at teardown if any attempt happened, even when application code swallowed the exception (`except Exception`). A test
that provokes a block on purpose takes the record with `network_guard.consume()`. Opt out with `@pytest.mark.allow_network`.

## 4. Fakes (`tests/fakes.py`) and fixtures (`tests/conftest.py`)

They replace the provider at the HTTP / SDK boundary, so the real client code runs. Not autouse.

| Fixture | Fake | Knobs |
| :--- | :--- | :--- |
| `fake_resend` | Resend `POST /emails` (sets `RESEND_API_KEY` to a fake key) | `.sent`, `.requests`, `.fail_with(status, times=1)`, `.fail_with_network_error()` |
| `fake_zoom` | S2S OAuth token, create / get / patch / delete meeting | `.meetings`, `.created`, `.token_requests`, `.set_status(id, 'started'|'not_started'|'error')` (Zoom reports `started` / `waiting`; `error` = HTTP 500), `.fail_next(op, status)` for `token/create/get/update/delete` |
| `fake_google` | Calendar v3 events insert / patch / put / delete (404, then 410 after delete), `freeBusy`, OAuth token | `.events`, `.add_busy(start, end)`, `.revoke()` (`invalid_grant`), `.fail_next(op, status)` |
| `fake_r2` | boto3 S3 client stub returned by `get_r2_client()` | `put_object/head_object/get_object(Range, IfMatch)/copy_object(CopySourceIfMatch)/delete_object/generate_presigned_url`, real `ClientError` codes (`404`, `NoSuchKey`, `PreconditionFailed`), `.objects`, `.calls`, `.presigned` |

Every fake HTTP call must pass `timeout=`; an unexpected URL is an `AssertionError`.

**FakeR2 caveat:** the fixture patches the module attribute `apps.common.r2_client.get_r2_client`. It only takes effect where
the client is looked up through that global at call time: inside `r2_client.py` call `get_r2_client()` by its global name,
and elsewhere use `r2_client.get_r2_client()` (module attribute), never `from apps.common.r2_client import get_r2_client`
(that binds the real function at import time and bypasses the fake). The same applies to the `requests` attribute that
FakeResend / FakeZoom / FakeGoogle replace in `integrations/{email,zoom,google_calendar}.py`.

## 5. Factories (`tests/factories.py`) and the clock

`import factories as f`: `make_user(role=...)`, `make_student()`, `make_admin()`, `make_student_profile()`,
`make_teacher_profile(status='approved', availability=True, **fields)` (plan §3.1 truth table; refuses `is_verified=` /
`is_active=`, which are GeneratedFields since T1a; writes `status=` directly, test-only), `advance_teacher(profile, *statuses,
actor=admin)` (real `transition_teacher`, audit rows; use it to change an existing tutor's status in a test), `make_booking(teacher, student, status=..., funded=False)`,
`advance_booking(booking, *statuses)` (real `transition_booking`, audit rows), `make_payment_transaction(...)`.

`make_booking(status=...)` writes the status directly: the documented test-only path (the booking-status guard scans
`apps/` only). Use `advance_booking` when the transition rules or the audit trail matter.

`apps/common/clock.py::now()` is the time seam for new code (`from apps.common import clock; clock.now()`); the
`frozen_clock` fixture freezes it (`.set(aware_dt)`, `.advance(minutes=5)`). Existing code is not migrated.

## 6. Migration tests (`tests/migration_helpers.py`)

`migrate_and_build(before, after, build, verify)` under `@pytest.mark.django_db(transaction=True)`: migrate back to `before`,
`build(old_apps)` with historical models, migrate to `after`, `verify(new_apps)`, and always migrate back to the latest
leaves. Smoke test: `tests/test_q0_migration_helpers.py` (users 0004 -> 0005).

## 7. Mutation helper (`backend/scripts/mutate.py`)

```
python scripts/mutate.py --file apps/x.py --line 42 --find "<=" --replace "<" --test tests/test_x.py [--test ...]
```
Refuses a dirty tree (`git status --porcelain` non-empty), mutates the first occurrence on that one line, refuses a Python
mutant that does not compile, prints the backup path (recover from it if the process is killed), runs pytest with bytecode
writing off, restores the file byte-for-byte in a `finally` and
verifies it by hash. Exit 0 = KILLED, 1 = SURVIVED, 2 = refused / no verdict. In Windows PowerShell 5.1 escape embedded
double quotes (`'return \"\"'`), see ERR-120. Each slice records its mutants in `docs/mutation/<slice>.md`.

## 8. Per-agent working rules (plan §5)

- Scripts and scratch output go in the agent's own `scratchpad/<slice-id>/` (outside the repo); never run a script you did
  not write; never edit the shared main checkout (only use its venv interpreter).
- Mutate **copies** only: `mutate.py` on a clean worktree, never by hand-editing and "remembering" to revert.
- First commit = red tests only; commit WIP after every green step; keep `docs/slices/<id>.md` (done / remaining / next
  command) current so a replacement agent can resume.
- Write code with editor tools (no heredocs / shell one-liners), run `python -m compileall -q apps tests scripts` after
  multi-file edits, run the **full** suite plus `ruff check .` before hand-off and paste the counts.

## 9. CI (`.github/workflows/quality-gates.yml`)

- `lint` (new, blocking): pinned ruff, `ruff check .`.
- `backend`: installs `requirements-dev.txt`, runs the suite with `--cov=apps --cov=config --cov-report=term:skip-covered`
  (reported, **not** enforced yet) and `--durations=15`.
- Stale OpenAPI: already enforced by `tests/test_api_contract.py::...::test_committed_schema_is_current` (backend job and
  the `API contract` workflow); not duplicated.

Follow-ups (not in Q0): diff coverage on changed lines with the plan §5 thresholds; `pytest-xdist` after an
order-dependence check (`pytest-randomly` / `-p random_order` is not installed); throttle / typed-schema / pagination
guards; pip-audit of the dev requirements.
