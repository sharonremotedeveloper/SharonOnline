# Payouts, receipts and calendar hints: what is built, and what is needed from Anesu to go live

**Updated:** 2026-10-06 (Claude, Package A and its follow-ups, branch `feature/claude-financial-core`).
Design: `adr/ADR-0003-payout-batches.md`. Slice notes: `slices/P1.md`, `slices/T10_8.md`, `slices/G2.md`, `slices/T3b.md`.
Everything below the line "Needed from Anesu" is the only thing standing between this code and real money moving.

## 1. What is built and verified (no action needed)

| Area | Behaviour | Where |
| :--- | :--- | :--- |
| Receipts | one per successful payment, `INV-YYYYMM-XXXXX`, owner-only list + PDF; the student wallet lists them with a download button | `payments/services/receipts.py`, `components/student/ReceiptsList.tsx` |
| Payout runs | create -> approve (different admin) -> bank CSV (password re-entered, audited, formula-safe) -> mark paid (different admin) -> bank return reversal; one open line per tutor by DB constraint; bank fingerprint + balance re-checked | `payments/services/payout_batches.py`, `admin_api/payout_views.py`, `components/admin/PayoutRuns.tsx` |
| Bank-change code | creating or changing payout bank details needs a 6-digit code e-mailed to the tutor (10 min, 5 guesses, hashed, single use) and a mandatory "bank details changed" notice; payouts are held 72 h after a change | `payments/services/bank_change_code.py`, payout-settings page |
| Payout notices | `payout_paid`, `payout_returned` (mandatory `payment` category) via `notify()` | `notifications/builtin_kinds.py` |
| Statements (P2) | `GET /payments/wallet/tutor/statement/` CSV over ledger 2020 with a running balance; a button on the tutor wallet | `payments/services/statements.py` |
| Google busy hint | public listing only, fails open; a rescheduled lesson now updates the same calendar event (id kept) and recreates it only if the tutor deleted it | `integrations/google_calendar.py`, `bookings/services/fulfillment.py` |
| Material assets (T3b) | admin PDF/audio commit through quarantine | `materials/assets.py` |

The legacy `POST /admin/payouts/execute-batch/` still answers 503 on purpose; the admin page no longer offers the old client-side "ACB CSV" (it exported masked data) or the disabled execute button.

## 2. Needed from Anesu (in the order that unblocks the most)

| # | What I need | Why it blocks | My recommendation (so the answer can be "agree") |
| :-- | :--- | :--- | :--- |
| 1 | **D-3**: payout cadence, and the rail (manual bank EFT file vs Wise API vs PayPal Payouts) | the run is manual today; cadence decides whether I add a scheduler that *prepares* a run and e-mails admins | Bi-weekly; manual EFT CSV for the MVP (built); no automatic approval ever. Also confirm the provisional numbers: minimum payout **R100**, **72 h** hold after a bank change (`PAYOUT_MIN_ZAR`, `PAYOUT_BANK_CHANGE_HOLD_HOURS`) |
| 2 | **A second admin account** (a real second person: e.g. Sharon, or the accountant) and a yes/no on "platform owner may be the second approver" | the creator can never approve or mark paid, so with one admin a run can be made but never finished (by design; it is not a setting) | Create the second admin in Django admin with their own e-mail and password. Keep "owner as second approver" **off** |
| 3 | **D-13 (new): how money gets from PayPal / PayFast into the Sharon bank account, and who records it** | ledger account 1030 (bank) has no inflow, so the payout postings (CR 1030) drive the bank balance negative on the books; PayPal pays out USD/EUR/JPY and the ledger refuses a mixed-currency journal | Answer: (a) which bank account, (b) how often money is withdrawn from PayPal / PayFast, (c) does PayPal convert to ZAR itself or does the bank. Then I build an admin "record gateway withdrawal" form (DR 1030 / CR 1010 or 1020, rate and fee captured, FX difference to a new expense account). The accountant should confirm the FX-difference account (see D-12) |
| 4 | **D-12** (accountant + attorney): VAT registration status and rate, legal entity name and address for receipts, whether tutors are independent contractors and what tax document they get | `PLATFORM_VAT_RATE` is 0 and receipts print "VAT registration details to be confirmed"; tutor statements are a reconciliation CSV, not a tax certificate | Give me the rate, the VAT number, the legal name/address; I change one setting and the receipt wording. Statements stay as they are until the accountant names the tax document |
| 5 | **Production configuration** (secrets stay in the host, never in files): `PAYOUT_DATA_KEYS` + `PAYOUT_DATA_ACTIVE_KEY`, a live `RESEND_API_KEY` (the bank-change code is an e-mail), `PLATFORM_VAT_RATE`, the private R2 bucket | without a working e-mail provider no tutor can save bank details any more | Add them in the host's secret manager; I will run `manage.py check --deploy` after. I will not read or write secrets |
| 6 | **Google Cloud project** and OAuth credentials, plus one real tutor calendar for a live check | G2 and the event-preserving reschedule are tested against a fake of Google's API only | Create the project per `slices/G1.md`; tell me when the credentials are in staging and I run the live checklist (section 4) |
| 7 | **Go to merge**: say "merge Package A" and I run the full gate on `develop` and push (`gh` must be `sharonremotedeveloper`) | nothing is on `develop` yet | |

Nothing else in this list needs a decision from you; the remaining items are mine (section 3).

## 3. What I will do next without waiting (in order)

1. **When D-13 is answered:** gateway withdrawal recording (DR 1030 / CR 1010|1020), a reconciliation report "gateway cash vs bank cash", and the guard that a payout run warns when 1030 would go negative.
2. **When D-3 is answered:** a Celery task that *prepares* (never approves) a pending run on the agreed cadence and sends one `admin_alert`, plus the admin dashboard tile.
3. **Tutor payout history screen** (the wallet already lists payouts; add "returned" and the run reference) and a tutor-facing notice preferences page entry for the new kinds.
4. **Receipts:** an e-mailed receipt on payment (needs the PDF attachment decision, small) once VAT wording (row 4) is known.
5. **Admin UI polish** after you have used the run screen once: per-line "skip this tutor" and a downloadable run summary.

## 4. Go-live dry run (I run it in staging the day items 2, 3, 5 are done)

1. Two admins exist; two tutors with bank accounts saved through the e-mailed code; each earns a cleared balance of at least R100.
2. Admin A creates a run; confirm A cannot approve (403 `maker_checker_violation`); admin B approves.
3. B downloads the CSV with their password; confirm one audit row, `Cache-Control: no-store`, no formula cells, bank numbers match the tutors.
4. Change one tutor's bank details after approval: the next download must skip that line (`bank_details_changed`).
5. B marks the run paid: ledger shows one balanced DR 2020 / CR 1030 per tutor, tutor wallets drop to zero, both tutors receive the `payout_paid` e-mail.
6. Mark one line returned by the bank: balance returns, `payout_returned` e-mail arrives, the next run pays it again.
7. Download the tutor statement and tick the running balance against the wallet.
8. Student side: pay a lesson in sandbox, open the receipt PDF; check number and VAT line against the accountant's wording.
9. Calendar: connect one tutor calendar, add a personal event, confirm the slot disappears from the public listing but a booking on that time still works; reschedule a lesson and confirm the same event moves.

## 5. Not verified, said plainly

- The new screens (admin payout runs, receipts list, statement button, bank-change code field) compile, lint and build, and the API behind them is covered by tests, but I have **not** looked at them in a browser against a running backend with a logged-in session.
- Google and e-mail behaviour is verified against fakes only. PayPal/PayFast sandbox verification is unchanged and still pending.
