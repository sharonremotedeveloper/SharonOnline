# Handoff: Phases 11-12 (Claude -> Codex)

**Written:** 2026-10-05 by Claude (lead architect agent) for Codex, on Anesu MUPESA's instruction ("I need Codex to pick up from where you would have left").
**Read this first, then** `docs/PHASE_11_12_EXECUTION_PLAN.md` (the approved plan; §4 slice table, §5 definition of done, §9 decisions), `docs/QUALITY_GATES.md`, `docs/AI_AGENT_COLLABORATION_RULES.md`, `CLAUDE.md` (workspace root).

> **2026-10-05 update: who does what next is in `docs/PHASE_11_12_TASK_ASSIGNMENTS.md` (Codex, Antigravity, Claude streams, waves, seams). T3/G1/R1 and Video SDK V1-V3 now exist uncommitted in the working tree; read that file before starting anything.**

Claude built Phase 11/12 as parallel slices run by sub-agents in git worktrees, each reviewed by an independent QA agent, then merged onto a local integration branch. You will not have those sub-agents; section 8 says how to do the same work by hand.

---

## 1. Where things stand (updated after the push, 2026-10-05)

**Layers 0 and 1 are on `origin/develop` (`f4c0e0a`) and CI is green on every job**, including `postgres-ledger` (PostgreSQL 16) which ran the Postgres-marked tests and migration round trips of T1a/T1b/T1c/T2/N1a/Z1 for the first time. Local gate at the same commit: backend **3051 passed, 24 skipped**; `ruff`, `manage.py check`, `makemigrations --check`, `scripts/check_deploy.py` clean; frontend `lint` clean, `npm test` 167/167, `check:api-types` ok, `npm run build` ok.

| Layer / slice | What | State |
| :--- | :--- | :--- |
| L0 **Q0, F0, N1c, T1a** | quality gates; money-defect fixes; unified `send_email`; tutor status machine | on `develop`, CI green |
| L1 **T1c** | tutor profile at signup, `/teachers/me/`, `tutor_status` | on `develop`, CI green |
| L1 **N1a** | notifications app core (`notify()`, delivery, alerts, retention) | on `develop`, CI green |
| L1 **T1b** | `bookable()`, staff review actions, admin cancel of a suspended tutor's lessons | on `develop`, CI green |
| L1 **Z1** | Zoom client hardening, host link, payout-hold admin (legacy Meetings path) | on `develop`, CI green |
| L1 **T2** | availability, DST fix, notice at pay time, timezone-change conflicts | on `develop`, CI green (its review fixes were not independently re-reviewed) |
| L1 **T3** uploads, **G1** Google Calendar OAuth, **R1** attendance-payload purge, Zoom Video SDK **V1-V3** | on `develop` (layer-1b integration, 2026-10-05; review items open, see `PHASE_11_12_TASK_ASSIGNMENTS.md` §0.4) | **review fixes next** |
| L2-L4 (N1b, N2a-c, N3, T4a/b, G2, T6, F1, F2, N4, T5, T7, P1/P2, I0-I3) | not started | plan §4 |
| Zoom Video SDK slices V1-V5 | planned in `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md` | **unconfirmed with Anesu, see section 6** |

## 2. Repository state (verified 2026-10-05 after the push and cleanup)

