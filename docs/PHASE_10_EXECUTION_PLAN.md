# Phase 10 Execution Plan - Real payments (and the two tracks that run beside it)

**Created:** 2026-10-03 · **Author:** Claude (lead architect) · **Parent:** `PRODUCTION_READINESS_PLAN.md` §Phase 10 · **Inputs:** the code as of `develop` @ `4ea9c16`, `CANCELLATION_AND_REFUNDS.md`, `SETTLEMENT_PATHS.md`, `DECISIONS_D1_D12.md`, `TOOL_ACCESS_AND_ACCOUNTS.md`.

## 1. Where we are

| Phase | State |
| :--- | :--- |
| 7 Security + spec freeze | Code done (7.1-7.9). **Open, human:** 7.10 secrets check, decisions D-3, D-4, D-7..D-12. 7.11 docs hygiene waits on those. |
| 8 Honest frontend + real auth | Done except **8.9** (Next.js major upgrade, a launch blocker for security advisories, not for development). |
| 9 Booking core | **Done** (9.1-9.10). One validated state machine, holds, slot grid, list, cancellation + reschedule, settlement paths, Zoom attendance, memo, reviews. 876 backend + 93 frontend tests. |
| 10 Real payments | **Not started as a phase, but about a third of the groundwork exists** (see §2). |
| 11-16 | Not started. |

Money safety is in good shape: verified webhooks, a double-entry ledger that cannot be edited, "settled exactly once", refund requests, expiring credit lots. What is missing is **the user-facing half of payments**: nobody can actually pay, buy a pack, or get a refund paid out.

## 2. What already exists for Phase 10 (so we do not rebuild it)

| Piece | State today |
| :--- | :--- |
| PayFast ITN verification (signature, source IP, server postback, amount match) | Done (7.2) |
| PayPal webhook verification + capture lookup | Done (7.3) |
| `POST /payments/checkout/init/` | Creates the `INITIALIZED` transaction and the **signed PayFast form fields**; guards hold, slot and tutor. For PayPal it returns a `custom_id` but **does not create a PayPal Order** yet. |
| Frontend checkout page | Still simulated (`setTimeout`, fake confirm). Timer must follow `hold_expires_at`. |
| Prices | Tutor row `price_per_25min_usd`; ZAR via `ZAR_PER_USD` (18.0) config; FX 18.75 hardcoded in ledger. No price table, no EUR/JPY. |
| Refunds | `RefundRequest` + ledger 2050 + `RefundGateway` plug-in point. Default backend only leaves requests pending (Task 9.6). |
| Credits | Expiring lots, `spend_credit()`, expiry job. **No purchase flow, no redemption endpoint.** |
| Receipts, DB ledger trigger, Postgres payment tests | None |

## 3. Recommendation: what to do next

**Do Phase 10 now, and start the CI track (13.3) in the same week.**

Why Phase 10 first: it is the critical path to a demonstrable product (book -> pay -> lesson -> tutor paid) and Phases 11 (payouts) and 16 (live gateways) both depend on it. Phase 12 (Zoom/email) can wait: attendance and cancellation already behave correctly against mocks, and 12 is mostly real-account work.

Why CI now: the full backend suite takes 15-50 minutes on this machine, nothing runs automatically, and every Phase 10 change touches money. A GitHub Actions run (Postgres + Redis services) also gives us the first run on real Postgres, which Task 10.10 needs anyway.

### Three tracks

| Track | Tasks | Who | Notes |
| :--- | :--- | :--- | :--- |
| **A. Payments (critical path)** | 10.1 -> 10.5 -> 10.2 -> 10.4 -> 10.7 -> 10.6 -> 10.3 -> 10.8 -> 10.9 -> 10.10 | ARCH backend, CODEX frontend (10.3) | §5 |
| **B. Ops (parallel)** | 13.3 CI first, then 13.2 dependency lockfile, 13.1 production images | ARCH | Needs nothing from Anesu. Start day 1. |
| **C. Hygiene (small, fit in the gaps)** | 7.10 secrets check (Anesu), 8.9 Next.js 15/16 upgrade, 7.11 docs reconcile once D-3/4/7/8 are answered | Anesu / ARCH | 8.9 must land before the first hosted staging (13.6). |

