# Production Readiness Plan (Phases 7-16)

**Created:** 2026-10-02 · **Author:** Claude (lead architect agent) · **Source:** four-way audit (backend, frontend, spec-vs-roadmap, infra/ops).
**Status of the audit:** read-only code review; nothing was executed except `tsc --noEmit` (clean). Findings marked *(verify)* should be reproduced with a failing test before being fixed.

## 0. Why this plan exists

Phases 1-6 in `PROGRESS_AND_ROADMAP.md` delivered a UI-complete, test-green **skeleton**. They did not deliver a working money-and-lessons platform:

- Payment webhooks are unauthenticated; checkout is a stub; both gateway buttons in the UI are `setTimeout` simulations.
- Payout execution writes hardcoded totals to the ledger. Admin telemetry mixes in invented floor values.
- Every `lib/api.ts` call silently falls back to mock data on any error, so failures look like success.
- Anyone can register (or PATCH themselves) as `admin`.
- Registering as a tutor creates no `TeacherProfile`; there is no tutor application flow.
- No CI, no production container images, no logging/Sentry, nothing deployed.

"Phase 6 COMPLETED" should be read as "scaffolding hardened", not "launched".

**Conventions** (per `AI_AGENT_COLLABORATION_RULES.md`): every task gets a failing test first where feasible; log failures as `ERR-006+`; tick `[x]` here **and** in `PROGRESS_AND_ROADMAP.md` when verified (`pytest` + `npm run build`); no secrets in files; sandbox gateways only; run `TOOL_ACCESS_AND_ACCOUNTS.md` checks before touching any external tool.

**Sizes:** S ≤ 0.5 day · M ≈ 1-2 days · L ≈ 3-5 days · XL > 1 week. **Owner hints:** `ARCH` (Claude), `CODEX`, `AG` (Antigravity), `ANESU` (human decision / account action).

## Phase map and dependencies

| Phase | Theme | Depends on | Gate to exit |
| :--- | :--- | :--- | :--- |
| **7** | Security emergency + spec freeze | none | No known auth/webhook exploit; decisions D-1..D-12 recorded |
| **8** | Honest frontend + real auth | 7 | Mock fallbacks removed from prod builds; login/refresh/logout/reset work against real API |
| **9** | Booking core | 7 (D-5) | reserve → book → pay-pending → confirmed → complete runs through one validated state machine |
| **10** | Real payments | 7, 9 (D-1, D-6, D-7) | Sandbox PayPal + PayFast end-to-end with verified webhooks; credits buyable and spendable |
| **11** | Tutor lifecycle + real payouts | 8, 10 (D-2, D-3, D-4) | Applicant → vetted → live → paid, with per-tutor balances |
| **12** | Integrations + notifications | 9 | Zoom/Resend/GCal/Eskom real, fail loudly; reminders actually send |
| **13** | Platform ops | can start after 7 | CI green, prod images, deployed staging, observability |
| **14** | Compliance + legal | D-12 | Legal pages, consent, erasure/export, retention jobs |
| **15** | Missing screens, admin, SEO, quality | 8-11 | 46-view inventory closed; test pyramid in CI |
| **16** | UAT + launch | all | SOW Milestone 3 sign-off, live gateways, DNS cutover |

Phases 13 (infra) and 14 (legal) run in parallel with 8-12 once Phase 7 is done.

### Status and what is next (updated 2026-10-03)

| Phase | Status |
| :--- | :--- |
| 7 | Code done; **open for Anesu:** 7.10 secrets check, D-3, D-4, D-7..D-12 |
| 8 | Done (8.9 Next.js 16 upgrade landed 2026-10-03) |
| 9 | **Done** (9.1-9.10) |
| **10** | **Next.** Detailed sprint plan, blockers and exit gate: [`PHASE_10_EXECUTION_PLAN.md`](PHASE_10_EXECUTION_PLAN.md). About a third of the groundwork exists (verified webhooks, PayFast signed form, refund requests, credit lots). |
| 13 | **Start 13.3 (CI) alongside Phase 10**: nothing runs automatically yet and the full suite takes 15-50 min locally |
| 11, 12 | After 10; can run as two parallel streams |
| 14, 15, 16 | As before; D-12 / live-gateway approval / counsel have the longest human lead times, start them now |

---

## Phase 7 - Security emergency + spec freeze

**Goal:** close exploitable holes and get the human decisions that block code.

