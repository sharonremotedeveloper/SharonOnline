# Phases 11 and 12 - Execution plan (tutor lifecycle + integrations/notifications), decision-free scope

**Created:** 2026-10-04 · **Author:** Claude (lead architect) · **Parents:** `PRODUCTION_READINESS_PLAN.md` Phases 11-12, `PHASE_10_EXECUTION_PLAN.md` §3 #7-8 · **Status:** DRAFT for review (logic review, docs-alignment review, QA review), then Anesu's approval. Nothing here is built yet.

Goal: finish everything in Phases 11 and 12 that does **not** wait on an open decision, on mocked HTTP, so that when Anesu answers D-3/D-4/D-8/D-9/D-10/D-11/D-12 only thin, well-isolated pieces remain. Rule from `PHASE_10_EXECUTION_PLAN.md` §4: where a decision is open we proceed on the recommended default **only when the work is reversible and isolated**, and mark it PROVISIONAL; we never encode an unconfirmed money-policy change.

## 1. Classification (from the docs-alignment audit)

| Task | State today | Class | What is built now | What waits |
| :--- | :--- | :--- | :--- | :--- |
| 11.1 profile at signup + `/teachers/me/` | absent (registration creates no `TeacherProfile`; tutors get 403 everywhere) | DECISION-FREE | all | - |
| 11.3 upload commit | absent (presign works, nothing records/validates the key) | DECISION-FREE | all | Cloudflare Stream video (gap G1, separate) |
| 11.4 vetting workflow | minimal boolean approve/reject, reason discarded, no audit, no e-mail | PARTLY | status enum, rubric, reason storage, audit rows, suspend/reactivate, admin screens | e-mail content (needs 12.2), training gate term (11.5), sign-off beyond one admin (D-11) |
| 11.2 application funnel | absent | PARTLY | funnel + server-side draft + uploads on the D-11 default (TEFL + SA ID + intro media) | final mandatory-document list, interview stage |
| 11.5 training hub | absent | DECISION-FREE for infrastructure | models, progress, gate predicate | real module content (Sharon supplies) |
| 11.6 availability CRUD | create/list only; UI save is broken | DECISION-FREE | all (min-notice / horizon as provisional settings) | - |
| 11.8 payout batches | read-only preview, execution disabled (503), `PayoutBatch` model unused | PARTLY | persisted batch + lines, state machine, CSV behind a bank-format interface, ledger posting on PROCESSED, idempotency | **D-3**: cadence, rail (Wise has no account), maker-checker rule; gap G2/G3 (gateway-to-bank cash, currency/FX/threshold) |
| 11.9 statements | absent | PARTLY | CSV/PDF of lessons, commission, net | tax wording / SARS format (D-12, D-11); needs 11.8 |
| 11.10 memo SLA | reminder only logs; forfeiture still pays the tutor 80 %; DEC D-4 text is contradictory | **BLOCKED on D-4 meaning** | only non-policy fixes: send the 12 h reminder e-mail, per-row failure isolation | whether a late memo forfeits pay (a money-policy change: not built without Anesu) |
| 11.11 teacher frontend on real data | wallet/payout settings real; profile static, schedule save broken, mock fallbacks remain | DECISION-FREE | after 11.1 and 11.6 | - |
| 12.1 Zoom hardening | `create_meeting` no longer returns None; but fake meetings when unconfigured, **a failed OAuth returns "" and then fabricates a mock meeting even in production**, token not cached, no 429/5xx handling | PARTLY | production guard, no-mock-in-prod, token cache, backoff, surfaced errors, `HostPicker` abstraction | host allocation (D-9) |
| 12.2 notification system | email transport exists; **no Notification model, no in-app, no preferences; T-24h/T-1h/T-10m only flip flags; late alert, memo warning, apology credit, tutor booking mail are log-only or absent** | PARTLY | model, dispatcher, preferences, templates + escaping, retry, all events except memo/apology wording | memo/apology wording (D-4), real domain (D-10) |
| 12.3 Resend | prod refuses `re_dev` at boot; no delivery webhook; two sender code paths | PARTLY | delivery webhook, bounce suppression, unified sender | SPF/DKIM and domain (D-10, DNS by Anesu) |
| 12.4 Google Calendar | outbound push only, token plain JSON on `User`, never refreshed, errors swallowed, reconcile is a stub | DECISION-FREE (live check needs Google credentials) | OAuth, encrypted storage, refresh, freebusy, slot-generator honours busy | Google Cloud project (client provides) |
| 12.5 Eskom | done by Codex | policy item blocked | migrate its notifications to `notify()` | outage windows in public slot projection (product approval) |
| 12.6 Zoom join frontend | absent (`joinUrl` ignored, `window.confirm`, fake latency) | DECISION-FREE (deep link default per SOW 3) | all | - |
| 12.7 notification centre | absent | DECISION-FREE | all, after 12.2 contract | - |
| 12.9 purges | absent | PARTLY | 90-day telemetry purge | recording purge (D-8 recommends no recording) |
| 11.7, 12.5 core, 12.8 | done | - | reuse, do not rebuild | - |

