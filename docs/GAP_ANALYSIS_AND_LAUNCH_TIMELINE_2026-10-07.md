# Gap analysis and launch timeline

**Date:** 2026-10-07 · **Method:** read-only review of docs, `git` state and source in `Project-files/` (nothing executed except `git log/status/rev-list` and file reads; **no test, build or provider call was run for this report**, so test counts below are quoted from docs, not re-verified).
**Rule used:** where docs and code disagree, the code wins; disagreements are listed in section 9.

## 0. Headline

- The product is a **feature-rich, heavily tested, entirely mocked** platform. Almost everything that can be built without external accounts is built. What remains is (1) things only a human or third party can unlock (domain, hosting accounts, PayPal/PayFast live approval, Zoom app webhook, legal counsel, decisions D-3/D-4/D-7/D-10/D-11/D-12), (2) ~10 unbuilt admin/student/tutor screens, (3) production hosting + observability, (4) real-provider verification (never done once), (5) compliance completion, (6) UAT.
- **No external provider has ever been called** (PayPal, PayFast, Zoom, Resend, Google, R2 for product flows, Eskom): `HANDOFF_PHASE_11_12.md` section 7. Every payment, refund, attendance and e-mail behavior is verified only against fakes. This is the largest hidden risk, bigger than any missing page.
- **Timeline (from 2026-10-07):** minimum hosted invite-only soft launch **best 3 weeks / likely 5-6 weeks / worst 9 weeks**; complete production launch of the full scope **best 7 weeks / likely 10-12 weeks / worst 18 weeks**. Critical path is external approvals and decisions, not engineering.

## 1. What is DONE (evidence)

| Area | Evidence |
| :--- | :--- |
| Backend apps and domain model | 11 apps in `backend/apps/` (users, teachers, materials, bookings, payments, integrations, crm, srs, admin_api, common, notifications); `backend/config/urls.py` wires 13 URL roots. Docs claim backend 3217 passed (2026-10-05, `PHASE_11_12_TASK_ASSIGNMENTS.md` section 0.46); ~2,376 `test` functions counted by grep (parametrization makes the real count higher). Not re-run today. |
| Security phase 7 | 7.1-7.9 done (role escalation, webhook signature verification, fail-fast prod settings, throttling, blacklist/logout, IDOR matrix, upload hardening); `PHASE_7_SECURITY_CHANGES.md`. |
| Auth and honest frontend (Phase 8) | HttpOnly cookie sessions via Next BFF (`frontend/src/app/api/session/*`, `api/proxy/[...path]`, `proxy.ts`), password reset, e-mail verification, login by e-mail, mock fallbacks removed (production build refuses `NEXT_PUBLIC_USE_MOCKS`, `next.config.mjs`), Next 16 / React 19. |
| Booking core (Phase 9) | `transition_booking()` state machine, 10-min Redis hold + DB backstop, slot generator with DST fix (T2), cancel/reschedule/strike/credit-expiry policy (D-6), settlement paths, memo, reviews. |
| Payments in code (Phase 10) | Price catalog (`LessonPrice`), FX table, PayPal Orders create/capture, PayFast signed form + ITN, webhook events, grace bookings, refund claim/call/apply protocol (ADR-0001), double-entry ledger with DB immutability trigger, receipts with `INV-` numbers + PDF (10.8), credit packs/wallet. All on mocked HTTP. |
| Payouts (Package A, P1a-c, P2) | Payout batches with maker-checker, defused bank CSV, bank-change e-mail code, 72 h hold, ledger posting, tutor statement CSV, admin payout-runs screen (`PAYOUTS_GO_LIVE.md`). |
| Tutor lifecycle | Status machine (T1a), `bookable()` gate (T1b), profile at signup (T1c), availability (T2), uploads/quarantine (T3, T3b), vetting rubric (T4a) + admin vetting UI (T4b), application funnel backend+UI (T5a/T5b), training infra (T6) with `/teacher/training`. |
| Integrations in code | Resend `send_email` + `notify()` (N1a/N1b/N1c), Resend webhook receiver (svix), Google Calendar OAuth (G1) + busy hint (G2), Eskom provider-backed status, attendance-payload retention (R1), Zoom Video SDK token service + endpoint + `VideoSdkClassroom` (V1-V3) and attendance telemetry/webhook receiver (V4, 14 contract tests unchanged). |
| Frontend routes | 51 `page.tsx` under `frontend/src/app` (public 14 incl. `/legal/[policy]`, auth 5, student 14, teacher 12, admin 8). `/tutors` and `/tutors/[id]` are now wired to the live API (Task 15.1 done; CLAUDE.md still calls them hardcoded). Sitemap, robots, OG images present. |
| Legal / compliance first cut | `frontend/src/content/legal/policies.ts` (terms, privacy, refunds, cookies, child-safety), `components/legal/CookieBanner.tsx`, SAR export pipeline (commit `d324e1d`). |
| Ops first cut | `backend/Dockerfile` (multi-stage, non-root, gunicorn, collectstatic, healthcheck), `frontend/Dockerfile` (standalone, non-root), `docker-compose.prod.yml` (commit `bb19a7e`), `requirements.in` + `requirements.lock`, CI `.github/workflows/quality-gates.yml` (lint, backend, frontend, dependency-audit, `postgres-ledger`, `redis-races`) and `api-contract.yml`, Dependabot, `scripts/check_deploy.py`. CI green on `develop` as of 2026-10-05 (doc claim). |
| UI/UX | Palette, header, dialog a11y, contrast, 44 px targets (commits 5184f4c..b638b9d, 2026-10-06/07); `UI_UX_SIGNOFF.md`. |
| Live-failure repair (2026-10-07) | Backend half (Task A: materials catalog, slug detail, power-guard contract, booking time authority, attendance duration, FX, media) merged to `develop` (`0ee1c2d`, `b232e45`, `7699a68`). |