## 4. What I need from Anesu before / during Phase 10

| # | Need | Why | Recommended answer |
| :--- | :--- | :--- | :--- |
| 1 | **PayPal sandbox app credentials** (client id, secret, webhook id) and **PayFast sandbox** merchant details, put in `backend/.env` (never in chat or git). Registry shows both as `AUTHORIZED`, account id still `TBD`. | 10.2 / 10.4 / 10.7 talk to the sandboxes. The PayFast sandbox values in `.env.example` are public test values and already work for the form. | Create the PayPal sandbox REST app under `sharonremotedeveloper@gmail.com`, confirm the active account when I run the registry check. |
| 2 | **D-7 credit bundles** | 10.1 / 10.6 define what can be bought. | Packs of 5 / 10 / 20 at 0 / 5 / 10 % off; no subscriptions in MVP. |
| 3 | **D-1 trial lesson**: yes or no, and price | 10.1 price catalog | No trial in MVP (first lesson at normal price); revisit after launch. |
| 4 | **Pack expiry** (from D-6): confirm 30 days applies to purchased packs, or set `CREDIT_EXPIRY_DAYS_BUNDLE` (recommend 90 days minimum for 10/20 packs; legal check under D-12) | 10.6 | 90 days for packs, 30 for refunds / bonuses. |
| 5 | **Currencies at launch**: USD + ZAR only, or also EUR + JPY | The plan lists all four; Japan/Korea/Europe are the target markets, PayPal handles all three foreign currencies | USD, EUR, JPY via PayPal; ZAR via PayFast. JPY has no decimals: the catalog must model that. |
| 6 | **FX approach** for ledger valuation: daily rate source + buffer | 10.5 | Use a configurable rate table updated by a daily job (source decided in 15.4 pricing screen); store the rate on every entry. Needs a source: confirm "exchangerate.host or the gateway's own conversion" is acceptable. |
| 7 | D-12 (entity / VAT / SARB) | Does **not** block sandbox work; blocks live gateways (16.1) and receipts' tax fields | Start the accountant / attorney conversation now, it has the longest lead time. |

Items 2-6 each take one line to answer. Without them I will proceed with the recommended answer and mark it provisional.

## 5. Track A in order

Dependencies: 10.1 and 10.5 are foundations; 10.2 builds on them; 10.4 and 10.7 need 10.2; 10.6 needs 10.1 + 10.7; 10.3 (frontend) can start once the 10.2 contract is frozen.

### Sprint 10-A - Foundations (about 4 days)

**10.1 Price catalog (M).**
* Models `Currency`-aware `Price` (per product, per currency, `Decimal`, minor-unit exponent so JPY = 0 decimals) and `CreditBundleProduct` (name, credits, discount, active). One source of truth: lesson price per currency is derived from the tutor's USD price **or** a flat catalog price (D-1 says platform-set flat, so: catalog price per currency, tutor row price becomes display only or is removed).
* `GET /payments/prices/` and `GET /payments/credits/bundles/`. Remove `float()` money and the 18.0 / 18.75 literals; frontend `lib/currency.ts` reads from the API.
* Tests: rounding per currency (JPY integer, others 2dp), no float anywhere (static check), bundle discount math, inactive products hidden.

**10.5 Multi-currency ledger (M).**
* Every `LedgerEntry` stores the FX snapshot (rate + source + timestamp) that produced `amount_zar`; the release job and `ledger_service` stop treating non-USD as USD (`payments/tasks.py` release uses USD maths today).
* Tests: EUR, JPY, ZAR capture -> clear -> refund each balance to zero in their own currency and in ZAR; rate change between capture and clearance does not unbalance either side.