Out of scope until answered: **11.10 policy** (D-4), **11.8 execution/rail/cadence scheduling** (D-3, G2, G3), **12.1 host allocation** (D-9), **12.3 domain verification** (D-10), **12.9 recording purge** (D-8), **11.9 tax content** (D-12).

## 2. Design decisions (architect proposals; the reviewers attack these)

### 2.1 Tutor status machine and the single bookable predicate (11.1 + 11.4)
Today status is two booleans (`is_verified`, `is_active`) with "rejected" inferred as both false. Six call sites filter on them (public list/detail, slots/reserve, reservation, rescheduling, checkout) plus strikes auto-deactivation and the admin serializer.
- `TeacherProfile.status` enum: `applied` (registered, funnel incomplete) -> `submitted` -> `in_review` -> `approved` | `changes_requested` (back to `submitted` on resubmit) | `rejected`; `approved` <-> `suspended`. `training_completed_at` (nullable) is separate from status.
- **One writer**: `teachers/services/vetting.py::transition_teacher(teacher, to, *, actor, reason='', rubric=None)`: row lock, allowed-transition map (mirrors `bookings/services/state_machine.py`), writes an immutable `TeacherStatusChange` audit row, keeps the legacy columns in sync (`is_verified = status in (approved, suspended)`? **No**: `is_verified` = vetted (approved or suspended), `is_active` = bookable switch: `status == approved and not strikes-deactivated`), and calls the notification hook. Nothing else may assign `status`, `is_verified` or `is_active` (a test fails the build if a view or task does, like the booking-status guard).
- `TeacherProfile.is_bookable` property and `TeacherProfile.objects.bookable()` queryset (`is_verified and is_active and training_ok`, where `training_ok` is true when `settings.TUTOR_TRAINING_GATE_ENABLED` is false or `training_completed_at` is set). **All six call sites use it**; strikes call `transition_teacher(..., 'suspended', reason='strikes')`.
- Data migration: `is_verified and is_active -> approved`; `not is_verified and not is_active -> rejected`; `not is_verified and is_active -> applied`; `is_verified and not is_active -> suspended`.
- Suspending a tutor with confirmed future lessons: the transition returns the affected bookings and the **admin chooses** (cancel through the existing tutor-cancel path with refund + credit, or leave); never silent. (Reuse `bookings/services/cancellation.py`.)
- `price_per_25min_usd`: stop exposing it (D-1/10.1); deprecate the field now, drop in a later migration.