### 7A. Security (do first, each is small)
- [x] **Task 7.1 (S, ARCH)** Remove `role` from writable fields in `RegisterSerializer` and `UserSerializer` (`users/serializers.py`); registration accepts only `student` or `teacher`, admin created only via management command/Django admin. Make `email` required + unique. *Tests:* register with `role=admin` → 400 or coerced to student; `PATCH /auth/me/ {role:admin}` ignored.
- [x] **Task 7.2 (M, ARCH)** PayFast ITN verification: signature (MD5 with passphrase), source-IP allowlist, server-to-server `validate` postback, amount/currency match against `PaymentTransaction`/booking. Reject (400) and log on any failure. Never default `pf_payment_id` to a random uuid.
- [x] **Task 7.3 (M, ARCH)** PayPal webhook verification via `verify-webhook-signature` API + order/capture lookup; remove `amount = 9.0` default; amount/currency must match. Idempotent on capture id.
- [x] **Task 7.4 (S, ARCH)** Production settings fail-fast: `SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `ZOOM_WEBHOOK_SECRET_TOKEN` required when `DEBUG` is false; reject known dev key and localhost origins. Remove `SECRET_KEY` fallback in `ZoomClient.get_webhook_secret`. Default `DJANGO_SETTINGS_MODULE` in `wsgi/asgi/celery/manage` must not silently be `local` in a container (set explicitly in images).
- [x] **Task 7.5 (S, ARCH)** Flip `DEFAULT_PERMISSION_CLASSES` to `IsAuthenticated`; mark public endpoints `AllowAny` explicitly (teachers list/detail, materials, health, register/token). Make `IsTeacher/IsStudent/IsTeacherOrAdmin` not auto-pass for `is_staff` unless intended. Drop `SessionAuthentication` from the API.
- [x] **Task 7.6 (S, ARCH)** DRF throttling: `AnonRateThrottle`/`UserRateThrottle` defaults plus scoped throttles on login, register, password reset, presigned-URL, and webhooks.
- [x] **Task 7.7 (S, ARCH)** Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS` + migrate; add `POST /auth/logout/`; shorten access lifetime to 15 min.
- [x] **Task 7.8 (M, ARCH)** Authorization audit: write a permission-matrix test (role × endpoint) and IDOR tests for `bookings/<id>/*`, CRM dossier (teacher must have taught the student), admin routes. Fix what fails. Also: `TeacherDetailView` must hide unverified teachers; remove the hardcoded default TEFL URL fallback (`teachers/models.py:67`).
- [x] **Task 7.9 (S, ARCH)** Upload hardening in `PresignedUploadURLView`: content-type allowlist per prefix, max size (`content-length-range` condition), cap `expires_in`, trailing-slash prefix match.
- [~] **Task 7.10 (.gitignore done; .env.apikeys confirmed empty; still inspect .mcp.json, .claude/, .codex/, .agents/ and git history) (S, ANESU+ARCH)** Secrets hygiene: inspect untracked `.mcp.json`, `.claude/`, `.codex/`, `.agents/`, `.env.apikeys` for tokens before any `git add`; add to `.gitignore` as appropriate.

### 7B. Spec freeze (decisions - `ANESU` with Sharon; record answers in `PROJECT_CONTEXT.md`)
- [x] **D-1** (answered 2026-10-02: platform-set flat price) Pricing: one retail price per currency; tutor-set price or platform-set; trial lesson yes/no and price.
- [x] **D-2** (80/20, platform bears gateway fees) Tutor pay model: fixed (R75), 80/20, or tiered 25/20/15; who bears gateway fees.
- [ ] **D-3** Payout cadence (monthly per SOW vs bi-weekly) and rail (bank EFT/ACB CSV vs Wise API vs PayPal Payouts); maker-checker approval yes/no.
- [ ] **D-4** Memo SLA: deadline, whether it gates payment, penalty, who funds the apology credit.
- [x] **D-5** (tutor T+10, student T+10, 5 min grace) No-show thresholds (tutor T+5 vs T+10), late-warning and disconnect-grace behaviour.
- [x] **D-6** (decided 2026-10-03, see `CANCELLATION_AND_REFUNDS.md`; 30-day expiry on purchased packs, zero outage pay and breakage accounting still to confirm) Refund + cancellation policy (>2h free? late-cancel tutor compensation? reschedule rules; gateway refund vs wallet credit; credit expiry period).
- [ ] **D-7** Credit bundles: sizes/discounts, subscriptions in MVP or not.
- [ ] **D-8** Recording policy (record or not, retention 7 days?, consent flow).
- [ ] **D-9** Zoom licensing model (per-tutor hosts / licence count / alternative hosts).
- [x] **D-13** Auth provider: **Django + simplejwt stays** (decided by Anesu 2026-10-02; Clerk and Neon Auth considered and declined for now). Keeps identity data in our own Postgres (simpler POPIA/GDPR/APPI). Phase 8 and Tasks 7.7, 8.4-8.6 stand as written. Hedge: keep all token verification behind one DRF authentication class so a provider swap later is localised. Because we own auth, Task 7.8 permission-matrix/IDOR tests and Task 13.3 CI are mandatory, not optional; add a scheduled `flushexpiredtokens` Celery beat job and an admin runbook for lockout / lost-2FA / email-change support requests.
- [ ] **D-10** Stack choices: backend host (Railway vs Render), frontend host (Vercel vs Cloudflare Pages), domain (`sharonesl.com` vs `sharon-esl.com`), whether Neon Auth/Functions/Storage are used at all (current answer: no, Django JWT + R2).
- [ ] **D-11** Tutor employment model and vetting process (who interviews, background checks, SA ID verification).
- [ ] **D-12** Legal entity, VAT status, POPIA Information Officer, accountant's view on SARB/FX; signed SOW with engineering fee filled in.
- [ ] **Task 7.11 (S, ARCH)** Docs hygiene once D-1..D-8 answered: reconcile `PROJECT_CONTEXT.md` vs `PROJECT_MASTER_CONTEXT.md`, fix stale `MASTER_MODULE_ROADMAP_AND_ARCHITECTURE.md`, drop `group` class type from schema docs or flag deferred.