**13.3 CI (M, Track B, same days).** Backend job (Postgres + Redis services, `pytest`, `makemigrations --check`, `check --deploy`, `pip-audit`), frontend job (`tsc`, `npm test`, `next build`, `npm audit` non-blocking until 8.9). Branch protection on `develop` / `main` is Anesu's click in GitHub.

### Sprint 10-B - Taking money (about 5 days)

**10.2 Checkout (L).**
* PayPal: create the Order via Orders v2 server-side (amount and currency from the catalog, `custom_id` = our reference, `reference_id` = booking), return the approval data; capture endpoint called by the frontend after approval; webhook remains the source of truth.
* PayFast: already builds the signed form; add `return_url` / `cancel_url` handling and `notify_url` from settings only.
* Keep every guard from 9.4 (hold, slot, tutor, lock extension) and return `hold_expires_at`.
* Tests (sandbox calls mocked at the HTTP layer): order created with exact amount, currency mismatch rejected, retry returns the same pending transaction instead of a second one, expired hold refused, capture of someone else's order refused.

**10.4 Webhook handler completion (M).**
* Handle `FAILED`, `DENIED`, `CANCELLED`, `REFUNDED`, chargeback / dispute events; PayFast `CANCELLED` / `FAILED` ITNs must mark the transaction `FAILED` (today they are only acknowledged, see `BOOKING_HOLDS.md`); unknown booking id -> quarantined anomaly, never a 500; record gateway fees to 5030.
* Real `reconcile_pending_transactions_task`: asks the gateway for the status of every transaction stuck in `INITIALIZED` / `PENDING` older than the grace period and applies it through the same idempotent handler.
* Tests: each event type, duplicate and out-of-order delivery, reconcile applies exactly once.

### Sprint 10-C - Giving money back and credits (about 5 days)