### 2.2 Notifications foundation (12.2/12.7/12.3)
New app `apps/notifications` (keeps `integrations` clean):
- `Notification(id, user FK, kind, title, body, payload JSON, booking FK null, idempotency_key UNIQUE, created_at, read_at null, email_state pending|sent|retryable|skipped|bounced, email_attempts, email_last_error (staff only), email_sent_at, provider_message_id)`; index `(user, read_at, -created_at)`.
- `NotificationPreference(user 1:1, email_by_kind JSON, in_app_by_kind JSON)`; **mandatory kinds cannot be turned off** (security, payment, cancellation, refund).
- Single entry `notify(user, kind, *, key, payload, booking=None)`: `get_or_create` on the key, then `transaction.on_commit(deliver_notification_task.delay)`. Delivery task: compare-and-swap claim of `email_state`, template registry per kind with `escape()` on every interpolated field, **recipient-timezone rendering**, `send_email(..., idempotency_key=key)` (Resend supports an Idempotency-Key header) returning the provider message id, retry with jitter and a cap, bounded sweep per run.
- `integrations/email.py::send_email` is unified: returns the provider id, accepts `attachments`, never silently mocks in non-DEBUG production (`ERROR` log; the boot guard remains), maps 4xx/5xx/429/timeout to `EmailDeliveryError`. `send_booking_confirmation_email` becomes a thin caller (its second `requests.post` path and the HTML-unescaped names go away).
- **Fulfilment must stop masking failures** (`integrations/tasks.py` marks `calendar_completed`/`email_completed` True when the calendar returns "" or the email returns False): fixed in the same wave.
- Existing durable outboxes (`EskomNotificationAttempt`, `SupportInquiry.delivery_state`) stay until a later slice wraps them in `notify()`; refund/payment-failure emails already use `cache.add` dedupe and are wrapped, not rewritten.
- API (IsAuthenticated, owner-only): `GET /notifications/?unread=1&cursor=`, `GET /notifications/unread-count/`, `POST /notifications/<id>/read/`, `POST /notifications/read-all/`, `GET|PATCH /notifications/preferences/`; user throttle; `email_last_error` never returned to non-staff.
- Event inventory (recipient, hook, idempotency key) is §4; existing `Booking.reminder_*_sent`, `tutor_late_alert_sent`, `memo_reminder_sent` flags **stay** (tests assert them) but are now set **after** a successful `notify`, or replaced by the notification key as the dedupe (flag kept in sync).

### 2.3 Zoom hardening (12.1a)
- `ZOOM_ACCOUNT_ID/CLIENT_ID/CLIENT_SECRET` become settings and are **required by the production boot guard** (today only the webhook secret is).
- No mock path unless `DEBUG` or an explicit `ZOOM_MOCK=1` in non-production; a failed OAuth **raises** `ZoomError` (the root-cause bug: it returned "" and then fell into the mock branch).
- Token cached in the Django cache for `expires_in - 60 s`, single-flight via `cache.add` lock, invalidated on a 401; 429 honours `Retry-After`; 5xx bounded retries with jitter; a probe that sees `error` is **not** treated as "no-show" (the attendance probe in `bookings/tasks.py` must distinguish "Zoom said waiting/ended" from "Zoom unreachable").
- `HostPicker` interface (`pick_host(booking) -> host_user_id`, default returns `'me'`) so D-9 is a one-class change; the chosen host id is stored on the booking (`zoom_host_user_id`, nullable) so attendance classification can use it later.

### 2.4 Google Calendar (12.4)
- `CalendarCredential(user 1:1, refresh_token_enc, scopes, connected_at, revoked_at, last_error)` encrypted with the existing versioned keyring pattern (`payments/services/payout_crypto.py`); data migration moves the plain `User.google_calendar_token` and the admin stops showing it.
- Endpoints (tutor only): `GET /integrations/google/connect/` (signed `state` bound to the user and expiring), `GET /integrations/google/callback/`, `DELETE /integrations/google/`. Scopes `calendar.events` + `calendar.freebusy` only. A refresh failure (`invalid_grant`) marks the credential revoked, stops pushes and **notifies the tutor**; it never retries forever.
- `reconcile_teacher_gcal_task` calls freebusy and caches busy spans (TTL 30 min); the slot generator **hides** overlapping slots but the DB uniqueness constraint stays the authority (busy data is a hint, never a booking decision). Event update (not delete+recreate) on reschedule.