## 2. What is MISSING

### (a) Unbuilt product features / pages (46-view inventory vs real routes)

Inventory IDs from `COMPREHENSIVE_PAGE_INVENTORY_AND_SYSTEM_LOGIC.md` (10 PUB + 12 STU + 12 TEA + 12 ADM = 46) checked against `frontend/src/app`:

| Missing or partial | Notes |
| :--- | :--- |
| **ADM-07** Curriculum CMS / lesson authoring | no admin route; materials are managed in Django admin only (T3b adds PDF/audio commit API). |
| **ADM-08** Users, RBAC, impersonation, freeze | none; Django admin only; no audited impersonation. |
| **ADM-09** Eskom outage radar / broadcast | backend status endpoints exist; no admin screen. |
| **ADM-10** Pricing, FX spread, commission matrix | only `/admin/finance/fx-rates`; prices edited in Django admin (`LessonPrice`); no commission/bundle UI. |
| **ADM-11** Privacy / compliance vault, DSR queue | none (SAR export exists server side). |
| **ADM-12** Webhook telemetry and DLQ + replay | none. |
| **STU-12** Account, timezone, regional settings | only `/student/profile`; no `/student/settings` (notification prefs exist in a drawer). |
| **STU-08** Study room / material hub (saved, annotations) | `/student/vocabulary` only; no `/student/materials`. |
| **STU-11** Dispute lodging (student side) | review page exists; no student dispute form found. Unverified. |
| **TEA-06** Booking roster and attendance telemetry | `teacher/bookings/` contains only `[id]/memo`; no list page. |
| **TEA-12** Reputation, analytics, badges | none. |
| Admin refunds / manual credits / support inbox UI | refund API exists (`RUNBOOK_REFUNDS.md`); no UI; support inquiries are Django-admin only. |
| Subscriptions, group classes, social OAuth, standby matchmaking, whiteboard, AI, SARB reporting, multi-region DR | deferred by design (CLAUDE.md "Deferred to Phase 2"). |
| Cancel / reschedule screens | API and client ready (9.6); `student/schedule` exists, completeness of the cancel and reschedule UX not verified. |
| Wallet-pack `trial lesson` | D-1 sub-question still open. |
| Tutor-side: payout statement PDF/payslip (11.9), SARS statements beyond CSV | CSV only. |

### (b) Incomplete / stubbed backend

- **PayFast refunds are a manual stub** (`PAYFAST_REFUNDS_ENABLED=False`, `PAYFAST_REFUNDS_UNVERIFIED.md`).
- **`POST /admin/payouts/execute-batch/` is a permanent `503 payout_execution_disabled`** (`apps/admin_api/views.py:429`); real money movement is a manual bank-CSV process by design, but there is no gateway withdrawal ledger entry: **gap G2 / decision D-13** (account 1030 has no inflow).
- `apps/admin_api/payout_views.py:132` and `bookings/serializers.py:216` raise `NotImplementedError` (guard rails, not defects).
- 15 views still use `OpenApiTypes.OBJECT` `TODO(8.8+)` instead of serializers (`admin_api/views.py`, `bookings/views.py`, `crm`, `integrations`, `payments`, `srs`); Task 15.9 follow-up. Shrink-only baseline.
- **Legacy Zoom Meetings path still live** (`integrations/zoom.py`, `zoom_hosts.py`, `bookings/services/host_link.py`, `host_link_views.py`, `Booking.zoom_meeting_id/zoom_host_user_id/zoom_start_url`, `ZoomLauncherButton.tsx`, `hostLink.ts`); retired only by V5 (not approved).
- Notification slices: N2a-c (reminders/events), N3 (Resend webhook), N4 appear implemented on branches merged into `develop` (commits `c4d4808`, `d387653`), but the roadmap rows still say "remaining slices include N2a-c/N3/N4". Treat as built-but-unverified.
- 12.9 recording purge deliberately absent (D-8: no recording in MVP).
- Phase 14 backend items open: erasure/anonymisation pipeline that preserves ledger integrity (14.3), general audit log + retention jobs (14.4), parental consent controls (14.5), consent log model (14.2).
- Phase 13 items open: Sentry/structured logging (13.4, no `sentry` anywhere in `backend/requirements.in`, `config/` or `frontend/package.json`), deep health check (`config/urls.py` health is a static JSON `healthy` with no DB/Redis/Celery probe), Celery broker hardening and CSP (13.5), performance pass (13.8), backups/DR (13.7).
- Task 10.10 (payment suite on Postgres + sandbox E2E script) not done; 10.4/10.5/10.6 flagged `[~]` pending sandbox shapes.
- Data-protection register items: `TeacherStatusChange` retention, notification payload erasure.

