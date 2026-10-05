# ADR-0003: Payout batches (design only, NOT approved to build)

**Status:** PROPOSED 2026-10-05 (Claude). **Build only after Anesu's explicit go** (plan section 9 item 2: a deliberate exception to
"payout execution waits on D-3"). Related: `PHASE_11_12_EXECUTION_PLAN.md` section 3.8, `SETTLEMENT_PATHS.md` (`PAYOUT_EXECUTED`),
`REMEDIATION_INTEGRATION.md` follow-up 1 (bank-change OTP), decisions D-3 (cadence / rail), D-12 (tax).

## Context
Cleared tutor earnings sit in ledger account 2020 (tutor payable). `admin_api.PayoutBatch` exists but is unused and
`ExecutePayoutBatchView` answers 503. Paying tutors is the one place where a bug moves real money out of the platform, so the
design makes the dangerous mistakes (paying twice, self-approval, leaking bank details, unmatched ledger) structurally hard.

## Decision (what we would build)
1. **Additive model.** Extend `PayoutBatch`; add `PayoutBatchLine` (one per tutor) and an immutable `PayoutAttempt`. Statuses
   `pending -> approved -> exported -> processed` (+ `cancelled` only before export). A bank return after processing is a line
   transition `paid -> returned` with a new ledger event and a **reversing** entry (ledger rows stay immutable).
2. **No double pay, by the database.** `PayoutBatchLine.is_open` plus a partial `UniqueConstraint(teacher, condition=is_open)`:
   a tutor can be in at most one open batch. Available balance = ledger balance (2020) minus open lines, computed under a lock on
   the tutor and re-checked at approve and at processed. `PAYOUT_MIN_ZAR` (provisional 100) carries small balances over.
3. **Real two-person control.** `approve` and `mark_processed` need actors different from the creator and from each other where
   possible. With one admin the system **refuses** (payouts stay blocked until a second admin exists or a TOTP step-up with a
   delay window is built). It is not a setting: "platform owner as second approver" is off and needs Anesu's explicit approval.
4. **Bank data.** The CSV export is the **only** decrypt path (a guard test fails if another module imports the decryptor); admin
   plus fresh re-auth, `Cache-Control: no-store`, formula-injection sanitising (`= + - @`), one audit row per download, never
   logged. The line snapshots the bank account and is **re-compared with the live account** at approve and export; a 72 h hold
   follows any bank-details change (and the bank-change OTP is a precondition, REMEDIATION follow-up 1). An account that cannot be
   decrypted becomes a visible *skipped line with a reason*, not a silent drop.
5. **Ledger.** One outer `transaction.atomic()`, one journal per line (DR 2020 / CR 1030, ZAR, user = the tutor), batch selected
   `for update`, `mark_processed` a no-op when already processed, DB backstop unique `(payout_batch, user, account, event_type)`.
   Payout = sum of the line amount snapshots. A suspended or removed tutor is still paid what they earned (never `bookable()`).
6. **Statements (P2)** are a CSV over the same lines; PDFs wait for the PDF tooling and tax wording (D-12).

## Consequences / open items
- Needs Anesu: the go; D-3 (cadence, rail: manual EFT CSV vs Wise); a second admin account; the tax identity question (D-12).
- Gap G2 stays: account 1030 has no inflow from gateway cash (documented, not solved by this ADR).
- Implementation slices: P1a (model + state machine), P1b (CSV + audit + guards), P1c (ledger posting), P2 (statements), each with
  Postgres-marked tests for the open-line constraint, the lock and the migration; mutation tables as for every money line.
