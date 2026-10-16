# Test bookings (no payment)

Status: **Implemented in code, covered by automated tests, intentionally disabled in production until the owner sets the variable below.**

## Two routes
1. **Non-production switch** `TEST_BOOKINGS_ENABLED` (defaults on when `PAYMENTS_ENABLED=false`). Production hard-sets it to False
   (`config/settings/production.py`) and it must stay that way.
2. **Production allowlist** `TEST_BOOKING_ALLOWED_EMAILS` (comma-separated, case-insensitive; default empty = off). With
   `PAYMENTS_ENABLED=false`, `POST /bookings/<id>/confirm-test/` confirms a held booking only if BOTH the student's and the tutor's
   e-mail are listed. Any other student or tutor gets 503. Payments enabled always wins (no allowlist then).

## What a test booking does and does not do
- Does: normal state transition to `confirmed` (audit reason `allowlisted test booking confirmed without payment`), slot lock, Daily room
  and notifications through the usual fulfilment path.
- Does not: create a payment, receipt, funding snapshot or ledger entry. Settlement of such a lesson stops with a missing-funding anomaly
  by design, so test bookings cannot reach payouts and cannot prove settlement. Settlement/refund acceptance needs a real or sandbox payment.

## Switching the production test window on (owner action, in order)
1. Railway production API: set `TEST_BOOKING_ALLOWED_EMAILS` to the student and tutor test e-mails (keep `PAYMENTS_ENABLED=false`).
2. Vercel Production: set `NEXT_PUBLIC_TEST_BOOKINGS_ENABLED=true` and redeploy (the button only renders when payments are off).
   While it is on, other signed-in students would see the button but the API refuses them.
3. Switch off: remove the Railway variable (and set the Vercel flag back to `false`).