**10.7 Real refund gateway (M).** Replace `ManualSandboxRefundGateway` with `PayPalRefundGateway` (capture refund API) and `PayFastRefundGateway` (PayFast refund API; if the sandbox does not support it, keep PayFast on the manual path and document it). Idempotency key = refund id; marks `PaymentTransaction.REFUNDED`; handles partial and failed refunds; the existing `process_pending_refunds_task` drives it. Tests: success, gateway error recorded not swallowed, double-run safe, refunded-then-webhook (the gateway's own refund notification) does not post twice.

**10.6 Credit purchase + redemption (M).**
* Buy a pack through the same checkout (`PaymentTransaction` without a booking, or a `CreditOrder`), webhook grants one lot via `grant_credit(source=purchase, unit_value=price/credit)` and posts the 2040 entry (cash in, wallet liability up).
* `POST /bookings/<id>/redeem-credit/`: `spend_credit()` atomically, booking -> confirmed, escrow funded from the wallet liability (DR 2040, CR 2010) so commission and the 80/20 split work unchanged.
* **Refund of a credit-funded booking restores the lot** (earliest of original expiry and now + 7 days) instead of calling a gateway; extend `request_refund` accordingly.
* Tests: concurrent redemptions never overspend, expired lots excluded, FIFO by expiry, refund restores, ledger balances for pack purchase -> redemption -> clearance -> breakage.

**10.3 Frontend checkout (L, CODEX, starts when the 10.2 contract is frozen).** Real `@paypal/react-paypal-js` buttons (create / capture via backend), PayFast form redirect, return / cancel pages, processing screen that polls the booking until the webhook confirms; timer follows `hold_expires_at`; show the 409 messages; wallet top-up and "pay with credits"; refunds list with **Convert to wallet credit**; delete `confirmPayment` / `redeemCredit` fakes. Cancel + reschedule screens use the 9.6 client (or stay for Phase 15: say which at sprint start).

### Sprint 10-D - Close-out (about 3 days)

* **10.8 Receipts (S):** `Receipt` model + PDF per capture and per refund, shown in the wallet; VAT fields stubbed until D-12.
* **10.9 Ledger backstop (S):** Postgres trigger rejecting UPDATE / DELETE on `LedgerEntry` (migration + Postgres-only test).
* **10.10 Payment test suite (M):** runs in CI on Postgres: signature failures, replay, amount mismatch, late payment, multi-currency, refund, credit purchase / redemption, concurrency (two webhooks / two redemptions at once).
* Also here: `PLATFORM_COMMISSION_RATE` as a setting (still literal 0.80 in `ledger_service` and the release job), and the sandbox end-to-end demo script below.

**Rough total: about 3 weeks of focused work** (L = 3-5 days, M = 1-2). The estimates assume answers to §4 arrive in week 1.

## 6. Carry-overs from earlier phases that land in Phase 10

| From | Item | Lands in |
| :--- | :--- | :--- |
| 9.6 | Real refund gateway; credit-funded refund restores the lot; `CREDIT_EXPIRY_DAYS_BUNDLE` decision | 10.7, 10.6 |
| 9.4 | Checkout timer follows `hold_expires_at`; PayFast CANCELLED / FAILED ITN marks the transaction failed | 10.3, 10.4 |
| 9.6 | `PLATFORM_COMMISSION_RATE` setting | 10.5 / close-out |
| 9.6 | Expiry warning e-mail (7 days before) | Phase 12 notifications (12.2) |
| 9.6 | Deactivated tutor's future lessons need an admin routine | Phase 15 admin (15.4) |
| 9.8 | Zoom registrant links (needs a Zoom plan decision, D-9) and sandbox check of the identity assumptions | Phase 12 (12.1) |
| 7.x | `PAYFAST_EXTRA_ALLOWED_CIDRS`, `SESSION_SECRET`, `TRUSTED_PROXY_COUNT` real values | 13.6 hosted staging |

## 7. Exit gate for Phase 10

All of these demonstrated against the **sandboxes**, from the UI, on Postgres:

1. A student pays a lesson with **PayPal (USD, EUR, JPY)** and with **PayFast (ZAR)**; the booking confirms only after the verified webhook; a refresh mid-payment does not double charge.
2. A student buys a **pack**, books two lessons with credits, cancels one (credit restored) and lets one expire (breakage posted).
3. A student cancels > 2 h out: **sandbox refund arrives** and the ledger shows 2010 -> 2050 -> cash; < 2 h: tutor is paid 80 % at +24 h.
4. A tutor no-show and an outage both refund; a late payment on a lost slot is quarantined and refunded.
5. For each currency: **trial balance is zero** and every booking's escrow returns to zero.
6. CI green on `develop` (backend on Postgres, frontend build), payment suite included.
7. No `float` in money code, no hardcoded FX, no simulated payment code left in the frontend.

## 8. After Phase 10

Order recommended: **11 (tutor lifecycle + payouts)** and **12 (integrations + notifications)** can run in parallel streams (11 is mostly backend + CODEX screens; 12 needs real Zoom / Resend / Google accounts), then **13.6 hosted staging** (needs 8.9 and real env values), then 15 (screens, admin, SEO, tests), 14 (legal, driven by Anesu's counsel), 16 (UAT and launch). The longest human lead times are D-12 (entity, VAT, SARB), live PayPal Business / PayFast merchant approval (16.1) and counsel for the legal pages (14.1): **start those in parallel with Phase 10**.

## 9. Risks

| Risk | Mitigation |
| :--- | :--- |
| Sandbox access slips (PayPal developer login, 2FA) | Build against mocked HTTP first (all tests do), do the live-sandbox pass at the end of each sprint |
| PayFast refund API unavailable in sandbox | Keep PayFast refunds on the manual-with-admin-action path and say so; PayPal path is fully automated |
| JPY / multi-currency rounding drift | Money as `Decimal` with per-currency exponent; ledger zero-sum tests per currency (10.5) |
| Local suite is slow (15-50 min) and hides regressions | CI in sprint 10-A; run targeted files locally |
| Ledger migration on live data later | Everything here is additive; backfill scripts tested on a copy; ledger stays append-only |
| Scope creep into subscriptions / trial lessons | Out of MVP unless Anesu says otherwise (D-7, D-1) |
