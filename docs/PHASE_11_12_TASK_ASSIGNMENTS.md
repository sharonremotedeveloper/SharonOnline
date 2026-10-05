# Phases 11-12: who does what next (Codex, Antigravity, Claude)

**Written:** 2026-10-05 by Claude (lead architect agent) on Anesu MUPESA's instruction · **Supersedes** the "next slices" list in `HANDOFF_PHASE_11_12.md` §3-4 for *assignment* (that file stays the reference for process, gates and gotchas) · **Plan of record:** `PHASE_11_12_EXECUTION_PLAN.md` §4 (slice table) · **Video plan:** `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md`.

## 0. Where we are (observed 2026-10-05, working tree of `Project-files`, branch `develop` = `origin/develop` `f4c0e0a`)

- Layers 0 and 1 (Q0, F0, N1c, T1a, T1c, N1a, T1b, Z1, T2) are pushed, CI green.
- **Codex** has implemented **T3, G1, R1** in the shared working tree (uncommitted): `teachers/assets.py` + migration `teachers 0012`, `common/crypto.py`, `integrations 0002/0003`, `bookings/retention.py` + `bookings 0017`, `tests/test_t3_g1_r1.py`.
- **Antigravity** has implemented the **Video SDK slices V1-V3** in the same tree (uncommitted): `integrations/services/video_sdk.py`, `bookings/video_views.py` (`GET /bookings/<id>/video-token/`, routed), `ZOOM_VIDEO_SDK_*` settings + guard, `VideoSdkClassroom.tsx`, `lib/videoSdk.ts`, both classroom pages, `@zoom/videosdk` in `package.json`.
- Claude ran the three new backend test files only: **30 passed**. Nothing else was verified (no full suite, no frontend build, no review). Treat both bodies of work as *unreviewed*.
- **Anesu's go for the Video SDK:** his message of 2026-10-05 ("antigravity just finished the zoom sdk and inbrowser zoom") is taken as confirmation of D-9 and as the go for **V1-V4**. **V5 (retire the legacy Meetings columns and files) is NOT approved**: it is destructive and needs his explicit go after the SDK has been exercised against a real Zoom Video SDK app (§6).
- **Risk to fix first:** two agents wrote into one checkout. Shared files are touched by both streams: `config/settings/base.py`, `guard.py`, `scripts/check_deploy.py`, `.env.example`, `ruff.toml`, `docs/api/openapi.yaml`, `frontend/package(-lock).json`, `docs/PHASE_11_12_EXECUTION_PLAN.md`, `PROGRESS_AND_ROADMAP.md`. Step 1 splits them cleanly.

## 0.4 STEP 1 DONE (2026-10-05): T3, G1, R1 and V1-V3 are merged and pushed to `develop`

Landed as one unit (the combined tree was gated as a whole, then committed per owner): backend **3089 passed, 24 skipped** (two consecutive full runs; one earlier run had a single unidentified flaky failure, to be chased by the next integrator), ruff, `manage.py check`, `makemigrations --check`, `check_deploy` clean; frontend lint, 167 tests, `check:api-types`, `build` green; `openapi.yaml` and `api.generated.ts` regenerated. Integrator review found and fixed two real defects (ERR-195 gcal reconcile crash; **ERR-196 the video-token endpoint gave a classroom to unpaid/settled lessons and leaked booking status to strangers**). `classroom_url(booking, role)` now exists (`bookings/services/classroom_links.py`). **Not yet done by Claude:** the V4 attendance contract test (A1 waits for it) and the deeper T3/G1 review items below.

Open review items for the owners (none blocks the push): **Codex** (C0): the Google callback returns provider/exception text to the browser (return a fixed message, log the type only); R2 copy happens inside `transaction.atomic`, so a rolled-back commit can orphan an object (add a cleanup/`on_commit` ordering note and test); the commit endpoint and callback have no typed serializers (`OpenApiTypes.OBJECT`: guard baseline must not grow); mutation tables `docs/mutation/{T3,G1,R1}.md` and `docs/slices/{T3,G1,R1}.md` do not exist yet. **Antigravity** (A0): require a 32+ character `ZOOM_VIDEO_SDK_SECRET` in the production guard (tests warn about an 18-byte key), add a pagination-free typed schema review, frontend tests for `videoSdk.ts`, browser verification, `docs/mutation/V1-V3.md`.