### (c) Frontend gaps (mock / hardcoded / static data)

- The Phase-8 "no mock fallback" rule is enforced (`lib/http.ts`, `next.config.mjs`); remaining mocks live only in `lib/api.ts`, `lib/http.ts` behind `NEXT_PUBLIC_USE_MOCKS` (dev flag).
- Remaining static data: marketing stats and FAQs (`(public)/page.tsx`, `support/page.tsx`), `TIMEZONES`/`CEFR_LEVELS` lists, `SA_BANKS` (acceptable constants). `student/confirmed` builds .ics client side.
- `frontend/src/app/sitemap.ts` falls back to `http://localhost:3000` if `NEXT_PUBLIC_SITE_URL` is unset (must be set at build, or sitemap/OG point to localhost).
- Task B of the 2026-10-07 live-failure repair (frontend half: `docs/REPAIR_PLAN_LIVE_FAILURES_CODEX_ANTIGRAVITY.md`, branch `feature/antigravity-repair`) has **no product commits beyond the docs commit** (`bd88f92`); the plan itself says "no product code changed". Frontend truthfulness of F-01..F-08 (materials, history, power-guard error states, schedule labels, media errors) is therefore unconfirmed even though the backend half is merged.
- No end-to-end tests: `frontend/test/` has two files; Playwright (15.7) not installed (`package.json` has no `playwright`); only the Node test runner (Vitest blocked on this machine).
- No Content-Security-Policy (`next.config.mjs` states it is deliberately deferred until tested against Zoom SDK, PayPal and PayFast). i18n (ja/ko/de/fr) is nice-to-have and absent although the target students are Japan/Korea/Europe.
- Accessibility: manual pass done; axe/Lighthouse in CI (15.6) not done.

### (d) Payments: sandbox to live

1. **PayPal sandbox credentials are not in the environment** (blocked on Anesu); every PayPal path (orders, capture, webhooks, refunds, disputes) has never touched PayPal. Unknowns listed in `PHASE_10_2_PAYPAL_ORDERS_PLAN.md` / `RUNBOOK_REFUNDS.md`: idempotency retention, REFUNDED/REVERSED/dispute payload shapes, PENDING reasons.
2. PayFast sandbox exists in `.env.example` (public sandbox values) but ITN against a public URL needs a hosted staging endpoint (PayFast cannot call localhost).
3. Sandbox E2E script and Postgres payment suite (10.10).
4. **Live accounts (16.1):** PayPal Business and PayFast merchant under the client's **legal entity**, with bank account, business documents, KYC/KYB. Blocked on D-12 (entity, VAT, POPIA officer). PayFast also needs a live website with terms/refund/privacy pages and often a review of the site; PayPal live approval for a marketplace taking international card/PayPal payments can include risk review and, for payouts to third parties, extra scrutiny (note: Sharon pays tutors by bank CSV, not via PayPal Payouts, which avoids that review).
5. Open money decisions: prices (provisional USD 9.00 / EUR 8.50 / ZAR 162 / JPY 1350), pack expiry rule, trial lesson, FX source (admin table now), D-13 treasury/bank inflow, accountant on SARB/FX treatment and VAT (14.6).
6. Before live: flip `PAYFAST_SANDBOX`/`PAYPAL_MODE`, remove sandbox constants (guard already blocks sandbox values in production per `DECISIONS_D1_D12.md`), rehearse a real R1 live charge + refund.

### (e) Video Calling Architecture: Transition to Daily.co (Decision D-14)

On 2026-10-08, the project resolved Decision **D-14**, approving the transition from Zoom Video SDK to **Daily.co** (see `DAILY_CO_MIGRATION_PLAN.md`).

