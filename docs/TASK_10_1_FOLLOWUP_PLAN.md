# Task 10.1 follow-up plan - closing the four "not done" items

**Created:** 2026-10-03 · **Parent:** `PHASE_10_EXECUTION_PLAN.md`, Task 10.1 (done on `feature/10-1-price-catalog`) · **Rule:** failing test first, mutation check on load-bearing lines, full suites, docs + ERR log, one commit per slice.

| Slice | Item | Needs Anesu? | Branch |
| :--- | :--- | :--- | :--- |
| A | Floats out of money code (admin telemetry, trial balance, booking price fields) | No | `feature/10-1a-no-float-money` |
| B | Ledger: remove the 18.75 default | No (needs CI Postgres run before merge) | `feature/10-1b-ledger-required-fx` |
| C | Frontend reads the price API (currency lib, pricing, checkout) | Confirm provisional prices | `feature/10-1c-frontend-prices` |
| D | EUR / JPY lesson checkout (PayPal) | **FX source decision** (blocked) | not started |

Merge order: A -> B -> C. D waits for the FX decision and for 10.2 (PayPal Orders).

## Slice A - remove `float()` from money paths
Scope (about 33 sites): `admin_api/views.py` (gmv, escrow, payout amounts, `round()` on floats), `ledger_service.py` trial balance / financial summary, `bookings/serializers.py` (`price_usd`/`price_zar`), `admin_api/serializers.py`, `teachers/views.py` price filter (`float(max_price)`).
1. Money leaves the API as **exact strings** (as `lesson-prices` and credit packs already do), via a small helper using `quantize_money`.
2. Tests first with values floats corrupt (sums, 3-way splits, large GMV) for telemetry, escrow view, trial balance, payout batch.
3. `Decimal` end to end; aggregate with `Sum`, serialize once. Teacher filter parses `max_price` with `Decimal`, 400 on garbage.
4. Contract change: regenerate OpenAPI + `api.generated.ts`; update the admin pages and the checkout page that read these fields.
5. Guard test: fails the build on `float(` in money modules, with an explicit allow-list for non-money use (ratings).
Acceptance: no `float(` in `payments/`, `admin_api/`, `bookings/serializers.py` outside the allow-list; suites green.

## Slice B - remove the ledger's 18.75 default
Current: `DEFAULT_FX_USD_TO_ZAR` is a default on `record_journal_entries` and 5 wrappers, a model default on `LedgerEntry.fx_rate_to_zar`, and a `legacy_default` fx_source fallback.
1. Inventory callers (`ledger_service`, `credits.py`, `refunds.py`, `settlement.py`, `webhook_handler.py`, `tasks.py`); those omitting FX are the real exposure.
2. `fx_rate_to_zar` / `fx_source` become required; absence raises `MissingLedgerFx` rather than valuing at an invented rate. ZAR journals pass `1` / `transaction_currency`.
3. FX comes only from stored snapshots (`PaymentTransaction`, `BookingFunding`, `CreditPurchase`) or `usd_to_zar_rate()` (`price_catalog`).
4. Tests first: no-FX call raises; every flow still posts balanced entries; `test_ledger_journal.py` asserts the captured rate, not 168.75.
5. Schema-only migration drops the model default (rows are immutable and untouched). `legacy_default` stays a historical value; a test forbids new rows with it.
6. Delete the constant. Mutation check: reintroduce a default and confirm failure.
Risk: immutable-ledger path; the Postgres trigger test (never run yet) must pass in CI before merge.

## Slice C - frontend reads the price API
1. New `lib/prices.ts` (added to `tsconfig.test.json`): types and `formatMoney(amountString, currency, decimals)` with `Intl.NumberFormat`; no `Math.round`; unit-tested (JPY 0 decimals, EUR 2, large values).
2. `lib/currency.ts`: drop hardcoded `DEFAULT_BUNDLES` and rounding; read `getLessonPrices()` / `getCreditPacks()`; keep symbols/flags/labels as presentation.
3. `PricingTable`, `CurrencySwitcher`, wallet page use `useApiData` with real loading/error/empty states, no fabricated fallback.
4. Checkout shows the amount returned by `checkout/init` in the gateway currency; remove `price_usd` / `~R{Math.round(price_zar)}`.
5. Tutor pages show the platform price instead of `price_per_25min_usd`. Dropping that column is deferred to Phase 11; stop exposing it in the public serializer.
Acceptance: no price literal in `frontend/src` outside tests; `npm test`, lint, build green.

## Slice D - EUR / JPY lesson checkout (blocked)
Needs decision: FX source. Recommendation: an admin-maintained `FxRate` model (currency, rate_to_zar, source, valid_from, set_by) with a stale-after-24h warning; a provider feed later behind the same model.
After the decision and 10.2: `gateway_fx_snapshot` uses `FxRate` for EUR/JPY; PayPal booking checkout accepts USD/EUR/JPY priced from `lesson_price()`; PayPal JPY amounts sent with 0 decimals; webhook amount checks use `quantize_money`; EUR/JPY rows added to the multi-currency trial-balance tests (also 10.10).

## Decisions needed from Anesu
1. Confirm provisional prices (USD 9.00, EUR 8.50, ZAR 162.00, JPY 1350).
2. FX source for EUR/JPY.
3. Stop exposing the tutor price field now and drop the column in Phase 11?