---

## Phase 8 - Honest frontend + real auth

**Goal:** the UI tells the truth about the backend. Depends on 7.1, 7.7.

- [x] **Task 8.1 (M, ARCH)** Single `request()` client in `lib/api.ts`: attaches token, parses DRF errors into typed `ApiError`, on 401 refreshes once via `/auth/token/refresh/` (queue concurrent calls), redirects to `/login` on failure. Replace the duplicated `API_BASE` in `AuthContext`.
- [x] **Task 8.2 (L, CODEX)** Remove silent mock fallbacks from every `api.*`, `studentApi.*`, `teacherCrmApi.*` call; fixtures only behind `NEXT_PUBLIC_USE_MOCKS=true` (build-time error if set with `NODE_ENV=production`). Add real loading/empty/error states, `error.tsx`, `loading.tsx`, `not-found.tsx`, and a toast system.
- [x] **Task 8.3 (M, ARCH)** `AuthContext`: delete `MOCK_USERS`, demo-profile buttons, fake sessions on network error (behind the mock flag only). Expired/invalid session → logged out, not cached profile.
- [x] **Task 8.4 (M, ARCH)** Move tokens to HttpOnly+Secure+SameSite cookies via Next route handlers (`/api/session/*`); `middleware.ts` verifies the JWT (signature or via a lightweight `/auth/me/` check) and role claim instead of trusting `sharon_user_role`.
- [x] **Task 8.5 (M, ARCH)** *(done 2026-10-02, see `PHASE_8_ACCOUNT_RECOVERY.md`)* Backend: password reset (request + confirm), email verification (Resend), change password. Frontend: `/reset-password`, `/verify-email`, real `/forgot-password`.
- [x] **Task 8.6 (S, CODEX)** *(done 2026-10-02: login by username or e-mail; `password_confirm` field error mapped)* Login by email (or support both) to match Figma/spec; map DRF field errors into forms (e.g. `password_confirm`).
- [x] **Task 8.9 (M, ARCH)** *(done 2026-10-03: Next 16.3.8, React 19.3, ESLint 9 flat config + `eslint-config-next` 16 (dev dependency), `middleware.ts` -> `proxy.ts`, async route `params`, `instrumentationHook` flag removed; `npm audit --omit=dev` = 0 vulnerabilities and is now a blocking CI step)* **Next.js security upgrade.** `npm audit` still lists Next 14.2.35 advisories (DoS in Server Components/Image Optimizer, cache-poisoning, SSRF in rewrites/WebSocket upgrades...) whose fixes exist only in Next 15/16 (React 19, breaking). The 14.2.13 -> 14.2.35 patch bump (2026-10-02) already removed the middleware auth-bypass, middleware SSRF and Windows RCE advisories. Plan the major upgrade before launch; until then keep the image optimizer on a strict `remotePatterns` list and put WAF/request-size limits in front.
- [x] **Task 8.7 (S, CODEX)** *(done 2026-10-02)* Frontend env: `frontend/.env.example` (required vs optional, PayPal/PayFast/Zoom/Sentry placeholders marked not-wired); `src/instrumentation.ts` -> `lib/server/{boot,config}.ts` makes `next start` exit 1 when `SESSION_SECRET`, the Django upstream URL, `NEXT_PUBLIC_APP_URL` (https) or `TRUSTED_PROXY_COUNT` are missing/invalid. (The browser no longer holds an API URL: it talks to `/api/proxy`.)
- [x] **Task 8.8 (S, ARCH)** *(done 2026-10-02, see `PHASE_8_ACCOUNT_RECOVERY.md` §3b)* `/auth/me/` now returns `credits` (students), `avatar_url` + `is_verified` (tutors), `email_verified`; wallet = `{total_credits, ledger[], bundles[]}` (mock aligned; redemptions join the ledger in Task 10.6); `drf-spectacular` adopted (admin-only `/api/schema/`, committed `docs/api/openapi.yaml` with a drift-guard test, zero schema warnings); TS types generated with `npm run gen:api` -> `frontend/src/types/api.generated.ts` (wallet page uses them). Remaining plain-`APIView`s are typed as generic objects (TODO markers) - Task 15.9 replaces them with real serializers.

## Phase 9 - Booking core

**Goal:** one validated, race-safe path from slot to completed lesson. Depends on 7.x; needs D-5, D-6.

