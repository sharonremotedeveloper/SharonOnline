# Phase 10 Execution Plan - Real payments (and the work that can proceed without waiting on Anesu)

**Created:** 2026-10-03 · **Re-baselined:** 2026-10-03 after merging Codex's remediation branch · **Author:** Claude (lead architect) · **Parent:** `PRODUCTION_READINESS_PLAN.md` §Phase 10 · **Inputs:** `develop` + `integration/codex-remediation`, `REMEDIATION_INTEGRATION.md`, `CANCELLATION_AND_REFUNDS.md`, `SETTLEMENT_PATHS.md`, `DECISIONS_D1_D12.md`, `TOOL_ACCESS_AND_ACCOUNTS.md`.

## 1. Where we are

| Phase | State |
| :--- | :--- |
| 7 Security + spec freeze | Code done. **Open, human:** 7.10 secrets check; decisions D-3, D-4, D-7..D-12. |
| 8 Honest frontend + real auth | Done, including **8.9** (Next 16 / React 19, 2026-10-03). |
| 9 Booking core | **Done** (9.1-9.10). |
| **Codex remediation (8 batches)** | **Reviewed and merged** (`REMEDIATION_INTEGRATION.md`): containment, funding provenance, credit packs and redemption, payment/ledger hardening, Zoom identity, profiles/support, tutor wallet + encrypted payout settings, Eskom, CI. Backend 980 tests, frontend 95. |
| 10 Real payments | **About half the groundwork exists** (§2). Remaining: PayPal orders and buttons, real refund gateways, lesson price catalog, event coverage, receipts, sandbox verification. |
| 11-16 | Not started, apart from pieces Codex delivered (11.7 tutor wallet + payout settings, 12.5 Eskom, 12.8 support, 15.9 contracts). |

## 2. Baseline for Phase 10 (what exists, what does not)

| Piece | State |
| :--- | :--- |
| PayFast ITN verification, PayPal webhook verification | Done (7.2, 7.3) |
| Booking funding record, FX snapshot on transactions and ledger rows (USD, ZAR), provider-fee snapshot, per-currency balanced journals | Done (Codex batches 2-3). **EUR and JPY are rejected until an FX source is approved.** |
| Append-only ledger: Python guards + Postgres trigger | Done; the Postgres test has never run (needs the first CI run) |
| Reconciliation of stuck payments | Provider-aware, only an authoritative failure fails a transaction (batch 3); event coverage to verify (below) |
| Credit packs (USD/ZAR/EUR/JPY prices), purchase checkout, credit redemption, immutable wallet history, 30-day expiring lots, expiry job | Done (batch 2 + 9.6) |
| Refunds: request -> ledger 2050 -> gateway; credit-funded lessons restore the credit; student can convert to wallet credit | Done (9.6). **The real PayPal / PayFast refund backends are not built** (default backend leaves requests pending). |
| `POST /payments/checkout/init/` | Booking or credit-pack target, server-side amount, hold guards. **PayFast signed form: done. PayPal: returns a reference but does not create a PayPal Order yet.** |
| Frontend checkout | Polls server state, never confirms client-side. PayFast form posts for real. **The PayPal button is a placeholder** (no `@paypal/react-paypal-js`). |
| Lesson price | **Done (10.1):** `LessonPrice` catalog, `GET /payments/lesson-prices/`; checkout, booking payloads and admin read it. Provisional prices await confirmation |
| Receipts / invoices | None |
| CI | `quality-gates.yml` + `api-contract.yml` exist; never run on GitHub |

## 3. Recommendation

Finish Phase 10 on mocked HTTP now (everything below that does not need your accounts), then do the live-sandbox pass the moment credentials exist. Run the remaining CI and dependency work in parallel. The order:

| # | Work | Needs Anesu? | Size |
| :--- | :--- | :--- | :--- |
| 1 | **Track B: finish CI + dependencies + images** (13.3 remainder: `check --deploy`, `pip-audit`/`npm audit`, Dependabot; 13.2 lockfile, runtime vs test requirements; 13.1 production Dockerfiles + a CI image-build job) | No (branch protection is a click for you) | 3-4 days |
| 2 | **8.9 Next.js 14 -> 15/16 upgrade** on its own branch (React 19, `next build`, tests, lint, middleware/BFF) | No | 2 days |
| 3 | **Sprint 10-A: 10.1 lesson price catalog** (platform-set flat price per currency, `Decimal`, JPY 0-decimal; remove `ZAR_PER_USD` and the 18.75 literals from live paths), using the recommended defaults below | Provisional answers (§4) | 2 days |
| 4 | **Sprint 10-B: 10.2 PayPal Orders v2 create + capture**, return/cancel handling; **10.3 real PayPal buttons** in the checkout; **10.4** remaining events (REFUNDED, chargeback/dispute, DENIED, PayFast CANCELLED -> FAILED, unknown booking -> quarantine) | No for code; sandbox check needs credentials | 5 days |
| 5 | **Sprint 10-C: 10.7 real refund gateways** (PayPal capture refund; PayFast refund, or keep PayFast on the manual action if its sandbox lacks refunds) with idempotency keys; the existing job drives them | Sandbox check needs credentials | 3 days |
| 6 | **Sprint 10-D:** 10.8 receipts + PDFs; `PLATFORM_COMMISSION_RATE` setting; 10.10 payment suite on Postgres in CI; sandbox E2E script | CI first run; credentials for the live pass | 4 days |
| 7 | **Phase 11 tasks that need no decision:** 11.1 tutor registration creates the profile + `/teachers/me/`; 11.6 availability CRUD validation; 11.3 upload-commit; 11.4 vetting workflow | No | 1-2 weeks, parallel |
| 8 | **Phase 12 tasks I can do on mocks:** 12.2 notification system (in-app + e-mail), 12.1 Zoom client hardening, 12.4 Google Calendar OAuth | Real accounts later | parallel |