## 0.46 PROGRESS (2026-10-05, evening; `develop` `cfd21b3`)

**Done by Claude and on `develop`:** V4 contract + seam (`video_provider.py`, `video_session_probe.py`, 14 tests; **Antigravity may
start V4**, see `docs/slices/V4-contract.md`), T4a (rubric / asset integrity / review packet / tutor feedback / submitted alert), T6
(training modules + completion + `backfill_training_completed`), T5a (application funnel backend, staff lead-in removed), docs truth
for SDK attendance (`ZOOM_ATTENDANCE.md`, `SETTLEMENT_PATHS.md`), ADR-0003 (payouts, design only). **Merged from Codex:** the T3/G1/R1
review fixes and N1b (notification API) after a fix round (ERR-198). Backend 3217 passed; two flaky tests fixed on the way (ERR-197,
ERR-199). **Contract changes the frontend must follow (T4b / T5b / T7):** approve needs `rubric` (+ `reviewed_assets`) and
`PATCH verify` without one is 400; the pending queue lists `submitted` / `in_review` only; new endpoints
`GET /admin/teachers/<id>/review-packet/`, `/teachers/me/application/` (+ `submit/`), `/teachers/me/training/`, `/notifications/*`;
`GET /teachers/me/` has `review_feedback`.
**Next for Codex:** N2a-c (use `classroom_url()`), N3, G2, N4, T3b; rebase on `develop` first (new migrations teachers 0013/0014, new
settings). **Next for Antigravity:** finish the V1-V3 review items, build V4 against the contract, then F2 (N1b is on `develop`), T4b, T5b,
T7. **Next for Claude:** review the branches that arrive, wave integration, P1 only on Anesu's go. **Environment note:** a worktree has no
backend `.env`; `tests/test_refund_deploy_check.py` reads the process environment and can fail without PayPal variables (it passes in CI
and in the main checkout).

## 0.45 WORKTREES READY (2026-10-05, from `develop` `db3e966`)

| Agent | Worktree (under `Project-files/.claude/worktrees/`) | Branch | First task |
| :-- | :-- | :-- | :-- |
| Codex | `codex-n1b` | `feature/n1b-notification-api` | N1b (ERR 250) |
| Codex | `codex-t3-fixes` | `fix/t3-g1-r1-review` | C0 review items (ERR 220/230/240) |
| Antigravity | `antigravity-v1-v3-fixes` | `fix/v1-v3-review` | A0 (ERR 360-380), then V4 design/build |
| Claude | `claude-t4a` | `feature/t4a-vetting-backend` | T4a (ERR 300), then V4 contract test, T6 |

Using a worktree: `cd` into it and stay there. **Python:** the venv exists only in the main checkout; run `"C:/Dev/Active Projects/Sharon Online/Project-files/backend/venv/Scripts/python.exe" -m pytest ...` with the worktree's `backend/` as the working directory (verified). **Frontend:** run `npm ci` once inside the worktree's `frontend/`. Merge back by rebasing on `origin/develop` and telling Claude (integrator) which branch is ready; do not push to `develop` yourself unless Claude says so. After `npm run build` restore `frontend/package-lock.json`, `tsconfig.json`, `next-env.d.ts` if they changed.

## 0.5 FINAL KICKOFF (2026-10-05): what starts now