- [x] **Task 9.1 (L, ARCH)** *(done 2026-10-02, see `BOOKING_STATE_MACHINE.md`)* `transition_booking(booking, to_status, *, actor, reason)` in `bookings/services/`: allowed-transition map, `select_for_update`, emits audit row, idempotent side effects. Route all ~15 direct status writes through it (`SubmitMemoView`, `ReportOutageView`, dispute resolve, Celery tasks, webhook handler). *Tests:* illegal transitions raise; memo on cancelled/pending booking rejected; dispute can't be re-resolved.
- [x] **Task 9.2 (M, ARCH)** Make reserve and create one coherent step: `POST /bookings/reserve/` takes the Redis lock **and** creates a `pending_payment` booking, returns `booking_id` (UUID) + `lock_expires_at`. Validate: slot inside availability, 25-min alignment, future, teacher active+verified, lock owned by caller, no overlap with the student's own bookings, no duplicate pending. Handle missing teacher with 404, not 500. Frontend timer driven by `lock_expires_at`.
- [x] **Task 9.3 (S, ARCH)** *(done 2026-10-02: busy = every status except pending/cancelled + live holds from the DB, overlap-based, no duplicate slots; `?days=`/`?tz=` validated with 400; unverified tutors have no public slots)* Slot generator: treat all non-cancelled terminal-or-active statuses as busy (memo-pending, forfeited, disputed, pending_payment holds); validate `days`/`tz` params (400, not 500).
- [x] **Task 9.4 (M, ARCH)** *(done 2026-10-02, see `BOOKING_HOLDS.md`)* Purge task: do not cancel a booking with an in-flight `PaymentTransaction` (INITIALIZED/PENDING); extend hold or wait for webhook outcome. Late payment on a purged-but-free slot re-confirms safely.
- [x] **Task 9.5 (M, ARCH)** *(done 2026-10-02, see `BOOKING_LIST.md`: status/when/from/to/ordering/page_size filters, validated, scoped; tutor dashboard uses them)* `GET /bookings/` with status/date filters (my lessons, upcoming) + student/teacher scoping; ties to `/student/schedule` and teacher roster.
- [x] **Task 9.6 (M, ARCH)** *(done 2026-10-03, see `CANCELLATION_AND_REFUNDS.md`; cancel / reschedule screens come with the Phase 15 student and tutor pages, the API and client are ready)* Cancellation + reschedule engine per D-6: student cancel (>2h free / <2h forfeit), teacher cancel (refund + bonus credit + strike), reschedule rules; endpoints + UI; refunds routed through Phase 10 refund service.
- [x] **Task 9.7 (S, ARCH)** *(done 2026-10-02, see `SETTLEMENT_PATHS.md`; open policy questions for Anesu listed there)* `ReportOutageView`: require booking in a valid window, actor checks, idempotent (one credit per booking); fix escrow so `INTERRUPTED_POWER`/`STUDENT_NO_SHOW` reach the correct settlement path (`payments/tasks.py:41-62`).
- [x] **Task 9.8 (M, ARCH)** *(done 2026-10-02, see `ZOOM_ATTENDANCE.md`; registrant links need a Zoom plan decision, sandbox check in Phase 11)* Zoom attendance mapping: map participants by `zoom_user_id`/registrant to teacher vs student (no "default guest = student"); idempotent join events; use Zoom `end_time`; handle `meeting.started`. Teacher uses host link, not guessed email.
- [x] **Task 9.9 (S, ARCH)** *(done 2026-10-02: `LessonMemoInputSerializer`, lesson tutor only, finished lessons only, flashcards atomic and non-destructive, `grammar_notes` field added)* Memo endpoint: input serializer (validate vocabulary words), only the booking's teacher, only valid states; stop swallowing flashcard-creation errors (`except Exception: pass`).
- [x] **Task 9.10 (S, ARCH)** *(done 2026-10-02, see `LESSON_REVIEWS.md`)* Merge the duplicate review endpoints (`bookings/<id>/review` vs `student/bookings/<id>/review`) into one: completed bookings only, one review per booking, use `Avg`, keep `written_feedback` out of student/teacher-facing serializers per the asymmetric-privacy invariant.

## Phase 10 - Real payments

**Goal:** sandbox money flows end to end, correctly. Depends on 7.2, 7.3, 9.1, 9.2; needs D-1, D-6, D-7. *Sandbox only; read `TOOL_ACCESS_AND_ACCOUNTS.md` first.*

