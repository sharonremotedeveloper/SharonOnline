# Slot holds and in-flight payments (Task 9.4)

A `pending_payment` booking *holds* its slot. `apps/bookings/services/holds.py` is the single definition of how long, shared by the purge job, reservation, checkout and the booking API (`lock_expires_at`).

| Rule | Value | Setting |
| :--- | :--- | :--- |
| Base hold (= Redis lock TTL) | `created_at + 10 min` | `LOCK_DURATION_SECONDS` (code constant) |
| Payment in flight (an `INITIALIZED` PaymentTransaction younger than the grace period) extends the hold to `tx.created_at + grace` | 15 min | `PAYMENT_INFLIGHT_GRACE_SECONDS` |
| Hard cap, however many attempts | `created_at + 30 min` | `PAYMENT_HOLD_MAX_SECONDS` |

`live_hold_q(now)` is the queryset form; the purge job cancels exactly `status=pending_payment AND NOT live_hold_q(now)`, so "purgeable" and "no longer holds the slot" can never drift apart.

## What changed

* **Purge** no longer cancels a booking whose customer is mid-payment. It also skips rows locked by a payment webhook (`skip_locked`), and cancels once the attempt is stale, failed, or the hard cap passes.
* **Checkout init** now refuses (409) when: the hold has lapsed; another booking already owns the slot; the Redis lock was lost to another student. Otherwise it re-takes/extends the Redis lock for the grace period. It returns `hold_expires_at` so the UI timer can follow the extension. *We never start collecting money for a booking we can no longer honour.*
* **Reserve** also asks the database whether another student has a live hold (or owns) the same slot, because the Redis lock alone can lapse while their payment is still running.
* **API** `lock_expires_at` (booking detail / reservation) uses the same function, so the timer matches server behaviour.

## Late payments (hold already lapsed and purged)

Unchanged and now explicitly tested: a capture that lands after the purge **re-confirms** the booking (`cancelled -> confirmed`, audited) when the slot is still free; if someone else took the slot it is **quarantined** (`-> disputed`, DEF-501, student made whole with a credit + dispute case + ledger entries).

## Known limits / follow-ups

* Slot *display* (`slot_generator`) still relies on the Redis lock for held slots; Task 9.3 makes it treat live DB holds as busy too (reserve already enforces it).
* Frontend checkout timer is computed once from `lock_expires_at`; when Phase 10 wires `POST /payments/checkout/init/` it must reset the timer from the response's `hold_expires_at`, and show the 409 messages.
* A gateway that leaves a payment pending for hours (e.g. e-check) outlives the 15-minute grace; those arrive through the late-payment path above.
* PayFast `CANCELLED/FAILED` ITNs are acknowledged without marking the transaction `FAILED`; the hold simply lapses with the grace period (Task 10.x can tighten this).