**Why the transition was approved:**
- **Raw Canvas Overhead:** Zoom Video SDK required raw HTML5 `<canvas>` rendering (`mediaStream.renderVideo(canvas)`) because enabling COOP/COEP headers breaks PayFast and PayPal checkout iframes. Daily.co uses native `<video>` elements with standard WebRTC.
- **Cross-Browser Stability:** Daily Prebuilt / standard WebRTC eliminates mobile Safari canvas dimension and audio context glitches.
- **Maintenance & Lifecycle:** Zoom enforces a quarterly minimum client version policy (locking out apps older than 9 months). Daily.co has standard semantic versioning without forced client obsolescence.
- **Dual Credentials:** Zoom Video SDK required separate credential pairs for join tokens vs REST session probes; Daily uses a single clean API key and webhook secret.

| Slice | Status | Description |
| :--- | :--- | :--- |
| D1 Daily settings & client | Upcoming | `DAILY_API_KEY`, room token issuer (`POST /v1/meeting-tokens`) |
| D2 Token endpoint & probe | Upcoming | Return `{ room_url, token }`; $T+10\text{m}$ presence probe against Daily REST API |
| D3 Frontend Daily Classroom | Upcoming | Drop `@daily-co/daily-js` / Prebuilt iframe into `ClassroomSplitLayout.tsx` |
| D4 Webhook ingestion | Upcoming | Ingest Daily `participant.joined` / `participant.left` into `AttendanceAudit` |
| D5 Clean up stale Zoom code | Upcoming | Retire `@zoom/videosdk`, Zoom S2S files, and legacy columns |

### (f) Security, compliance, legal

- **Counsel review of all legal text.** `policies.ts` is generated copy that names "Sharon Online (Pty) Ltd." before the entity exists (D-12) and is dated 2026-10-06; it needs lawyer review, the Information Officer, VAT status and POPIA/GDPR/APPI wording (cross-border video transfer, children/Kids specialty).
- Consent log, cookie consent persistence server side, DSR intake form and admin queue (14.2), erasure pipeline, audit log (14.3, 14.4), retention for webhook payloads and 7-year tax archive.
- `/security-review` of the full repo and a pen-test checklist for auth, payments, uploads, webhooks (16.3); CSP; WAF/rate limiting at the edge; secrets-hygiene closeout (Task 7.10 still `[~]`: inspect `.mcp.json`, `.claude/`, `.codex/`, `.agents/` and git history).
- 2FA/OTP: bank-change OTP exists; account 2FA for admin (16.5 "enable 2FA") and admin second-account requirement for maker-checker payouts.
- Tutor vetting operations: D-11 (who interviews, SA ID, background checks) and `TUTOR_TRAINING_GATE_ENABLED=True` with `backfill_training_completed` before launch (16.4 launch checklist), plus real training content from Sharon.

### (g) Infrastructure and hosting

State: images and a prod compose exist; **nothing is deployed anywhere and no hosting decision is final** (D-10 open).

