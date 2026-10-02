# Phase 7A - Security Changes (Reference)

**Completed:** 2026-10-02 · **Author:** Claude (lead architect) · **Plan:** `PHASE_7_EXECUTION_PLAN.md` · **Decisions:** `DECISIONS_D1_D12.md`
**Verification:** backend `pytest` 173 passed (baseline 74), `manage.py check` and `makemigrations --check` clean, `npm run build` passes, live R2 upload test passed.

This document describes what changed, what API clients and operators must now do differently, and what is still open.

## 1. Behaviour changes by task

| Task | Before | After |
| :--- | :--- | :--- |
| 7.1 Registration | Anyone could register or PATCH themselves as `admin`; email optional | `role` limited to `student`/`teacher`; `admin` returns 400. `UserSerializer.role` is read-only. Email required and unique (case-insensitive). |
| 7.2 PayFast ITN | Unauthenticated; amount and booking taken from the request | Signature (MD5 + passphrase), source IP, merchant id, amount/currency vs the stored expected value, and a server-to-server `validate` postback must all pass. Failures return 400 and are logged. |
| 7.3 PayPal | Unauthenticated; defaulted to `9.0` when amount missing | PayPal's `verify-webhook-signature` API, then the capture is re-read from PayPal and its amount/currency compared to the stored expectation. Only `PAYMENT.CAPTURE.COMPLETED` acts. PayPal outages return 503 so PayPal retries. |
| 7.4 Settings | Dev secret key and localhost origins could reach production; Zoom secret fell back to `SECRET_KEY` | `config/settings/guard.py` aborts startup on unsafe values. Zoom webhooks fail closed with no secret. `wsgi`/`asgi`/`celery` default to production settings. |
| 7.5 Permissions | Default `IsAuthenticatedOrReadOnly` plus session auth; staff implicitly passed student/teacher checks | Default `IsAuthenticated`, JWT only. Every API view must declare permissions (enforced by a test). `is_staff` no longer implies student/teacher. |
| 7.6 Throttling | None | Anon 60/min, user 300/min, login 5/min, register 5/h, upload 30/h, checkout 20/h, webhooks 120/min. |
| 7.7 Logout | None; refresh tokens could not be revoked | `token_blacklist` installed; `POST /api/v1/auth/logout/` blacklists the supplied refresh token. |
| 7.8 Authorization | Any teacher could edit any student's dossier; admin edits went to an arbitrary tutor; outage refund repeatable; unverified tutors publicly viewable | Dossier edits need a lesson or existing dossier with that student; admins must pass `teacher_id`. Outage reports and memos are status-guarded and the refund is atomic and idempotent. Unverified tutors 404. Hardcoded TEFL URL removed. |
| 7.9 Uploads | Any content type, no size cap, prefix match without trailing slash | Per-prefix content-type allowlist and size cap (`apps/common/upload_policy.py`); `size` required; expiry clamped 60-900 s; `//`, `%` and control characters rejected. |

## 2. API contract changes

- `POST /api/v1/auth/register/`: `role` ∈ {`student`, `teacher`}, `email` required.
- `POST /api/v1/auth/logout/` (new): body `{"refresh": "<token>"}`, auth required, returns 205. 400 if the token is invalid or belongs to another user.
- `POST /api/v1/payments/checkout/init/`: now persists an `INITIALIZED` `PaymentTransaction`. Returns `transaction_reference` and string `amount`. The booking must be `pending_payment` (409 otherwise). PayFast returns signed `fields` plus `action_url`; PayPal returns `custom_id` (= the reference, which PayPal echoes back).
- `POST /api/v1/integrations/storage/presigned-url/` (upload): requires `content_type` (allowlisted for the prefix) and `size` in bytes. The returned PUT URL has `Content-Length` signed, so R2 rejects a different size. Download responses are unchanged.
- `POST /api/v1/bookings/<id>/report-outage/`: 409 unless the booking is `confirmed` or `in_progress`.
- `POST /api/v1/bookings/<id>/memo/`: 409 for bookings that are unpaid, cancelled, disputed, no-show or interrupted.
- `PATCH /api/v1/teacher/students/<id>/dossier/`: 403 for a tutor with no history with the student; admins send `teacher_id`.
- `POST /api/v1/teachers/availability/manage/`: 403 (not 500) for a teacher without a profile.
- Rate limiting returns 429 with `Retry-After`.