- [~] **Task 10.1 (M, ARCH)** *(Codex batch 2: `CreditPack` catalog with USD/ZAR/EUR/JPY prices + `GET /payments/credit-packs/`. Frontend done in Slice C (`feature/10-1c-frontend-prices`): `lib/prices.ts` formats decimal strings with Intl and no float math, every price label/pack/checkout amount comes from `/payments/lesson-prices/`, `/payments/credit-packs/` and the `checkout/init` response, no price literals left in `frontend/src` outside tests (the dev-only mock fixtures for admin disputes keep sample amounts). Remaining: the lesson price catalog (D-1 flat price), remove `ZAR_PER_USD` / 18.75 from live paths; JPY has no decimals)* Price catalog: `Price`/`CreditBundleProduct` models per currency (USD/EUR/JPY/ZAR) as the single source of truth; `GET /payments/credits/bundles/`; remove hardcoded 18.0/18.75 FX and `float()` money (use `Decimal`). Frontend `lib/currency.ts` reads from the API.
- [ ] **Task 10.2 (L, ARCH)** *(sprint 10-B; PayFast signed form and the 9.4 hold guards already exist - add the PayPal Order create/capture)* `CheckoutInitializeView`: validate gateway, booking state/hold/ownership; create `PaymentTransaction(INITIALIZED)`; PayPal: create Order via Orders v2; PayFast: build signed form (merchant id/key from env, `notify/return/cancel` URLs). Env settings for all gateway keys; no sandbox constants in code.
- [ ] **Task 10.3 (L, CODEX)** Frontend checkout: real `@paypal/react-paypal-js` buttons (create/capture via backend), PayFast signed form redirect, return/cancel pages, processing screen that polls booking status until the webhook confirms. Delete `confirmPayment`/`redeemCredit` fakes.
- [~] **Task 10.4 (M, ARCH)** *(Codex batch 3: provider-aware reconciliation, fee snapshot to 5030, durable anomalies. Remaining: verify/finish REFUNDED, DENIED, chargeback/dispute events and PayFast CANCELLED -> FAILED)* Webhook handler: store/transition by gateway reference, record gateway fees (acct 5030), handle `FAILED`, `DENIED`, `REFUNDED`, chargeback/dispute events, unknown `booking_id` → quarantine (not 500); real `reconcile_pending_transactions_task` that queries gateway status.
- [~] **Task 10.5 (M, ARCH)** *(Codex batch 3: FX rate + source on every transaction and ledger row, journals balance per currency and in ZAR, USD and ZAR supported. Remaining: EUR / JPY, blocked on an approved FX source)* Multi-currency ledger correctness: `PaymentTransaction.currency/amount` flow into `ledger_service` with an explicit FX snapshot (rate + source) on every entry; fix escrow release treating non-USD as USD (`payments/tasks.py:77`); test EUR/JPY/ZAR round-trips balance to zero.
- [~] **Task 10.6 (M, ARCH)** *(done in code by Codex batch 2 + 9.6: pack purchase checkout, row-locked soonest-expiry redemption, immutable wallet history, credit-funded refund restores the lot. Remaining: sandbox end-to-end and the pack-expiry decision)* Credit purchase + redemption: buy a bundle via checkout; `POST /bookings/<id>/redeem-credit/` decrements a wallet balance atomically; credit-funded bookings get correct escrow/commission accounting (per D-1/D-2). Wallet ledger endpoint (`{total_credits, ledger[]}`), `/student/wallet` top-up flow.
- [ ] **Task 10.7 (M, ARCH)** *(sprint 10-C; `RefundRequest` + 2050 ledger + `RefundGateway` plug-in exist from 9.6 - this task is the real PayPal / PayFast backends replacing `ManualSandboxRefundGateway`)* Refund service: gateway refund (PayPal/PayFast) vs wallet credit per D-6; sets `PaymentTransaction.REFUNDED`; used by cancellation, no-show, outage, dispute paths; balanced ledger entries.
- [ ] **Task 10.8 (S, ARCH)** Invoices/receipts: `Receipt` model + PDF, shown in student wallet; VAT fields stubbed per D-12.
- [x] **Task 10.9 (S, ARCH)** *(Codex batch 3, migration `0011`; its Postgres test runs in CI for the first time)* DB-level ledger immutability backstop (Postgres trigger rejecting UPDATE/DELETE on `LedgerEntry`) in addition to the Python guards.
- [ ] **Task 10.10 (M, ARCH)** Payment test suite: signature failure paths, replay, amount mismatch, late payment, multi-currency, refund, concurrency on Postgres (not SQLite).

## Phase 11 - Tutor lifecycle + real payouts

**Goal:** applicant → vetted → live → paid. Depends on 8.x, 10.x; needs D-2, D-3, D-4, D-11.