Rough total for items 1-6: about three weeks. Items 7-8 interleave.

### Out of scope until you answer
Payout execution (11.8) waits on D-3; memo SLA behaviour (11.10) on D-4; recording (12.9) on D-8; Zoom host strategy (12.1) on D-9; hosted staging (13.6) on D-10 and 8.9; legal pages (14.x) on D-12; live gateways (16.1) on D-12.

## 4. What I need from Anesu (recommended answer in brackets; without a reply I proceed with it and mark it provisional)

| # | Need |
| :--- | :--- |
| 1 | **PayPal sandbox app credentials** (client id, secret, webhook id) in `backend/.env` (never chat or git); PayFast sandbox values already work. Registry check first: both are `AUTHORIZED`, account id `TBD`. |
| 2 | **D-7 packs** (5 / 10 / 20 at 0 / 5 / 10 % off, no subscriptions). Codex's seeded catalog already holds launch packs; confirm or change the numbers. |
| 3 | **D-1 trial lesson** (none in MVP). |
| 4 | **Pack expiry** (90 days for purchased packs, 30 for refunds and bonuses). Today every credit expires in 30 days. |
| 5 | **Currencies at launch** (USD, EUR, JPY via PayPal; ZAR via PayFast). EUR and JPY need an FX source before a lesson can be settled. |
| 6 | **FX source** for ledger valuation (a configurable daily rate table; which provider is your call). |
| 7 | **D-12** (entity, VAT, SARB): start with your accountant and attorney now. Does not block sandbox work. |
| 8 | Housekeeping: **GitHub branch protection** on `develop` and `main` once CI has run; **7.10 secrets check** (`.mcp.json`, `.claude/`, `.codex/`, `.agents/`, git history); `gh auth switch --user sharonremotedeveloper` before I push. |

## 5. Work I can start immediately (no input needed)

In order: **(1) Track B** (CI completion, lockfile, production images), **(2) 8.9 Next.js upgrade**, **(3) 10.1 price catalog**, **(4) 10.2 / 10.3 / 10.4 on mocked HTTP**, **(5) 10.7**, **(6) 10.8-10.10**, with **Phase 11/12 decision-free tasks** interleaved. Every task keeps the project loop: failing test first, mutation check on the load-bearing lines, full suites, docs and ERR log, feature branch, commit; merging and pushing wait for your word.

## 6. Exit gate for Phase 10

Demonstrated against the **sandboxes**, from the UI, on Postgres in CI:

1. A student pays a lesson with PayPal (USD, plus EUR / JPY once the FX source exists) and with PayFast (ZAR); the booking confirms only after the verified webhook; a refresh mid-payment does not double charge.
2. A student buys a pack, books two lessons with credits, cancels one (credit restored) and lets one expire (breakage posted).
3. A student cancels > 2 h out: the sandbox refund arrives and the ledger shows 2010 -> 2050 -> cash; < 2 h: the tutor is paid 80 % at +24 h.
4. Tutor no-show and outage refund; a late payment on a lost slot is quarantined and refunded.
5. For each currency: trial balance is zero and every booking's escrow returns to zero.
6. CI green on `develop`, including the Postgres and Redis jobs.
7. No `float` in money code, no hardcoded FX, no simulated payment UI left.

## 7. After Phase 10

Phases 11 (tutor lifecycle + payouts) and 12 (integrations + notifications) as two parallel streams, then 13.6 hosted staging (needs 8.9 and real env values), then 15 (screens, admin, SEO, tests), 14 (legal), 16 (UAT and launch). The longest human lead times are D-12, live PayPal Business / PayFast merchant approval (16.1) and counsel for the legal pages (14.1): start them now.

## 8. Risks

| Risk | Mitigation |
| :--- | :--- |
| The Redis race job failed on its first run and exposed a real lock bug (fixed, ERR-030); it must go green on real Redis before Phase 10 builds on it | Push the fix and read the next run; the other three jobs passed first time |
| Sandbox access slips | All new gateway code is built and tested against mocked HTTP; the live pass is a short final step |
| EUR / JPY unsettleable without an FX source | Rejected loudly (not silently valued); decision item 6 |
| Next.js 15/16 + React 19 breaks the BFF or middleware | Separate branch, full test + build gate, merge only when green |
| Local test run time | Now ~20 s; if it regresses, investigate before it hides regressions |
| Scope creep (subscriptions, trial lessons) | Out of MVP unless you say otherwise |