## 3. Data model

- `payments.0006_paymenttransaction_merchant_reference`: nullable unique `merchant_reference`. Checkout creates the row with `gateway_reference="INIT-<ref>"`; the verified webhook rebinds `gateway_reference` to the gateway's own id (PayFast `pf_payment_id`, PayPal capture id) and then calls the unchanged idempotent `process_payment_webhook`. Ledger and DEF-501 logic were not modified.
- Run `python manage.py migrate` (also installs the `token_blacklist` tables).

## 4. Configuration

New or changed environment variables (see `.env.example`):

| Variable | Purpose | Production rule |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | Signing key | Required, >=50 chars, not `django-insecure…` |
| `DJANGO_ALLOWED_HOSTS` | Hosts | Real hostnames only |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | Origins | Required, `https://`, no localhost |
| `ZOOM_WEBHOOK_SECRET_TOKEN` | Zoom HMAC | Required |
| `PAYFAST_MERCHANT_ID/KEY/PASSPHRASE`, `PAYFAST_SANDBOX`, `PAYFAST_NOTIFY_URL` | PayFast | If `PAYFAST_SANDBOX=False`: all required, sandbox id `10000100` forbidden |
| `PAYFAST_SKIP_IP_CHECK` | Dev-only IP-check bypass | Must be false |
| `PAYFAST_TRUSTED_PROXY_COUNT` | Read client IP from `X-Forwarded-For` | Set to the number of proxies |
| `ZAR_PER_USD` | Interim ZAR rate until the D-1 price table exists | Default 18.0 |
| `PAYPAL_CLIENT_ID/SECRET`, `PAYPAL_MODE`, `PAYPAL_WEBHOOK_ID` | PayPal | `PAYPAL_WEBHOOK_ID` required when PayPal is configured |
| `THROTTLE_NUM_PROXIES` | Proxy count for rate limiting | Set behind a load balancer |
| `CLOUDFLARE_R2_*` | R2 storage | Local `.env` configured and live-tested |

Local development: settings default to `config.settings.local` for `manage.py`; Docker compose sets it explicitly. The tests' autouse fixture clears the cache per test so throttle counters do not leak.

## 5. Tests added (99 in 7A, +47 in 7B = 220 total)

`test_security_auth.py` (registration, logout, permission declaration, anonymous access), `test_settings_guard.py` (production guard, Zoom fail-closed), `test_upload_hardening.py` (policy + throttles), `test_permission_matrix.py` (IDOR, CRM, admin routes, teacher visibility), `test_payment_verification.py` (checkout, 12 PayFast and 10 PayPal cases with the network faked). Gateway HTTP goes through `requests` inside `apps/payments/gateways/`, which tests monkeypatch; there is no "fake gateway" flag that could reach production.

Existing tests were adjusted only where behaviour intentionally changed (the upload tests now send `size`); none were deleted.

## 5b. Phase 7B - adversarial review fixes (2026-10-02)

An independent security/systems-design review of 7.1-7.3 confirmed no forgeable-payment or admin-escalation path, but found gaps around them. Fixed here (suite 173 -> 220 passing; each key fix was mutation-checked by reverting it and watching its test fail):

