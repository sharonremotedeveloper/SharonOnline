# Lesson reviews (Task 9.10)

One implementation: `bookings/services/reviews.py::submit_review()`, behind one view class `SubmitReviewView`.

| URL | Status |
| :--- | :--- |
| `POST /api/v1/student/bookings/<id>/review/` | canonical (what the web app calls) |
| `POST /api/v1/bookings/<id>/review/` | deprecated alias (`LegacySubmitReviewView`, same behaviour); accepts the old `review` field as `private_notes` |

Request: `{rating: 1-5, tags?: [rubric tags], private_notes?: <= 2000 chars}`. Response `200 {success, status: "review_recorded", message}`.

## Rules (all enforced server-side, all tested in `tests/test_review_endpoint.py`)

* Only a **student**, only for **their own** lesson (someone else's lesson is a 404; tutors/admins get 403).
* Only lessons that **took place**: `completed_pending_memo`, `completed`, `completed_memo_forfeited`. Anything else is a 409.
* **One review per lesson**, whichever URL is used; a second attempt is a 409 and changes nothing (reviews were silently overwritable before, which let a rating be changed at will).
* Tags must come from the rubric (`REVIEW_TAGS`, mirrors `RUBRIC_TAGS` in `ReviewRubricModal.tsx` - change both together); duplicates collapse; max 8.
* The tutor's public `rating_avg` / `rating_count` are recomputed with a DB `Avg`/`Count` while holding the tutor-row lock, and **only those two columns are written** (the old code saved the whole tutor row from a stale copy, which could undo a concurrent deactivation or SLA strike, and averaged in Python).
* Throttled: 30 reviews/hour per user.

## Privacy (asymmetric-feedback invariant)

* `Booking.student_review` (the written text) is **staff-only**: `BookingDetailSerializer` removes it for everyone else, including the tutor it is about, and the field is read-only in that serializer. Before this task the tutor received it on `GET /bookings/<id>/`.
* The student's own lesson archive returns only `rating`, the tags they chose and the submission time - never the text, and no invented tags (the archive used to return a fixed `["Clear Pronunciation", "Great Corrections", "Patience"]` for every rated lesson).
* In the Django admin the review fields (`student_rating`, `student_review`, `student_review_tags`, `reviewed_at`) are read-only: reviews are evidence, not editable data.
* The tutor still sees the rating on the booking (as before) and the public average; they do not see tags or text.

## Open / follow-ups

* There is no admin API/UI for reading review text yet (Django admin only). Add one with the Phase 15 admin screens (moderation, tutor-quality reporting).
* Whether tutors should see per-lesson star ratings at all is a product decision for Anesu; today they can (unchanged).
* The student archive still returns a few placeholder defaults for lessons without a material (`material_cefr` "B2", `material_slug` "freetalk-discussion"); the UI links to that slug. Fix with the Phase 15 student-screens pass.