### 2.5 Availability (11.6)
`PATCH|DELETE /teachers/availability/manage/<id>/`, `PUT /teachers/availability/replace/` (atomic weekly matrix: fixes the frontend contract), `TeacherTimeOff` (start/end UTC, reason), validators (`end > start`, `day_of_week` 0-6, no overlap within a day), settings `TUTOR_MIN_NOTICE_MINUTES` (replaces the hard-coded 10) and `BOOKING_HORIZON_DAYS` (14). Existing overlapping rows are tolerated by the migration (reported, not failed). Editing availability **never** cancels existing bookings. Unknown timezone no longer silently falls back to Johannesburg: it is rejected at profile save.

### 2.6 Upload commit (11.3)
`POST /teachers/me/assets/commit/ {kind, key}`: caller's prefix check, `head_object` (size, content-type) against `common/upload_policy.py`, magic-byte sniff (ranged GET of the first bytes), then record the key (private TEFL/ID keys go to the private storage field, never a public URL), delete the replaced object, fail **closed** when R2 is not configured (the fake `/api/v1/upload/<key>` URL is removed in production). TOCTOU: the committed object is **copied to a final key** and the presigned key discarded, so the tutor cannot overwrite an approved asset through a still-valid presign.

### 2.7 Retention (12.9a)
`apps/integrations/retention.py::purge_old_telemetry_task` (daily, queue `scheduler_beat`, `@distributed_task_lock`, batches): clears `AttendanceAudit.raw_payload` and webhook event rows older than `TELEMETRY_RETENTION_DAYS` (90) **except** bookings that are `DISPUTED` or have an unresolved `DisputeCase` (and keeps verdict columns: classification, join/leave times). Registered in `celery_schedule.py` by the notification owner (one editor of that file per wave).