- [ ] **Task 11.1 (M, ARCH)** Auto-create `TeacherProfile` (status `applied`) on tutor registration; teacher self-profile endpoints (`GET/PATCH /teachers/me/`: bio, headline, price per D-1, specialties, accent, timezone).
- [ ] **Task 11.2 (M, CODEX)** Tutor application funnel `/teacher/apply` (Figma `ApplyScreen`): SA ID, TEFL upload, video/audio, power-backup declaration, speed test; progress saved server-side.
- [ ] **Task 11.3 (M, ARCH)** Upload-commit step: after presigned upload, `POST /teachers/me/assets/commit/` verifies the object exists (HEAD), re-validates type/size, then sets `avatar_url`/`intro_audio_url`/`tefl_certificate_url`. Same for admin material PDFs/audio.
- [ ] **Task 11.4 (M, ARCH)** Vetting workflow: rubric scoring, "request re-recording", stored `rejection_reason`, notification email to tutor, audit trail, suspend/reactivate; tutors can't take bookings until verified **and** training gate passed.
- [ ] **Task 11.5 (L, CODEX)** Teacher Training Hub (SOW 2.4 deliverable): modules, completion tracking, gate before slots open.
- [ ] **Task 11.6 (M, ARCH)** Availability CRUD: update/delete, validate `end > start`, `day_of_week` 0-6, no overlaps, time-off/vacation, minimum notice, booking horizon setting.
- [x] **Task 11.7 (L, ARCH)** Per-tutor payable balance derived from ledger acct 2020; `GET /payments/wallet/tutor/`; tutor bank details model encrypted with a versioned keyring; masked `payout-settings` endpoints with current-password reauthentication. OTP remains separate hardening under Task 15.3. *(Batch 6)*
- [ ] **Task 11.8 (L, ARCH)** Real payout batch: build from cleared balances per tutor (per-line records), idempotent execution, `EXPORTED → PROCESSED` states, EFT/ACB CSV export (or API per D-3), maker-checker if D-3 says so; remove hardcoded fake banks/totals/`5520.0`.
- [ ] **Task 11.9 (M, ARCH)** Tutor payslips + SARS-friendly statements (CSV/PDF) and admin audit export.
- [ ] **Task 11.10 (S, ARCH)** Memo SLA behaviour per D-4: penalty/forfeiture/payment gating implemented consistently in tasks and ledger.
- [ ] **Task 11.11 (M, CODEX)** Tutor wallet, payout settings, and dashboard wallet summaries use real APIs as of Batch 6; teacher profile and remaining dashboard/availability surfaces still need full real-data completion.

## Phase 12 - Integrations + notifications

**Goal:** every external integration real, observable, and failing loudly. Depends on 9.x; needs D-8, D-9. *Check `TOOL_ACCESS_AND_ACCOUNTS.md` and verify each account before use.*

- [ ] **Task 12.1 (M, ARCH)** Zoom client: no fake meetings when unconfigured in production (raise); explicit error handling/429 backoff; cache the S2S access token; fix `create_meeting` returning `None`; implement D-9 host strategy (per-tutor users or alternative hosts) so concurrent lessons don't collide.
- [ ] **Task 12.2 (M, ARCH)** Notification system: `Notification` model (in-app) + email dispatch; real T-24h/T-1h/T-10m reminders, teacher late-alert, memo SLA warning, apology credit email, tutor booking notification, Eskom shield alert. Resend failures retried with backoff and surfaced; HTML-escape names.
- [ ] **Task 12.3 (M, ARCH)** Resend: domain verification (SPF/DKIM) once D-10 domain is chosen; delivery webhook; production refuses `re_dev` mock key.
- [ ] **Task 12.4 (L, ARCH)** Google Calendar: OAuth connect/callback endpoints, encrypted refresh-token storage, token refresh, cancel/reschedule event updates, real freebusy in `reconcile_teacher_gcal_task`, slot generator honours busy times. Remove token exposure from `UserAdmin`.
- [ ] **Task 12.5 (M, ARCH)** EskomSePush client, quota-aware durable cache, tutor area mapping, real four-hour warning logic, status endpoint, and tutor-only backup PATCH are complete in Batch 7. Remaining: apply provider outage windows to unreserved public-search slot projection after product approval of the booking policy.
- [ ] **Task 12.6 (M, CODEX)** Frontend Zoom join: gate by `LessonCountDownClock` window, use backend-provided join/start URLs only, remove `window.confirm` hack and simulated latency; decide Meeting SDK embed vs deep link.
- [ ] **Task 12.7 (M, CODEX)** In-app notification centre + polling (SSE/WebSocket later), notification preferences.
- [x] **Task 12.8 (S, ARCH)** Support inquiries: durable `POST /auth/inquiries/`, admin inbox, throttling, and retryable support-team notification; `/support` now reaches a real persisted workflow. *(Batch 5)*
- [ ] **Task 12.9 (M, ARCH)** 7-day recording purge and 90-day telemetry purge Celery jobs (per D-8 and compliance).

## Phase 13 - Platform ops (parallel track)

**Goal:** reproducible builds, safe deploys, observability. Can start after Task 7.4.

