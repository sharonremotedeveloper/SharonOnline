# Booking list and filters (Task 9.5)

`GET /api/v1/bookings/` - "my lessons". Logic lives in `bookings/services/listing.py`; the view only wires it up.

## Scope (applied first; filters can only narrow it)

| Caller | Sees |
| :--- | :--- |
| Student (and any non-tutor) | lessons they booked |
| Tutor with a profile | lessons they teach |
| Tutor account without a profile | nothing (it used to fall back to "lessons I booked as a student") |

There is no `student=` / `teacher=` parameter: nobody can ask for someone else's list. Admin lesson search belongs to the admin API (Phase 15).

## Query parameters (all optional; bad values are a 400 naming the field)

| Param | Meaning |
| :--- | :--- |
| `status` | one or more statuses, comma-separated or repeated (`?status=completed,cancelled`) |
| `when=upcoming` | not yet ended, and not cancelled; an unpaid `pending_payment` booking only while its hold is live (`holds.live_hold_q`) |
| `when=past` | already ended (any status, so a "confirmed" lesson nobody settled yet shows here too) |
| `from`, `to` | on `start_time_utc`, both ends inclusive. A date (`2026-10-05`) means the whole UTC day; a date-time is taken as given, naive = UTC |
| `ordering` | `start_time_utc` or `-start_time_utc` only. Default: soonest first for `when=upcoming`, newest first otherwise |
| `page`, `page_size` | 20 per page by default, `page_size` capped at 100 (larger values are clamped, not rejected) |

Response is the standard DRF page `{count, next, previous, results}`; `next` keeps the filters.

## Frontend

`lib/bookings.ts::listBookings(params)` builds the query and returns `{items, count, hasMore}`. The tutor dashboard now asks for upcoming lessons, pending memos and this month's completed count as three filtered queries; the "counted from your most recent bookings only" caveat is gone because the server counts. The student schedule page (Phase 15) should use the same helper.

## Follow-ups

* Past lessons that ended while still `confirmed` are settled by the attendance job (Task 9.8 improves attendance mapping).
* No free-text search or tutor/material filter yet; add when the schedule screens need them.