### 2.8 Payout batches (11.8, PROVISIONAL on D-3 defaults, wave 3, needs Anesu's go)
`PayoutBatch` (reference unique, period, status `pending -> approved -> exported -> processed | cancelled`, `created_by`, `approved_by`, Decimal totals) + `PayoutBatchLine` (teacher, `amount_zar` Decimal, bank snapshot ciphertext + last4, status `pending|paid|failed`, ledger journal ref, **unique (teacher, batch)** and a guard that a teacher's cleared balance cannot sit in two open batches). Maker-checker: `approved_by != created_by`; the platform owner can act as second approver until staff exist (setting). CSV export is the **only** decrypt path, admin-only, audited (`PayoutAttempt`/audit row per download). Ledger: posting only on `mark_processed` (DR 2020 / CR 1030 per line inside one transaction, immutable; failed lines are reversed by reversing entries, never edited). Payout = the sum of the `amount_zar` snapshots in ZAR, minimum payout threshold as a setting. Payout preview stops filtering on `is_verified` (a suspended tutor must still get paid what they earned).

## 3. Slices, waves, parallelism

Each slice = one branch `feature/<id>`, one agent in its own worktree, **tests first**, mutation checks on load-bearing lines, own migration numbered at merge time (linearised per app), docs + ERR log + roadmap, commits ending with the Co-Authored-By line, no push. Slice reviews: QA agent on every slice; Architect on money/security slices (T1, T3, T4, G1, P1).

**Wave 0 (disjoint files, run in parallel):**
- **T1** status machine + auto profile + `/teachers/me/` + `is_bookable` refactor of the six call sites + data migration (11.1). Files: `teachers/*`, `users/serializers.py`, admin serializer fake-data removal, strikes hook. *Everything in the tutor stream depends on it.*
- **N1** notifications foundation + unified `send_email` + fulfilment-masking fix (12.2a). Files: `apps/notifications/*`, `integrations/email.py`, `integrations/tasks.py` (fulfilment only), `config/settings/base.py` (apps, task routes), `config/urls.py`.
- **Z1** Zoom hardening (12.1a). Files: `integrations/zoom.py`, `config/settings/{base,guard}.py`, `bookings/tasks.py` (probe semantics only), `tests/test_zoom_client.py`.

**Wave 1 (after T1 / N1 merge; parallel where files are disjoint):**
- **T2** availability CRUD + time-off + horizon/notice (11.6): `teachers/*` (new modules), `slot_generator.py`.
- **T3** upload commit (11.3): `common/*`, new `teachers/asset_views.py`.
- **T4** vetting workflow + audit + admin screens + rubric (11.4): `teachers/services/vetting.py`, `admin_api/*` new modules, FE admin vetting. E-mails via `notify` (N1).
- **N2** event wiring (12.2b): split by file - N2a `bookings/tasks.py` (reminders, late, no-show, memo 12 h *reminder only*), N2b `integrations/tasks.py` + cancellation/rescheduling (+ tutor booking notification), N2c `teachers/strikes.py` + vetting outcome hook.
- **N3** Resend delivery webhook + bounce suppression (12.3).
- **G1** Google OAuth + encrypted credentials + refresh (12.4a).
- **R1** telemetry purge (12.9a).
- **F1** Zoom join frontend (12.6). **F2** notification centre frontend (12.7, after the N1 API contract is frozen and `api.generated.ts` regenerated).

**Wave 2:** **T5** application funnel (11.2, after T3 + T4), **T6** training hub infrastructure (11.5), **T7** teacher frontend on real data + removal of mock fallbacks (11.11, after T1 + T2 + T4), **G2** freebusy + slot-generator busy handling + event update (12.4b), **N4** Eskom/support/refund notifications wrapped in `notify()` (12.5 cleanup), **11.10-lite** (12 h memo reminder e-mail through `notify`, per-row failure isolation in the memo/forfeiture sweeps; **no pay-policy change**).

**Wave 3 (needs Anesu's confirmation of the D-3 defaults):** **P1** payout batches (11.8, Architect + QA review mandatory), **P2** statements/payslips (11.9, CSV first, PDF after a dependency decision).

Conflict hotspots and rules: `teachers/{models,views,urls,serializers}.py` (T1 owns; others add new modules and only append routes), `admin_api/*` (T4 and P1 add new modules, append routes), `config/celery_schedule.py` and `config/settings/base.py` (one owner per wave, others send a patch to the owner), migrations (linearised at merge), `lib/api.ts` (frontend slices append). OpenAPI/TS regeneration after every API-changing merge: `manage.py spectacular --file ../docs/api/openapi.yaml`, `npm run gen:api`, `npm run check:api-types`.

## 4. Notification event inventory (recipient / channel / hook / idempotency key)

| Event | Recipient | Channel | Hook | Key |
| :--- | :--- | :--- | :--- | :--- |
| Booking confirmed | student, tutor | e-mail + in-app | `dispatch_booking_fulfillment` (tutor mail is new) | `booking-confirmed:{bid}:{role}` |
| Cancelled | other party | e-mail + in-app | `send_cancellation_emails` | `booking-cancelled:{bid}:{uid}` |
| Rescheduled | both | e-mail + in-app | `rescheduling.py` | `booking-rescheduled:{bid}:{new_start}:{role}` |
| Reminder T-24h / T-1h / T-10m | student (+tutor for 1 h, 10 m) | e-mail (+in-app) | `bookings/tasks.py` reminders | `reminder:{tier}:{bid}:{role}` |
| Tutor late (T+5 m) | student + admin | in-app + admin mail | `bookings/tasks.py` | `tutor-late:{bid}` |
| Tutor no-show + restitution | student, tutor (strike) | e-mail + in-app | `bookings/tasks.py` | `teacher-no-show:{bid}:{role}` |
| Student no-show | tutor, student | in-app | `bookings/tasks.py` | `student-no-show:{bid}:{role}` |
| Memo due (12 h) | tutor | e-mail + in-app | `bookings/tasks.py` | `memo-warn:{bid}` |
| Memo forfeited / apology credit | tutor, student | **wording waits for D-4** | - | `memo-forfeit:{bid}:{role}` |
| Strike / deactivation | tutor, admin | e-mail + in-app | `teachers/strikes.py` -> `transition_teacher` | `strike:{tid}:{bid}`, `suspended:{tid}:{change_id}` |
| Refund processed | student | e-mail + in-app | `send_refund_processed_email_task` (wrapped, keeps `cache.add`) | `refund-processed:{rid}` |
| Vetting approved / changes requested / rejected | tutor | e-mail + in-app | `transition_teacher` | `vetting:{tid}:{change_id}` |
| Credit granted / expiring (T-3 d) | student | e-mail + in-app | `grant_credit`; expiring needs a new job | `credit-granted:{lot}`, `credit-expiring:{lot}:3d` |
| Eskom shield | tutor + student | e-mail + in-app | existing durable task (wrap later) | `eskom-shield:{bid}:{uid}:{window}` |
| Bank details changed | tutor | e-mail (mandatory) | payout settings view | `bank-changed:{uid}:{ts}` |
| Calendar disconnected | tutor | e-mail + in-app | Google refresh failure | `gcal-revoked:{uid}:{ts}` |
| Admin money alerts | admin | e-mail | `alerts.py` (unchanged) | `GatewayAnomaly (code,key)` |

## 5. Engineering standards (apply to every slice)

TDD (red first), mutation checks on every authorization, state-transition and idempotency line, tables of mutants reported; no `float` in money code (guard test); no secrets, tokens, emails or exception text in logs (ids and error types only); every new endpoint typed in OpenAPI (no `OpenApiTypes.OBJECT`); every new list endpoint paginated; every state change through one service with a row lock and an audit row; every async side effect idempotent with a durable key; migrations additive, nullable or defaulted, reversible, safe on Postgres; PII/documents only in the private vault; frontend: real loading/error/empty states, no fabricated data, accessible components, tests for pure helpers (Vitest is blocked: Node test runner). Gates before a slice is "done": `manage.py check`, `makemigrations --check`, full pytest, `tests/test_no_float_money.py`, frontend lint (0 warnings), `npm test`, `npm run build`, `npm run check:api-types`. Merge order and CI: merge to `develop` only on Anesu's word; run `develop` CI (incl. `postgres-ledger`) after each push; anything touching row locks needs a Postgres test marker.

## 6. Questions that still change the design (defaults in brackets; none blocks wave 0-2)

1. D-3 payout cadence/rail/maker-checker (bi-weekly, EFT/ACB CSV, maker-checker yes) - gates wave 3 only.
2. D-4: does a late memo forfeit the lesson's pay (DEC says yes; code pays 80 % today) - gates 11.10 policy; we ship only the reminder email and failure isolation.
3. D-11 vetting stages / who approves (any admin approves; Sharon interviews; training gate blocks going live) - the status machine is built to absorb a later extra stage.
4. D-9 Zoom hosts (`HostPicker` abstraction only).
5. D-8 recording (no recording; telemetry purge only).
6. D-10 domain/sender (`sharonesl.com`; sending stays mock-safe until verified).
7. Tutor status enum above (replaces the two booleans) - confirm.
8. Training gate on by default? [`TUTOR_TRAINING_GATE_ENABLED=False` until real content exists.]
9. Cloudflare Stream video (gap G1): separate slice after the funnel; needs a Cloudflare Stream decision.
10. Minimum payout threshold and currency handling (R100, ZAR snapshots) - wave 3.

## 7. Known doc drift to fix while here
`CLAUDE.md` says 8 beat schedules (there are 11); `PROJECT_CONTEXT.md` still says fixed R75 payout; UI slice doc hardcodes "6.40 x 18.75"; `DECISIONS_D1_D12.md` D-4 claims the code forfeits tutor pay (it does not); `ERROR_LOGS` ID blocks; Slice 7 UI still shows "hourly rate".