| Item | State |
| :--- | :--- |
| Domain / DNS | **No domain owned or configured.** `sharonesl.com` used in config, not registered/verified; Cloudflare account has **no DNS zone** (`TOOL_ACCESS_AND_ACCOUNTS.md` row for Cloudflare). Blocks: Resend SPF/DKIM, TLS, Zoom webhook URL, PayFast ITN, cookies/CORS. |
| Backend host | Railway project id recorded (`RAILWAY_SETUP.md`) but **CLI login is the wrong account**; no service created, no `railway link`. Alternatives (Render/Fly) undecided. |
| Frontend host | Vercel `AUTHORIZED`, not verified; no `vercel.json`; the `frontend/Dockerfile` standalone image also allows container hosting. Next BFF needs a stable server runtime and `SESSION_SECRET`, `INTERNAL_API_URL`, `TRUSTED_PROXY_COUNT` (boot check, `lib/server/boot.ts`). |
| Postgres | Neon project `sweet-bonus-69458238` exists and CLI is confirmed; no migrated staging DB, no pooled-connection tuning, PITR/retention not set. |
| Redis | Upstash `AUTHORIZED`, unverified; locks and Celery need `rediss://` options and visibility timeout (13.5). |
| Celery | worker/beat services defined in `docker-compose.prod.yml` and `RAILWAY_SETUP.md`; no separate per-queue workers; exactly-one beat instance is a manual rule; Neon scale-to-zero vs two 60-s beat jobs unanalysed (13.8). |
| R2 | Public bucket `esl-platform-assets` and private bucket `esl-platform-private-vetting` exist; no custom domain `assets.sharonesl.com` (needs the DNS zone); versioning/lifecycle unset. |
| Secrets | `.env` only locally; no secret-store plan beyond host variables; prod compose uses `change_me_in_prod` defaults. |
| Monitoring | none: no Sentry, no structured logging, health is static, no uptime monitor, no alerting on the staff `alert_staff()` channel beyond e-mail. |
| Backups / DR | none documented (13.7); no restore drill. |
| Staging | none hosted ("Task 6.5" was a local docker test). |
| CI/CD | CI exists; **no deploy pipeline**, no required-status branch protection (Anesu's click), no migrations release command. |

### (h) Testing, QA, launch readiness

- Strong unit/integration base (docs: 3217 backend, 198-203 frontend tests); the Postgres/Redis-marked tests run only in CI.
- Missing: Playwright E2E, hosted-staging E2E with real sandboxes (16.2), k6/Locust smoke (13.8), axe/Lighthouse budgets, coverage thresholds (15.8), `check --deploy` in CI is present but real hosted verification isn't.
- UAT with beta tutors/students and SOW Milestone sign-off (16.4); admin handover video; post-launch runbook, on-call, restore drill (16.6); 30-day warranty clock starts at DNS cutover (SOW section 8).
- Full-suite flakiness history (ERR-193/197/199) suggests keeping a "two clean consecutive runs" rule.

### (i) Decisions and credentials blocked on Anesu

| Ref | Needed | Blocks |
| :--- | :--- | :--- |
| D-3 | payout cadence + rail confirmation (code assumes bi-weekly, bank CSV), R100 minimum, 72 h hold, **second admin account** | real payouts (P1 go) |
| D-4 | memo SLA penalty/gating (only 12 h reminder ships) | 11.10 |
| D-7 | credit bundle sizes/discounts, subscriptions yes/no | pricing UI |
| D-10 | stack/hosts and **domain** | all hosting |
| D-11 | tutor employment model and vetting process | go-live of tutors |
| D-12 | legal entity, VAT, POPIA Information Officer, accountant on SARB/FX; signed SOW | live gateways, legal pages |
| D-13 | how money gets from PayPal/PayFast into the bank, who records it | ledger inflow |
| D-1 residual | trial lesson; confirm provisional prices | catalog |
| D-6 residual | confirm 30-day expiry on packs, zero outage pay, breakage accounting | policy |
| D-9 | docs say approved 2026-10-05; Claude could not verify Anesu's approval, `HANDOFF` section 6 asks him to confirm; V5 explicitly not approved | V5 |
| 7.10 | secrets-hygiene inspection | security closeout |
| Accounts / credentials | PayPal sandbox then live; PayFast live merchant; Zoom webhook Secret Token + public URL; Resend sending domain; Railway re-login as `sharonremotedeveloper@gmail.com`; Vercel/Upstash verification; Cloudflare DNS zone; Sentry project; branch protection; second admin user; Google OAuth consent publishing (production verification for Calendar scope may take weeks) | each live check |
| Content from Sharon | training modules, vetting rubric content, legal sign-off, curriculum content, tutor onboarding | training gate, launch |

## 3. Timeline to a complete, fully hosted, production-launched product

### 3.1 Assumptions

1. Today is 2026-10-07; work days = Mon-Fri. Three agents run in parallel in worktrees (collaboration cap of 4) with Claude integrating; observed throughput in the last 5 days was roughly one slice per agent per day.
2. Anesu responds to blocking asks within 1-2 working days (most blocked items have been waiting 5+ days, so this is the main risk).
3. Domain is bought and DNS delegated to Cloudflare within week 1.
4. Provisional defaults (prices, thresholds) are accepted unless Anesu changes them.
5. Third-party approvals take: PayPal live 1-4 weeks, PayFast live 1-3 weeks (start together), Google OAuth sensitive-scope verification 1-6 weeks (avoidable at soft launch by staying in testing with named tutors, up to 100 users), legal review 2-4 weeks.
6. Tutor payouts stay a manual bank CSV run (no automation) at launch.
7. Estimates are agent working days (AD) for engineering and calendar days for external gating.

### 3.2 Workstreams

| # | Workstream | Owner | Effort | Gate |
| :--- | :--- | :--- | :--- | :--- |
| W1 | Domain, DNS, accounts re-verification (Railway/Vercel/Upstash/Neon/Cloudflare/Sentry), secrets store | Anesu then Claude | 2-3 days elapsed | Anesu |
| W2 | Hosted staging: deploy backend+celery+beat+frontend, migrate on Neon, fix prod compose/env gaps, Sentry + structured logs + deep health, CSP, branch protection, backups/restore runbook | Claude (ops), Codex (Celery/health) | 8-10 AD | W1 |
| W3 | Sandbox verification: PayPal create/capture/refund/webhook, PayFast ITN, Resend + domain, Zoom Video SDK webhook + two-party session, R2 private/public, Google OAuth, Eskom; fix drift found (expect real bugs) | Claude + Codex, Antigravity (Zoom) | 8-12 AD | W2 + credentials |
| W4 | Frontend truthfulness repair (live-failure Task B) + remaining screens: STU-12 settings, STU-08 study hub, STU-11 dispute form, TEA-06 roster, TEA-12 performance, cancel/reschedule UX, wallet/receipt polish | Antigravity + Codex | 10-14 AD | none (parallel) |
| W5 | Admin console: users/RBAC/impersonation/freeze (ADM-08), curriculum CMS (ADM-07), pricing/commission/bundles (ADM-10), outage radar (ADM-09), compliance vault + DLQ (ADM-11/12), refund and support UI | Codex (API) + Antigravity (UI) | 15-20 AD | D-7 for ADM-10 |
| W6 | Compliance engineering: erasure/anonymisation, consent log, audit log, retention jobs, DSR queue, CSP | Claude + Codex | 8-10 AD | counsel for wording |
| W7 | Payments hardening: 10.10 Postgres suite, D-13 treasury posting form, PayFast refund automation (or keep manual), VAT fields, receipts for packs | Claude | 6-8 AD | D-13, D-12 |
| W8 | QA: Playwright E2E across student/tutor/admin, axe/Lighthouse, k6 smoke, `/security-review` + fixes, flake hunt | all three | 10-12 AD | W2 |
| W9 | Live gateways: entity, KYC, PayPal Business + PayFast merchant, live key rotation, one real charge/refund | Anesu | 2-6 weeks elapsed | D-12, domain, live site with legal pages |
| W10 | Legal: counsel review of 5 policies, Information Officer, VAT, tutor agreement | Anesu + counsel | 2-4 weeks elapsed | D-11, D-12 |
| W11 | Pilot/UAT: recruit and vet beta tutors, training content, 2-week beta with real students on sandbox or small live payments, SOW sign-off | Anesu + Sharon | 2-3 weeks elapsed | W3, W4 |
| W12 | Cutover: DNS/SSL/HSTS, training gate ON, backfill, warranty clock, handover, monitoring/on-call | Claude + Anesu | 3-4 AD | all |

### 3.3 Critical path

`D-10/domain (W1)` -> `hosted staging (W2)` -> `credentials + sandbox verification (W3)` -> `UAT/beta (W11)` -> `live gateways approved (W9, started in parallel at week 1)` -> `cutover (W12)`.
For the full scope the longer chains are W9+W10 (entity, counsel, live gateway approval) running in parallel with W2/W3, then the admin console W5 (15-20 AD) which is the longest engineering stream but not gating soft launch.

### 3.4 Parallelism

- **Day 0 (this week):** Anesu: buy domain, point DNS to Cloudflare, re-login Railway, create PayPal sandbox app, answer D-10/D-12/D-3 minimum set, start the legal entity/accountant/counsel conversations, start PayPal Business and PayFast merchant applications. Claude: W2 prep (fix prod compose gaps below), integrate the open branches. Codex: W5 APIs, W6. Antigravity: W4.
- **Weeks 2-4:** W2 and W3 sequential on Claude; W4/W5 parallel on Codex/Antigravity; Anesu: sandbox clicking, Zoom webhook secret, Resend domain.
- **Weeks 4-8:** W6-W8, UAT recruiting; live gateway approvals land.
- Concurrency cap of 4 agents and the integrator bottleneck (Claude owns settings/urls/OpenAPI) limit speedup; assume 2.5x not 3x.

### 3.5 Totals

| Scenario | Soft launch (hosted, invite-only, limited tutors, one live gateway or sandbox-with-manual) | Full production launch (full scope above, both gateways live, legal signed, UAT done) |
| :--- | :--- | :--- |
| **Best** | **3 weeks** (about 2026-10-28) | **7 weeks** (about 2026-11-25) |
| **Likely** | **5-6 weeks** (about 2026-11-11 to 11-18) | **10-12 weeks** (about 2026-12-16 to 2027-01-06) |
| **Worst** | **9 weeks** (about 2026-12-09) | **18 weeks** (about 2027-02-10) |

What drives the spread: (best) Anesu unblocks domain/credentials in days, sandbox verification finds few defects, PayPal and PayFast approve within a week or two, counsel is quick; (worst) entity/D-12 incomplete, gateways reject or request documents twice, sandbox testing reveals shape mismatches in refund/dispute/Zoom no-show paths (the mocked suite has never met reality), Zoom C2 forces rework, Christmas shutdown of Japanese/European/South African counterparts in late December adds 2-3 weeks to anything not already approved.

### 3.6 Fastest path to a minimum hosted soft launch (target 3-6 weeks)

Scope cut: invite-only, 5-15 vetted tutors, tens of students, **USD/PayPal only (or PayPal + sandbox-free manual ZAR via PayFast later)**, tutors paid by manual bank-CSV runs, Google Calendar in testing mode (named tutors only), existing Django admin for users/pricing/curriculum/support, no new admin screens, legal pages shipped as counsel-reviewed minimal Terms/Privacy/Refund, training gate on with a short real module set.

1. Days 1-3: buy domain, DNS to Cloudflare, Railway/Vercel/Upstash/Neon login verification (Anesu), pick D-10, collect PayPal sandbox creds.
2. Days 3-10: Claude deploys staging (backend, worker, beat, frontend), sets Sentry, deep health, fixes env gaps, enables backups.
3. Days 8-15: sandbox verification of PayPal, Resend (domain SPF/DKIM), Zoom Video SDK webhook + a real two-person lesson, R2, Google; fix findings.
4. Days 10-18 in parallel: Antigravity finishes frontend truthfulness repair and STU-12/TEA-06; Codex hardens ledger inflow (D-13) and payouts runbook; counsel reviews minimal legal set.
5. Days 15-25: PayPal live approval (started day 1), switch to live with a single real charge and refund, invite beta, monitor.
6. Everything else (admin console W5, TEA-12, compliance engineering W6 beyond DSR basics, PayFast live, V5 cleanup) follows during the beta.

This path deliberately skips W5 and most of W6/W7, which is why it is 2-3x faster than the full scope; the price is that admin operations remain in Django admin and POPIA/GDPR erasure is a manual runbook until W6 lands.

## 4. Risks that would move the dates most

1. **Mocked-only verification**: first contact with PayPal/PayFast/Zoom/Resend will reveal defects; reserve 8-12 AD plus rework slack. Highest technical risk.
2. **Human latency on blocked items** (domain, D-12, PayPal sandbox credentials, Railway login mismatch have been open since 2026-10-02 to 2026-10-05).
3. **Legal entity and live-gateway KYC** (calendar time you cannot compress).
4. **Zoom no-show semantics** (C2) and Video SDK minutes/quotas under real concurrency.
5. **Integrator bottleneck** (single reviewer/merger, ERR block exhaustion, flaky tests).
6. **Branch sprawl**: `main` is 196 commits behind `develop` and the working checkout is on a side branch behind `develop`; promotion needs a full gate + Anesu's word.

## 5. Recommended next 10 actions (in order)

1. Anesu: buy the domain, delegate DNS to Cloudflare, record D-10.
2. Anesu: `railway login` as `sharonremotedeveloper@gmail.com`, verify Vercel/Upstash; add a Video SDK row to `TOOL_ACCESS_AND_ACCOUNTS.md` section 3.4.
3. Anesu: create PayPal sandbox REST app and put credentials in `backend/.env`; start PayPal Business and PayFast merchant applications; start the entity/accountant/counsel conversations (D-12).
4. Claude: switch to `develop` (the working checkout is on `feature/landing-audit-fixes`, 3 behind), run the full gate once to replace the quoted docs with fresh numbers.
5. Claude: fix `docker-compose.prod.yml` gaps (section 9 item 5) and write the staging deploy runbook.
6. Antigravity: complete the frontend half of the live-failure repair (F-01..F-08).
7. Codex: N2a-c/N3/N4 verification, ADM-08/ADM-10 APIs, deep health check, Celery hardening.
8. Anesu: answer D-3, D-7, D-11, D-13 and the residual D-1/D-6/D-9 confirmations.
9. Claude: staging sandbox verification plan (PayPal, Zoom, Resend, R2, Google) with a pass/fail table.
10. Anesu with Sharon: supply training modules and vetting rubric content; recruit 5-10 beta tutors.

## 6. Roadmap status vs reality (for hygiene)

`PROGRESS_AND_ROADMAP.md` section 5 still lists Phase 13 "NOT STARTED", 14 "NOT STARTED", 15 "NOT STARTED" while production Dockerfiles, CI, legal hub, cookie banner, SAR export, live tutor directory and SEO metadata are on `develop`. Tasks 11.2, 11.5, 12.6, 15.5 are unchecked in `PRODUCTION_READINESS_PLAN.md` though built. Recommend a single roadmap reconciliation pass.

## 7. Appendix: what "hosted" must contain on day one

Backend `config.settings.production` with `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `ZOOM_WEBHOOK_SECRET_TOKEN`/`ZOOM_VIDEO_SDK_*`, `CLOUDFLARE_R2_*` incl. private bucket, `PAYPAL_*`/`PAYFAST_*`, `RESEND_*`, `INTEGRATION_DATA_KEYS`, `PAYOUT_DATA_KEYS`; frontend `SESSION_SECRET`, `INTERNAL_API_URL`, `NEXT_PUBLIC_APP_URL` (https), `NEXT_PUBLIC_SITE_URL`, `TRUSTED_PROXY_COUNT`; `scripts/check_deploy.py` green; `migrate` as a release step (not on container start); one beat instance; workers consuming `celery,scheduler_beat,financial_escrow,notifications,critical_io`.

## 8. Evidence index

Docs read: root `CLAUDE.md`, `docs/README.md` (not opened beyond directory listing), `PROGRESS_AND_ROADMAP.md`, `PRODUCTION_READINESS_PLAN.md`, `PHASE_11_12_TASK_ASSIGNMENTS.md`, `HANDOFF_PHASE_11_12.md`, `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md`, `TOOL_ACCESS_AND_ACCOUNTS.md`, `DECISIONS_D1_D12.md`, `RAILWAY_SETUP.md`, `PAYOUTS_GO_LIVE.md` (first 60 lines), `REPAIR_PLAN_LIVE_FAILURES_CODEX_ANTIGRAVITY.md` (first 60 lines), `docs/slices/V4.md`, root `COMPREHENSIVE_PAGE_INVENTORY_AND_SYSTEM_LOGIC.md` (headings) and the SOW (milestones and warranty). Code inspected: `backend/config/urls.py`, `backend/config/settings/{production,guard}.py` (grep), `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.prod.yml`, `.github/workflows/quality-gates.yml`, `frontend/next.config.mjs`, `frontend/src/app/**/page.tsx`, `frontend/src/app/sitemap.ts`, `frontend/src/content/legal/policies.ts`. Not read: `PROJECT_CONTEXT.md`, `PROJECT_MASTER_CONTEXT.md` in full, individual models.py files, `docs/README.md` body; the claims about their content are inferred from other docs.

## 9. Doc-vs-code discrepancies found

1. **Branches:** CLAUDE.md says only `develop` and `main` exist. Actually 14 local branches (codex-repair, feature/*, fix/*, integration/layer-2a/b/c), most already merged into `develop`. The working checkout is on `feature/landing-audit-fixes` (1 ahead, 3 behind `origin/develop` = `7699a68`). `main` = `261077c`, 196 commits behind `develop`. The task assignments doc cites `develop` `35be981`/`cfd21b3`; CLAUDE.md cites `261077c`/`f4c0e0a`.
2. **Test counts:** CLAUDE.md "1840 passed" and "frontend 152"; later docs say 3217 backend and 198-203 frontend; the quoted figures are all stale relative to each other. Fresh run needed.
3. **Zoom authorization:** `ZOOM_VIDEO_SDK_MIGRATION_PLAN.md` section 6 still says "Do NOT implement Phase 12-V1 through V5 until explicitly authorized", yet V1-V4 are implemented on `develop` and the assignments doc treats Anesu's chat message as the go. CLAUDE.md and `HANDOFF` section 6 say Anesu's approval of D-9 is unverified. That plan file also has uncommitted edits in the working tree (new section 5 runbook).
4. **Zoom ops claims:** plan section 5 says the SDK key/secret are in "the local ignored `.env`"; the file is `Project-files/.env` (there is no `backend/.env`). The registry lists no Video SDK row.
5. **`docker-compose.prod.yml` is not launch-ready:** frontend service sets `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` (the browser no longer holds an API URL, Phase 8), does not set `SESSION_SECRET` or `TRUSTED_PROXY_COUNT` (required by the boot check in `lib/server/boot.ts` per Task 8.7), the web service omits `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and Zoom/PayPal/PayFast/R2 variables that the production guard requires, and database credentials default to `change_me_in_prod`. Inferred from reading the file and the guard; not executed.
6. **`ENVIRONMENT_AND_TESTING.md`** shows `SECRET_KEY=` while `config/settings/base.py:9` reads `DJANGO_SECRET_KEY`.
7. **Roadmap status:** see section 6; also `PROGRESS_AND_ROADMAP.md` tracker lists 30 of the 46 views and still says Django 5.1 / Next 14 in places (CLAUDE.md says Django 5.2 / Next 16).
8. **`/tutors` pages:** CLAUDE.md says they "still use hardcoded arrays (Task 15.1)"; roadmap and routes show 15.1 is done (live API).
9. **CLAUDE.md "44 routes" / "43 views"** vs 51 `page.tsx` files today.
10. **Health endpoint** `GET /api/health/` returns a static `healthy`; Task 13.4 describes a deep check, and Docker healthchecks and uptime monitors would report healthy with the DB down.
11. **Sitemap/OG** default to `http://localhost:3000` if `NEXT_PUBLIC_SITE_URL` is missing.
12. **Notification slices** reported as "remaining" in the Phase 12 row though commits show N2/N3/N4-style work merged (`c4d4808`, `d387653`).
13. **Repair plan** (2026-10-07) says no product code changed; the backend half is merged to `develop`, the frontend half is not.