- [ ] **Task 13.1 (M, ARCH)** Production images: multi-stage backend Dockerfile (gunicorn, non-root, `collectstatic`, healthcheck, no venv/sqlite via `.dockerignore`); frontend `next build` + `output: 'standalone'`, non-root. Keep a separate dev compose; stop seeding in prod.
- [ ] **Task 13.2 (M, ARCH)** Dependency hygiene: `requirements.in` + lockfile (pip-tools/uv), split runtime vs test deps, add missing `python-dateutil`, enable `django-filter` properly (or remove), `pip-audit`/Dependabot.
- [x] **Task 13.3 (M, ARCH)** *(done 2026-10-03: Codex batch 8 base + `scripts/check_deploy.py` (production `check --deploy`), blocking `pip-audit`, informational `npm audit` until 8.9, fresh-PostgreSQL `migrate`, actions on v7, least-privilege permissions, Dependabot weekly. First real run found two real bugs: the Redis lock owner check, ERR-030, and Django 5.1's 8 advisories, ERR-031. Branch protection is Anesu's click in GitHub)* GitHub Actions: backend (Postgres + Redis services, `pytest`, `makemigrations --check`, `manage.py check --deploy`), frontend (ESLint, `tsc`, tests, `next build`), `pip-audit`/`npm audit`. Required checks on `develop`/`main`.
- [ ] **Task 13.4 (M, ARCH)** Logging + monitoring: structured `LOGGING`, Sentry (backend, Celery, frontend), custom DRF exception handler, deep `/api/health/` (DB, Redis, Celery) and readiness vs liveness, `SECURE_REDIRECT_EXEMPT` for health.
- [ ] **Task 13.5 (M, ARCH)** Settings completion: `CSRF_TRUSTED_ORIGINS`, `SECURE_REFERRER_POLICY`, CSP/security headers in `next.config`, defer HSTS preload until TLS verified, `STORAGES` cleanup, guard requiring R2 creds in production, Celery broker options (`rediss` ssl, `acks_late`, visibility timeout, retry/backoff, queue-specific workers, single beat instance, durable schedule).
- [ ] **Task 13.6 (L, ANESU+ARCH)** Hosted staging: verify accounts (Railway re-login as the registry account, Neon, Upstash, Vercel, Cloudflare) and log in `TOOL_ACCESS_AND_ACCOUNTS.md` §4; Neon branch for migration tests; release command for `migrate`; separate Celery worker services per queue; pooled-connection tuning (`conn_max_age` with PgBouncer).
- [ ] **Task 13.7 (S, ARCH)** Backups/DR: Neon PITR + retention, R2 versioning/lifecycle, restore runbook, tested once.
- [ ] **Task 13.8 (M, ARCH)** Performance pass: `select_related/prefetch_related` and indexes on hot paths, cache public list endpoints, pagination for all `APIView` lists, review beat load (two 60-second jobs) against Neon scale-to-zero, k6/Locust smoke.

## Phase 14 - Compliance + legal (parallel track)

**Goal:** POPIA/GDPR/APPI-defensible launch. Needs D-8, D-11, D-12; legal review is a human task.

- [ ] **Task 14.1 (M, ANESU)** Legal copy: Terms, Privacy, Refund/Cancellation, Child-safety, cookie policy (reviewed by counsel); appoint Information Officer.
- [ ] **Task 14.2 (M, CODEX)** `/legal/[policy]` hub + Data Subject Request form; footer links; consent/cookie banner with a consent log model (cookie, marketing, cross-border video).
- [ ] **Task 14.3 (L, ARCH)** Data-subject rights: account export (SAR) and erasure/anonymisation pipeline that preserves ledger integrity (anonymise PII, keep immutable financial rows).
- [ ] **Task 14.4 (M, ARCH)** General audit log (admin actions, PII access, impersonation) and retention jobs (raw webhook payloads, telemetry, tax archive 7 years).
- [ ] **Task 14.5 (S, ARCH)** Parental-consent controls for the Kids specialty if retained at launch.
- [ ] **Task 14.6 (S, ANESU)** Accountant sign-off on SARB/FX treatment and VAT; correct the "bypassed" claim in `PROJECT_MASTER_CONTEXT.md`.

## Phase 15 - Missing screens, admin, SEO, quality

**Goal:** close the 46-view inventory and put the test pyramid in CI. Depends on 8-11.