- `origin/develop` = `f4c0e0a`; local `develop` is identical. `main` = `261077c` (promote to `main` only on Anesu's word).
- **Branches are clean:** locally and on the remote only `develop` and `main` exist. All layer-0/1 feature branches, `worktree-agent-*` branches, `integration/layer-1`, the five Dependabot branches and their PRs (#16-#20, closed as superseded) were removed. `.claude/worktrees/` is empty. There are no open PRs.
- The Zoom Video SDK docs written by Antigravity (`ZOOM_VIDEO_SDK_MIGRATION_PLAN.md`, edits to `DECISIONS_D1_D12.md` and `ZOOM_ATTENDANCE.md`) were committed at Anesu's instruction (`d3c5a3f`).
- Dependency bumps applied in one change (`f4c0e0a`): `ruff==0.16.10` (lint ratchet verified unchanged), `django-cors-headers>=4.9.0`, `psycopg2-binary>=2.9.13`, `python-dotenv>=1.2.4`, `pytest-django>=4.14.0`.
- Never `git add -A` blindly. After any `npm run build` / `npm install` in `frontend/` run `git checkout -- frontend/package-lock.json frontend/tsconfig.json frontend/next-env.d.ts` (the build rewrites them: `jsx: preserve`, an optional win32 SWC lockfile entry) and, after regenerating the API, check `git status` for CRLF-only noise on `docs/api/openapi.yaml` and `frontend/src/types/api.generated.ts` (checkout them if the content diff is empty).
- **GitHub account:** `gh auth status` must show `sharonremotedeveloper` active before any push (collaboration Rule 8, registry `docs/TOOL_ACCESS_AND_ACCOUNTS.md`). It was switched to `anesu-metabox` once during this work (logged as a MISMATCH); only Anesu switches it.

## 3. FIRST ACTIONS, in order

1. **Start T3, G1 and R1** from `develop` (section 4), one slice per branch, using the process in section 8. They are independent of each other; T3 must call T1c's `profile.revet_after_vetted_change` when an approved tutor swaps a vetted asset.
2. **Ask Anesu to confirm the Zoom Video SDK decision** (section 6) before building V1-V5 or polishing the legacy Zoom Meetings path.
3. **Have T2's late fixes independently reviewed** if capacity allows: `teachers/services/availability.py::guard_timezone_change` (the 409 on `PATCH /auth/me/`) and the `acknowledge_conflicts` flow.
4. Keep `CLAUDE.md` and `docs/PROGRESS_AND_ROADMAP.md` current after each slice (collaboration Rules 3-4, 7).

## 4. Next slices (plan §4 has the full table)

Reserved numbers so nothing collides (slice ERR block = 120 + 10 x index; leave gaps):
`Q0 120 · F0 130 · Z1 140 · T1a 150 · T1b 160 · T1c 170 · N1c 180 · integrator 190-199 (next free ERR-195) · N1a 200 · T2 210 · T3 220 · G1 230 · R1 240 · N1b 250 · N2a 260 · N2b 270 · N2c 280 · N3 290 · T4a 300 · G2 310 · T6 320 · F1 330 · F2 340 · N4 350 ...` (always take the next free number inside your block; never reuse another slice's).
Migration leaves today: `teachers 0010` (T2 adds 0011), `bookings 0016`, `payments 0022`, `notifications 0001`. G1 will add an `integrations` migration; T3 may add `teachers` 0012+.

- **T3 uploads** (plan §3.6, depends on T1a, call T1c's `profile.revet_after_vetted_change` from the asset commit for approved tutors): quarantine presign prefix `incoming/{uid}/`, `POST /teachers/me/assets/commit/`, magic-byte sniff, ETag pin, random final key, **separate private R2 bucket for vetting documents (needs Anesu: a Cloudflare action)**, fail **closed** in production, audit row per private-document access. Real R2 is not called in tests (`tests/fakes.py::FakeR2`).
- **G1 Google Calendar OAuth** (plan §3.4): `CalendarCredential`, generic `common/crypto` keyring with `INTEGRATION_DATA_KEYS` (not `PAYOUT_DATA_KEYS`), state nonce, wipe the plaintext `User.google_calendar_token`. Needs a Google Cloud project for any live check.
- **R1** (plan §3.7): batched daily purge of `AttendanceAudit.raw_payload` older than 90 days only; exclusions for disputed/unresolved bookings.
- Then L2: N1b (notification API + preferences), N2a-c (events: reminders, confirmations, strikes...), N3 (Resend webhook), T4a (vetting rubric), G2 (busy times into `generate_teacher_slots(..., blocked_intervals=[...])`), T6 (training gate + **idempotent backfill `approved AND training_completed_at IS NULL` before the gate is enabled**), F1 (join gating). **N1a is merged, so N2/N4 should now call `notify()`; do not wire `teachers/vetting.py::notify_status_change` until you have read `TUTOR_STATUS_MACHINE.md` §7 (notify only on outcome statuses; the legacy multi-edge verify path is already gone).**

## 5. Decisions still open for Anesu (do not encode them; ship provisional defaults)

From plan §9 and later: payout batches P1 as a deliberate exception to "execution waits on D-3" (needs a second admin; no self-approval); training gate must be ON before launch (currently OFF, boot warning); a **second private R2 bucket**; PDF tooling for receipts/payslips/memos; **D-4** memo pay-forfeiture (only the 12 h reminder ships); `BOOKING_HORIZON_DAYS=14` and `TUTOR_MIN_NOTICE_MINUTES=10` (provisional); `ADMIN_CANCEL_BONUS_CREDITS=0`, `LATE_WARNING_MINUTES=5`, `CREDIT_EXPIRY_WARNING_DAYS=7`; **should any payment be refused once the notice window has closed even after the lesson started** (T2 kept the old capture-then-late-settlement path; `BOOKING_HORIZON`/`docs/BOOKING_HOLDS.md`); retention/erasure for `TeacherStatusChange` (the Django admin cannot delete a tutor until Phase 14); PayPal sandbox credentials; D-3, D-10, D-12. **Answered:** D-8 (no recording in the MVP, Sharon signed off); staff-only `suspended -> rejected` edge (built in T1b).

## 6. Zoom: the Video SDK plan changes direction (unconfirmed by Claude)

The docs written by Antigravity (committed on `develop` at Anesu's instruction, `d3c5a3f`) describe a decision to move from Zoom Meetings (S2S) to the **Zoom Video SDK** (embedded in-browser classroom; `GET /bookings/<id>/video-token/`; slices V1-V5) and mark as STALE/DEPRECATED: `integrations/zoom.py` meeting provisioning, `zoom_hosts.py` (`HostPicker`), `bookings/services/host_link.py` + `host_link_views.py`, `Booking.zoom_meeting_id/zoom_host_user_id/zoom_start_url`, `ZoomLauncherButton.tsx`, `hostLink.ts`. The files say the decision was approved on 2026-10-05 and the code stays operational until the plan is triggered. Claude could not verify who approved it (the decision file uses Anesu's tick) and asked him; **confirm with Anesu before building V1-V5, and before spending effort on the deferred Z1 polish** (below). Until V5, the Meetings path is live and its safety fixes matter:
- Z1 delivered: S2S token cache, bounded retries, `create_meeting` search-before-retry (agenda marker), `auto_recording: none`, host link endpoint, `HostPicker` default `'me'` (**single host account = concurrent lessons collide: launch blocker until D-9 is implemented, which the SDK plan removes**), tutor classroom fetches the host link on Start.
- Z1 deferred (not done, only needed if the Meetings path stays): staff alert when staff open a host link, exclude held rows from the escrow-release batch query, popup-blocker-safe window opening in `ZoomLauncherButton`, its component test, `CheckConstraint` on `HostLinkIssue`, admin ordering.
- The legacy **staff-hosted lesson holds escrow** until an admin marks `HostLinkIssue` reviewed (`SETTLEMENT_PATHS.md`); it retires with V5.
- F0's attendance rules (never a no-show on `unknown`/no meeting, DISPUTED at lesson end) are the money-safety backbone; any Video SDK attendance (V4) must keep the same semantics.

## 7. Unverified (be honest about these when reporting)

Everything external is mocked: **no PayPal, PayFast, Zoom, Resend, Google or R2 call has ever been made.** Specifically unverified: PayPal request-id retention and PENDING refund lifecycle; Resend 409/24 h idempotency semantics and `attachments[].content_type`; Zoom `GET /users/{host}/meetings` returns `agenda`, host `start_url` (ZAK) lifetime, `Retry-After` format, `past_meetings/{id}/instances` for a never-held meeting (**C2: if it 404s every real no-show becomes DISPUTED**); real Postgres concurrency beyond the Postgres-marked tests (Docker Desktop's engine would not start on Claude's machine, so those run only in CI); the new tutor "Start" flow was never clicked in a browser; PayFast refunds are a manual stub.

## 8. How the work was run (reproduce by hand)

1. **Plan -> tests first -> implement -> mutation table -> full gate -> independent review -> fix -> re-review.** The first commit of a slice contains only red tests (paste the red run into `docs/slices/<ID>.md`). `docs/mutation/<ID>.md` lists a mutant per authorization / state-transition / idempotency / lock / money line, killed by a test (`backend/scripts/mutate.py`, needs a clean tree, restores byte-for-byte). A reviewer who did not write the code attacks the branch read-only and returns BLOCKER/MAJOR/MINOR; fixes get red tests first again. Every slice's QA found real bugs (e.g. PayPal could capture money for a just-suspended tutor; a backfill reverse could delete tutor-entered data), so do not skip the review.
2. **Integration branch.** Merge approved slices in dependency order onto `integration/layer-N`, resolve conflicts keeping both sides, **regenerate (never hand-merge) `docs/api/openapi.yaml` and `frontend/src/types/api.generated.ts`** (`manage.py spectacular --file ../docs/api/openapi.yaml`, then `npm run gen:api`, `npm run check:api-types`), then run the full gate: `pytest -q`, `ruff check .`, `manage.py check`, `makemigrations --check --dry-run`, `scripts/check_deploy.py`, frontend `lint`/`test`/`build`. Integration regularly exposes seams (shrink-only guard baselines must be lowered when a slice fixes an offender; fakes follow module moves): log each as an `ERR-19x`.
3. **Guards are shrink-only.** `backend/tests/guards/*` allowlists and the ruff count baseline may never grow; a fixed offender fails the build until its number is lowered.
4. **Postgres rule (ERR-192).** SQLite hides Postgres failures. A migration with a data step plus schema changes must update each row once and end the data step with `SET CONSTRAINTS ALL IMMEDIATE` on Postgres; `select_for_update()` combined with `select_related()` needs `of=('self',)`; every new lock/constraint/data migration gets a `@pytest.mark.postgres` test, which only CI runs. Pull requests (or a push to `develop`) are how you get CI on it.
5. **Lock order:** booking -> tutor everywhere (`transition_teacher` locks only the tutor; never a booking).
6. Tooling gotchas on this Windows machine: write files with the editor/Write tool, never PowerShell `Set-Content`/heredocs (adds BOMs, mangles quotes); use `git commit -F <file>` for messages with special characters; invoke `backend/venv/Scripts/python.exe` directly (do not activate the venv); PowerShell 5.1 strips embedded double quotes from native-command arguments (`mutate.py` refuses mutants that do not compile); the clock ticks in ~15 ms steps so tests must not rely on distinct `now()` values (ERR-193); Node tests cannot use Vitest (Application Control).
7. Commit trailers: Claude used `Co-Authored-By: Claude Opus 5.5 / Sonnet 5.5 <noreply@anthropic.com>`; use your own attribution.

## 9. Map of what was added (where to read the code)

- **Quality gates:** `backend/tests/guards/`, `tests/fakes.py`, `tests/factories.py`, `tests/network_guard.py`, `tests/migration_helpers.py`, `apps/common/clock.py`, `scripts/mutate.py`, `ruff.toml` (`docs/QUALITY_GATES.md`).
- **Fulfilment / attendance (F0):** `bookings/services/fulfillment.py`, `attendance_probe.py`, `payments/migrations/0022_*` (`docs/ZOOM_ATTENDANCE.md`, `SETTLEMENT_PATHS.md`).
- **E-mail:** `integrations/services/email.py`, `integrations/email.py` (`docs/NOTIFICATIONS.md`).
- **Notifications:** `apps/notifications/` (`NOTIFICATIONS.md` §2, `adr/ADR-0002-notification-delivery.md`, `RUNBOOK_NOTIFICATIONS.md`); beat schedules now 13.
- **Tutor lifecycle:** `teachers/vetting.py`, `review.py`, `profile.py`, models `TeacherStatusChange`, `bookable()`/`operational()` (`docs/TUTOR_STATUS_MACHINE.md`); admin cancel of a suspended tutor's lessons `bookings/services/admin_cancellation.py`.
- **Zoom (Meetings, legacy after the SDK plan):** `integrations/zoom.py`, `zoom_auth.py`, `zoom_hosts.py`, `bookings/services/host_link.py`, `HostLinkIssue`.
- **Availability (T2, on `develop`):** `bookings/services/slot_generator.py`, `notice.py`, `teachers/services/{schedule,availability}.py`, `common/timezones.py`.
- Review/QA transcripts live in each slice's `docs/slices/<ID>.md` and `docs/mutation/<ID>.md`; every failure is in `docs/ERROR_LOGS_AND_RESOLUTIONS.md`.