| Finding | Fix |
| :--- | :--- |
| **HIGH** Second payment for an already-settled reference returned 200 and was dropped (money taken, no ledger, no refund) | PayFast/PayPal views compare the incoming gateway id with the settled one. A different id is recorded as an `UNALLOCATED` transaction, posted DR gateway cash / CR 2030 (no wallet credit, per D-6) and a `GatewayAnomaly` is raised. Idempotent on redelivery. |
| **HIGH** A late second payment on a COMPLETED/IN_PROGRESS/etc. booking flipped it to `DISPUTED` (griefing; freezes escrow) | `process_payment_webhook` only acts on `PENDING_PAYMENT` / `CANCELLED` (DEF-501 path unchanged). Any other state is held as unallocated and the booking is never touched. `UNALLOCATED` rows are excluded from escrow selection. |
| **HIGH** `NUM_PROXIES = 0 or None` made DRF trust the client's whole `X-Forwarded-For`, so rotating the header bypassed every IP throttle | `NUM_PROXIES` is now the integer (0 = ignore XFF). Added a per-username login throttle (`login_user`, 10/hour). |
| MED Authenticated-but-rejected payments (amount mismatch, unknown ref) were only logged | `GatewayAnomaly` rows, written only after signature/IP checks, de-duplicated across gateway retries. |
| MED PayPal re-serialised the event before verifying | Raw request bytes are forwarded verbatim in `webhook_event`. |
| MED Anyone could spend PayPal API calls; PayPal 4xx treated as outage | Local pre-checks (`SHA256withRSA`, https `*.paypal.com` cert host, transmission time window) before any outbound call; 400/422 from PayPal = invalid (400), only 5xx/network = 503. Token refreshed once on a 401. Capture id URL-quoted. |
| MED Guard gaps | Production now requires `THROTTLE_NUM_PROXIES>=1` and (if PayFast configured) `PAYFAST_TRUSTED_PROXY_COUNT>=1` unless `BEHIND_NO_PROXY=1`; passphrase whenever PayFast is configured; sandbox in prod needs `ALLOW_PAYMENT_SANDBOX_IN_PROD=1`; `PAYPAL_MODE` must be `live`/`sandbox`; PayPal secret required; notify URL https. |
| MED Celery fulfillment dispatched inside the open transaction and failures were swallowed | `transaction.on_commit`; failure logged with `logger.exception`. |
| MED PayFast postback held the row lock; DNS lookups repeated on every ITN when failing | Postback now runs between two short transactions (state re-checked under the lock); DNS failures are negative-cached 60s; optional `PAYFAST_EXTRA_ALLOWED_CIDRS`. |
| MED Logout needed a live access token | `POST /auth/logout/` is `AllowAny`, authenticated by the refresh token itself. |
| LOW PayFast `~` encoding (`%7E`), non-UUID/non-object checkout body (500), unverified/inactive tutor, past slot, zero price payable | Fixed with tests. Registration: IANA timezone validated, usernames unique case-insensitively, password similarity now evaluated with the user's own details. |

Migration `payments/0007`: `PaymentTransaction.Status.UNALLOCATED`, `LedgerEntry.EventType.UNALLOCATED_PAYMENT`, model `GatewayAnomaly`.

**Deliberately not done, with reasons**
- PayPal transmission-time window is 4 days (not 5 minutes): PayPal retries for ~3 days and may keep the original time; replay safety comes from idempotency.
- No hard-coded PayFast IP ranges: I could not verify them offline. Set `PAYFAST_EXTRA_ALLOWED_CIDRS` from PayFast's published list (DNS resolution still applies).
- A `CANCELLED` booking is still treated as payable (DEF-501 path) because the model cannot yet tell "hold expired" from "student/teacher cancelled". Needs `transition_booking()` / a cancellation reason (Phase 9).
- Not done (tracked): refunding unallocated money at the gateway (Phase 10 refund service), gateway fee capture to 5030, PayPal DENIED/REFUNDED/DISPUTE and PayFast chargeback handlers, daily gateway-vs-ledger reconciliation, re-dispatch of fulfillment for CONFIRMED bookings with no Zoom meeting, DB unique index on lower(email), NFKC username normalisation, JWT claims still carry email/role (the backend re-reads the DB per request; frontend must not trust them), refusing `config.settings.local` when `DATABASE_URL` looks like production, appending rejected-webhook audit table.

## 6. Known limits and follow-ups

- Gateways are verified against faked HTTP only. A real PayFast/PayPal **sandbox** run is Phase 10 and needs the account checks in `TOOL_ACCESS_AND_ACCOUNTS.md`.
- R2 has no presigned POST, so the size cap relies on the signed `Content-Length`. Verified live (wrong size and wrong type rejected, correct upload accepted).
- Access token lifetime stays 60 min: the frontend has no refresh flow yet. Move to 15 min in Phase 8.
- The `sharon_user_role` cookie is client-controlled and only drives UI routing; the backend is the only security boundary.
- A self-registered `teacher` has no `TeacherProfile` until Phase 11 adds the application flow; such users can authenticate but cannot manage availability.
- `ReportOutageView` still refunds a credit; D-6 ("gateway refund only") conflicts with that and is open in `DECISIONS_D1_D12.md`.
- No DB-level case-insensitive unique email constraint yet (serializer enforced). Add after confirming no duplicate rows exist.
- Task 7.10: check `.mcp.json`, `.claude/`, `.codex/`, `.agents/` and git history for tokens (`.env.apikeys` is empty).