**Decisions closed for kickoff:** Video SDK direction and V1-V4 = go (Anesu's instruction to start all three streams, 2026-10-05; if that is wrong he says so and V4 stops). V5 = still blocked. Private R2 bucket `esl-platform-private-vetting` and the Google Cloud project/OAuth client are provisioned (see `TOOL_ACCESS_AND_ACCOUNTS.md`; credentials live only in `backend/.env`, never in files). **Still missing:** the Zoom Video SDK app (key/secret/webhook secret) and the Resend domain. Both only block *live* checks; V4 and N3 are built and tested on mocks.

**Rule:** the shared checkout is retired as a workspace. Step 1 is done (§0.4); every agent now works only in its own worktree under `.claude/worktrees/` created from the current `origin/develop`: `codex-n1b`, `codex-t3-fixes`, `antigravity-v1-v3-fixes`, `claude-t4a`. Never edit the main checkout.

| Agent | Start now (no dependency on Step 1) | Starts when "worktrees ready" | Starts after the Step 1 merge |
| :-- | :-- | :-- | :-- |
| **Claude** | Step 1: split, worktrees, `classroom_url()`, V4 contract test, then reviews | review T3/G1/R1 and V1-V3, merge train | T4a, T6 (own worktrees off `develop`) |
| **Codex** | **N1b** in `.claude/worktrees/codex-n1b` off `develop` (needs only N1a; no shared file edits, OpenAPI regenerated by Claude) | fix review findings on T3/G1/R1 (C0) | N2a-c (after `classroom_url()` lands), N3, G2, N4, T3b |
| **Antigravity** | Read `PHASE_11_12_TASK_ASSIGNMENTS.md` and `ZOOM_ATTENDANCE.md`; draft the V4 design note in `docs/slices/V4.md` (webhook events, heartbeat shape, how each maps to the F0 tri-state) | A0: tests, browser check, `HardwareCheckModal` fake latency | A1 V4 build (after Claude's contract test is on `develop`), then A2-A5 |

### Copy-paste kickoff prompts

**Codex:** "Read `Project-files/docs/PHASE_11_12_TASK_ASSIGNMENTS.md` (§0.5, §2 Codex table) and `HANDOFF_PHASE_11_12.md` §8. Start slice N1b now in a new worktree off `develop` (ERR block 250, tests first, notification API + preferences per plan §3.2, no edits to shared files: hand `urls.py`/settings/celery snippets to Claude in `docs/slices/N1b.md`). Do not touch the shared checkout. When Claude posts 'worktrees ready', switch to `.claude/worktrees/codex-t3-g1-r1` and address review findings for T3/G1/R1 (blocks 220/230/240) before continuing N2a-c. Verify account per Rule 8 before any live R2/Google/Resend call."

**Antigravity:** "Read `Project-files/docs/PHASE_11_12_TASK_ASSIGNMENTS.md` (§0.5, §2 Antigravity table, §3 seams) and `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md`. Do not edit the shared checkout. Now: write `docs/slices/V4.md` (design only). When Claude posts 'worktrees ready', continue V1-V3 in `.claude/worktrees/antigravity-v1-v3` (A0: tests, browser verification, remove fake latency in `HardwareCheckModal`, ERR blocks 360-380). V4 starts only after Claude's attendance contract test is on `develop`, and must keep F0 semantics (unknown or missing evidence is never a no-show). V5 is not approved. Never put the Zoom SDK secret in any file; Rule 8 applies before any live Zoom call."

**Claude (me):** executing Step 1 as soon as Anesu says go on this document.

**Anesu, your only open actions:** (1) create the Zoom Video SDK app and put key/secret/webhook secret into `backend/.env` (plan §5), (2) a domain + DNS for Resend, (3) later: go/no-go on V5 and on P1 payouts.

## 1. Order of work (everyone, in this order)

**Step 1 - Land the working tree (Claude drives, today; Codex and Antigravity pause new code, answer questions only).**
1. Claude splits the tree by ownership into two branches off `develop`: `feature/t3-g1-r1` (Codex's files) and `feature/video-sdk-v1-v3` (Antigravity's files); shared files are resolved by hand keeping both sides; `openapi.yaml` and `api.generated.ts` are **regenerated, never merged**.
2. Each branch must show: red-tests-first commit or the equivalent evidence in `docs/slices/<ID>.md`, `docs/mutation/<ID>.md`, full gate (`pytest -q`, `ruff check .`, `manage.py check`, `makemigrations --check`, `scripts/check_deploy.py`; frontend `lint`, `test`, `check:api-types`, `build`), ERR entries in the slice's block.
3. Claude reviews both read-only (BLOCKER/MAJOR/MINOR): see the review checklist in §5. Owners fix; Claude merges in order **R1 -> G1 -> T3 -> V1-V3**, regenerates the contracts, runs the full gate, pushes `develop`, watches CI (incl. `postgres-ledger`).
4. From now on **every agent works in its own git worktree** (`.claude/worktrees/<agent>-<slice>`), never in the shared checkout.

**Step 2 - parallel streams (below), each on its own branch/worktree, merged by Claude in the train of §4.**

## 2. Assignments

Stream ownership follows the code each agent already holds, so context is not re-derived.

### Codex: notifications, calendar and uploads stream (backend)

| Order | Slice | What | Depends | ERR block |
| :-- | :-- | :-- | :-- | :-- |
| C0 | **T3, G1, R1** | Finish after review: fix review findings, mutation tables, slice docs, Postgres-marked tests for constraints/migrations. T3 must call T1c's `profile.revet_after_vetted_change` for approved tutors. | Step 1 | 220 / 230 / 240 |
| C1 | **N1b** | Notification API (`GET /notifications/`, `/unread-count/`, `POST /<id>/read/`, `/read-all/`, `GET|PATCH /preferences/`), mandatory-kind set enforced in code, typed serializers, pagination, OpenAPI. **This is the contract freeze trigger for F2.** | N1a | 250 |
| C2 | **N2a, N2b, N2c** | Events on `notify()`: reminders T-24h/T-1h/T-10m + late warning + no-show + memo 12 h (`bookings/services/reminders.py`); confirmed/cancelled/rescheduled with generation keys; strike/suspension/vetting outcome/bank-change/calendar-revoked. **Join links in every mail and reminder come from `bookings/services/classroom_links.py::classroom_url(booking, role)` (Claude writes it in Step 1; it returns `/student/classroom/<id>` or `/teacher/classroom/<id>`), never `zoom_join_url`.** Calendar events carry the same URL. | N1a, F0, T1b | 260 / 270 / 280 |
| C3 | **N3** | Resend webhook (Svix verify, timing-safe), bounce suppression. | N1a | 290 |
| C4 | **G2** | Busy times as a hint: `generate_teacher_slots(..., blocked_intervals=[...])` for the public list only, fail open, per-tutor fan-out, event update keeps the event id. | G1, T2 | 310 |
| C5 | **N4, T3b** | Wrap Eskom/refund/payment-failure senders in `notify()`; admin material PDFs/audio commit. | N1a / T3 | 350 / 470 |

Infrastructure status for live checks: Cloudflare private bucket `esl-platform-private-vetting` and Google Cloud project/OAuth client are provisioned (2026-10-05). Resend domain SPF/DKIM remains blocked: no domain is currently owned/configured, and no DNS provider zone is available. Once a domain and DNS provider are supplied, add the Resend records and update this handoff.

### Antigravity: classroom (Video SDK) and frontend stream

| Order | Slice | What | Depends | ERR block |
| :-- | :-- | :-- | :-- | :-- |
| A0 | **V1-V3 finish** | After review: fix findings; component/unit tests for `videoSdk.ts` and `VideoSdkClassroom.tsx` (Node test runner, not Vitest); verify in the built-in browser with a stubbed token (device selection, mute, leave, error and "too early" states, mobile width); remove the fake latency in `HardwareCheckModal` (this replaces plan slice F1). Token endpoint must never return the SDK secret. | Step 1 | 360 / 370 / 380 |
| A1 | **V4 attendance telemetry** | Video SDK webhook receiver (`/integrations/video-sdk/webhooks/`, timing-safe HMAC, URL-validation challenge) and/or client heartbeat -> `AttendanceAudit`, feeding the existing completion rule (>= 20 min) and T+10 probe. **Semantics are fixed by F0 and must not change:** an unknown/missing/errored signal is never a no-show (it ends DISPUTED); a booking with no session evidence is never scored on silence. Claude supplies the contract test in §3 first. | A0, V2 | 390 |
| A2 | **F2** notification centre | Bell, list, preferences page, jittered visibility-aware polling, a11y. Branches from the contract-freeze tag. | C1 + freeze | 340 |
| A3 | **T4b** admin vetting UI | Extend `/admin/teachers/vetting` onto the T4a API. | T4a + freeze | 410 |
| A4 | **T7a-c** | Teacher profile / schedule / dashboard on real data, remove the remaining mock fallbacks (per page group). | T1c, T2, T3, T4a | 440 / 450 / 460 |
| A5 | **T5b** application funnel UI | After T5a. | T5a | 430 |
| A6 | **V5** legacy cleanup | **Only on Anesu's explicit go** after the sandbox exercise (§6). | A1 live-verified | 400 |

Needs from Anesu: a **Zoom Video SDK app** (SDK key/secret, webhook secret token) created from `sharonremotedeveloper@gmail.com` per `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md` §5. Collaboration Rule 8 applies: verify the account against `TOOL_ACCESS_AND_ACCOUNTS.md` and log it in §4 before any live Zoom call; never put the secret in a file.

### Claude: integrator, reviewer, tutor-lifecycle stream

| Order | Slice | What | Depends | ERR block |
| :-- | :-- | :-- | :-- | :-- |
| L0 | **Step 1 integration + reviews** | Split, review, merge, regenerate contracts, gate, push, CI. Write `classroom_url()` and the V4 contract test (§3). | - | 190-199 (next ERR-195) |
| L1 | **T4a** vetting backend | Rubric (4 criteria x 1-5), reasons, suspend/reactivate with the bookings decision, audit, staff work queue, vetting-submitted admin alert. | T1b, N1a, T3 | 300 |
| L2 | **T6** training infra | Models, progress, gate flag, **idempotent backfill `approved AND training_completed_at IS NULL` before the gate is enabled**. | T1b | 320 |
| L3 | **T5a** funnel backend | `TeacherApplication`, step progress, speed test, power-backup declaration, submit `applied -> submitted`; `/auth/me` status. | T3, T4a | 420 |
| L4 | **I1, I2, I3** | Wave-end integration: merge the wave on a scratch branch in train order, full gate plus stream E2E tests (`tests/integration/test_stream_*.py`), tag the **contract freeze**. | each wave | 190-199 |
| L5 | **P1/P2 payouts** | **Design + ADR only** (maker-checker, no-double-pay constraint, CSV-only decrypt path). Build only after Anesu's go (plan §9 item 2; needs a second admin). | Anesu | 480+ |
| L6 | **Docs truth** | Rewrite the Zoom sections of `ZOOM_ATTENDANCE.md`/`SETTLEMENT_PATHS.md` for the SDK; keep `CLAUDE.md`, `PROGRESS_AND_ROADMAP.md`, `HANDOFF_PHASE_11_12.md` current; sign-off on T3, G1, T1a-style architecture items. | continuous | - |

## 3. How it fits together (the seams)

```
                 Step 1: land T3/G1/R1 + V1-V3, regenerate contracts, CI green
                                         |
   Codex ───────────── N1b ──► (contract freeze #1: notifications API)
     |                   |                          |
     |   N2a/b/c ◄── classroom_url() ──────────────┼── Antigravity V3 classroom routes
     |   N3, G2, N4, T3b                           |
     |                                    A2 F2 notification centre
   Claude ── T4a ──► (freeze #2: vetting API) ──► A3 T4b admin vetting UI
        |── T6 ──► T5a ──► (freeze #3) ──► A5 T5b funnel UI;  A4 T7a-c real data
   Antigravity ── V4 attendance ──► live sandbox check ──► [Anesu go] ──► V5 cleanup
```

The seams that must not drift:
1. **Join link.** One function, `classroom_url(booking, role)`, used by Codex's mails/reminders/calendar events and Antigravity's pages. Until V5 the Zoom fields stay in the model but are never shown to users.
2. **Attendance and money.** V4 only *produces evidence* for `AttendanceAudit`; verdicts stay in the F0/settlement code (`attendance_probe.py`, `settlement.py`). Claude's contract test (written in L0, before A1 starts) asserts: no signal -> no no-show verdict, DISPUTED at lesson end; >= 20 min dwell -> completion; tutor never joined with student present -> tutor no-show only with positive evidence. A1 is done when that test passes unchanged.
3. **Notifications vs reminders.** N2a decides *when* to remind from booking times; it does not read attendance. The "tutor late" warning keeps using the F0 tri-state and the provisional `LATE_WARNING_MINUTES=5`.
4. **Contracts.** Backend slices ship OpenAPI changes as part of their branch; Claude regenerates `openapi.yaml` and `api.generated.ts` after every merge. Frontend slices branch from the freeze tag and may not change a response shape; if they need to, they ask the backend owner.
5. **Locks and invariants stay as in CLAUDE.md**: booking -> tutor lock order; status changes only through `transition_booking()` / `transition_teacher()`; all new e-mail through `send_email`/`notify()`; no float money; guard baselines shrink only.

## 4. Merge train and waves

| Wave | Content | Gate |
| :-- | :-- | :-- |
| W0 | Step 1: R1, G1, T3, V1-V3 | full gate + CI Postgres job; tag `layer-1b` |
| W1 | Codex C1-C2, Antigravity A0-A1, Claude L1-L2 | I1: scratch-branch merge, full gate; tag `contract-freeze-w1` (N1b, T4a, V2) |
| W2 | Codex C3-C5, Antigravity A2-A4, Claude L3 | I2; tag `contract-freeze-w2` (T5a) |
| W3 | Antigravity A5 (and A6 if approved), Claude P1 if approved, QA sweep | I3, then promotion to `main` only on Anesu's word |

Train order inside a wave: backend slices first (dependency order), then frontend slices. One integrator (Claude) owns `config/celery_schedule.py`, `settings/base.py`, `urls.py`, `docs/api/openapi.yaml`, `frontend/src/types/api.generated.ts`, `package.json`/lockfile; other agents hand over registrations as snippets in their hand-off. Concurrency cap stays 4 agents; at most two agents may touch the same app in a wave (apps/integrations is Codex's, `apps/bookings/video_*` and `frontend/src/components/classroom` are Antigravity's, `apps/teachers`/`apps/admin_api` vetting is Claude's).

## 5. Review checklist for Step 1 (Claude)

- **T3:** quarantine prefix and ownership (user A cannot commit B's key), magic-byte sniff (SVG/polyglot/renamed exe rejected), ETag pin and server-side copy, random final key, fails closed in production, private documents never exposed through a public URL, access audit row, `revet_after_vetted_change` wiring.
- **G1:** refresh token encrypted at rest and absent from admin/logs/payloads, `INTEGRATION_DATA_KEYS` (not payout keys), `state` nonce single-use/bound/expiring, plaintext `User.google_calendar_token` wiped, `invalid_grant` marks revoked once.
- **R1:** `AttendanceAudit.raw_payload` only, 90 days, exclusions (DISPUTED, open DisputeCase, unreleased escrow/refund, no-show inside the dispute window), idempotent, id-range chunks, distributed lock; verdict columns untouched.
- **V1-V3:** JWT fields and expiry, role mapping (tutor 1, student 0), `tpc` deterministic, `cloud_recording_option: 0`, secret never leaves the server, 32+ byte key enforced outside tests (the test run warns about an 18-byte key), IDOR (only the booking's two parties and staff), T-15 min window to scheduled end, status gate (confirmed/in_progress), permission + throttle + typed schema on the view, frontend cleans up the client on unmount, no token in logs or URLs, `ZOOM_VIDEO_SDK_*` in the production guard and `check_deploy.py`.

## 6. What Anesu must provide (nothing here blocks Step 1; each blocks a live check)

1. **Zoom Video SDK app** (key, secret, webhook secret) - unblocks V4 live verification and V5.
2. **Explicit go for V5** after the sandbox run.
3. **Resend domain DNS** (N3) remains outstanding; the second private R2 bucket and Google Cloud project/OAuth client were provisioned on 2026-10-05.
4. Still open from the plan (do not encode; provisional defaults stay): P1 payout go, D-3/D-4/D-10/D-12, PayPal sandbox credentials, training gate ON before launch.
5. ~~Confirm the Video SDK go~~ treated as given for V1-V4 (see §0.5); Anesu reverses it if wrong.

## 7. Rules every agent keeps (unchanged, restated)

Read `docs/README.md`, `HANDOFF_PHASE_11_12.md` §8, `QUALITY_GATES.md`; tests first; no symptom patches; log every failure as `ERR-xxx` in your own block (new blocks above: V1 360, V2 370, V3 380, V4 390, V5 400, T4b 410, T5a 420, T5b 430, T7a 440, T7b 450, T7c 460, T3b 470, P1a 480, P1b 490, P1c 500); mark `[x]` in `PROGRESS_AND_ROADMAP.md`; do not claim done without gate output; keep `docs/slices/<ID>.md` current so another agent can resume; write files with the editor tools (no heredocs/`Set-Content`); never `git add -A`; work in your own worktree; only `sharonremotedeveloper` pushes; tool/account checks per Rule 8 before any external call. Hand-offs state slice done, files touched, test counts, and confirm the roadmap and error log are updated.