- [ ] **Task 15.1 (M, CODEX)** Wire `/tutors` and `/tutors/[id]` to the API: server components, server-side filter/search/pagination (`django-filter`), proper slug/id routing, 404 for unknown ids. Align serializer ↔ type shapes (`slug`, accent, video, rating, power backup, next slot).
- [ ] **Task 15.2 (L, CODEX)** Student screens: `/student/settings`, `/student/schedule` (calendar), `/student/favorites` + slot alerts, top-up, `/student/materials` (saved + annotations), student onboarding, email verify.
- [ ] **Task 15.3 (L, CODEX)** Teacher screens: `/teacher/bookings` roster, `/teacher/performance` (KPIs, badges), 2FA/bank-change OTP.
- [ ] **Task 15.4 (L, CODEX+ARCH)** Admin: Users/RBAC (+audited impersonation, freeze), Bookings, Materials/Curriculum editor (draft→review→publish, PDF generation), Pricing config (commission tiers, FX buffer, bundles), Outages/Eskom broadcast, Webhook DLQ + replay, admin manual credits/refunds. Remove all hardcoded telemetry floors; fix `EscrowLedgerView` to use transaction amounts and `end_time + 24h`.
- [ ] **Task 15.5 (M, CODEX)** SEO: `generateMetadata` per page, OG/Twitter cards, `sitemap.ts`, `robots.ts` (disallow app areas), JSON-LD, canonical URLs, `noindex` on `/student|teacher|admin`, server-render public listings, favicon/OG image.
- [ ] **Task 15.6 (M, CODEX)** Accessibility pass: axe in CI, Modal focus trap, labelled icon buttons, contrast, skip links, keyboard support in `SlotGrid`, reduced motion; Lighthouse budgets (mobile > 90).
- [ ] **Task 15.7 (L, CODEX)** Non-interactive zero-warning ESLint and the existing 90-test frontend suite are required in CI as of Batch 8. Remaining: Prettier, Testing Library/MSW expansion, and Playwright end-to-end flows.
- [ ] **Task 15.8 (M, ARCH)** Django checks, migration drift, 774-test regression, real PostgreSQL ledger-trigger tests, and real Redis race tests are required CI jobs as of Batch 8. Remaining: `check --deploy`, coverage thresholds/factories, and broader users/teachers/materials gaps.
- [x] **Task 15.9 (M, ARCH)** `drf-spectacular` OpenAPI schema + generated TS client; CI diff check so contracts can't drift. *(Batch 5)*
- [ ] **Task 15.10 (S, ARCH)** Student profile persistence and country/timezone validation are complete in Batch 5; route-order and `LiveSessionsView` ordering/filter remain.
- [ ] **Task 15.11 (M, CODEX)** Timezone/currency correctness in UI: default to browser/user timezone (not `Asia/Tokyo`), date-fns-tz everywhere, backend-driven price display.
- [ ] **Task 15.12 (nice-to-have)** i18n (ja/ko/de/fr), real-time presence via WebSockets/SSE, push/LINE notifications, SM-2 spaced repetition, PWA, Storybook.

## Phase 16 - UAT + launch

- [ ] **Task 16.1 (M, ANESU)** Obtain live PayPal Business + PayFast merchant accounts under the client's legal entity; verify; log in registry. Live keys never in files.
- [ ] **Task 16.2 (M, ARCH)** Full staging E2E on hosted infra (redo Task 6.5 properly): real sandbox payments, real Zoom, real email, Celery clustered; document results.
- [ ] **Task 16.3 (M, ARCH)** Security review pass: `/security-review` on the whole repo, dependency audit, pen-test checklist for auth, payments, uploads, webhooks.
- [ ] **Task 16.4 (M, ANESU)** UAT with beta tutors and students; SOW Milestone 2/3 sign-off; admin video walkthrough/handover.
- [ ] **Task 16.5 (M, ANESU+ARCH)** DNS/SSL cutover, HSTS preload, transfer vendor accounts to the client, move off the shared Gmail identity, enable 2FA, start the 30-day warranty clock.
- [ ] **Task 16.6 (S, ARCH)** Post-launch monitoring runbook, on-call, error budget, backup restore drill.

---

## Appendix A - Audit finding → task traceability (selected)

| Finding | Task |
| :--- | :--- |
| Admin self-registration / role PATCH | 7.1 |
| Unsigned PayFast/PayPal webhooks, default amount 9.0 | 7.2, 7.3 |
| Insecure `SECRET_KEY`/settings fallbacks | 7.4 |
| Open default permissions, no throttling | 7.5, 7.6 |
| Blacklist app missing, no logout | 7.7 |
| CRM dossier writable for any user id, IDOR | 7.8 |
| Unvalidated presigned upload | 7.9, 11.3 |
| Silent mock fallbacks, fake auth | 8.2, 8.3 |
| Role cookie trusted by middleware | 8.4 |
| No password reset / email verify | 8.5 |
| `reserve` returns no booking id; `POST /bookings/` unused/unvalidated | 9.2 |
| No `transition_booking()` | 9.1 |
| Credit-farming via `report-outage` | 9.7 |
| Stub checkout / simulated gateway buttons | 10.2, 10.3 |
| No refunds executed; credits unbuyable | 10.6, 10.7 |
| Non-USD treated as USD in escrow | 10.5 |
| Fake payout batch / fake telemetry | 11.8, 15.4 |
| No TeacherProfile on tutor register; no apply flow | 11.1, 11.2 |
| Fake Zoom meetings; single host collision | 12.1 |
| Reminders only log | 12.2 |
| GCal no OAuth/refresh; Eskom hardcoded | 12.4, 12.5 |
| Dev-only Dockerfiles, no CI, no Sentry | 13.1, 13.3, 13.4 |
| No legal pages / DSR / retention | 14.x, 12.9 |
| Hardcoded tutor pages, no SEO metadata | 15.1, 15.5 |

## Appendix B - Doc drift fixed or to fix

- `CLAUDE.md` status snapshot and "next free ID is `ERR-004`" were stale (Task 6.5 done; `ERR-004`/`ERR-005` used → next free is `ERR-006`). Updated 2026-10-02.
- `MASTER_MODULE_ROADMAP_AND_ARCHITECTURE.md` still shows PayFast/PayPal and payouts as queued. Reconcile in Task 7.11.
- `PROGRESS_AND_ROADMAP.md` shows Phases 1-6 `COMPLETED`; read with §0 above. Phases 7-16 tracked here and summarised in its new §5.
