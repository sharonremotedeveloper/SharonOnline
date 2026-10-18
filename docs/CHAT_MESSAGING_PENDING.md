# In-app chat (tutor / student / admin) - PENDING, DESIGN RECOMMENDED

**Status: PENDING - nothing built. The design below is recommended but not yet approved.** Recorded 2026-10-18 at
Anesu's request, to be completed later. Roadmap: Task 12.10 (slices C0-C6) in `PRODUCTION_READINESS_PLAN.md`.

**Requirement (Anesu, 2026-10-18).** Tutors can talk to students and admin. Admin can talk to tutors and students.
Students can talk to admin and tutors.

**How the design was reached.** Three agents worked on it:
- one mapped the codebase;
- one researched how Preply, italki, Cambly, Wyzant, Upwork and Airbnb handle messaging and compared build options;
- one review agent checked both reports against the code and chose one design.

Claude re-checked the two code facts the choice depends on (`frontend/src/lib/server/handlers.ts:133`,
`backend/Dockerfile:73`).

## 1. Decision in one paragraph

Build chat ourselves as a new Django app, `apps/chat`. Messages are stored in our Postgres database and served
through the existing Next.js BFF proxy. Clients poll one cheap "sync" endpoint, which answers **204 No Content** when
nothing has changed.

This needs no vendor, no new service and no new token in browser JavaScript. It reuses:
- `contact_guard` for the off-platform contact filter;
- `notify()` for unread-message e-mail;
- R2 private uploads for attachments;
- the guard-test framework.

Build order: the **support inbox** (student/tutor <-> staff) ships first, for the soft launch. Student <-> tutor chat
follows, gated on a paid booking. Instant delivery through Ably is an optional later upgrade; Ably would carry only a
"new message" signal, never the content.

## 2. What exists today (checked 2026-10-18)

- **No real-time stack.** There is no Django Channels, daphne, uvicorn, WebSocket or SSE code. `config/asgi.py` is the
  stock file and nothing uses it.
- **The backend can handle about 8 requests at once.** It runs WSGI: `gunicorn ... --workers 4 --threads 2`
  (`backend/Dockerfile:73`). Production has one replica each of API, worker and beat (`docs/RAILWAY_SETUP.md`).
- **The BFF proxy cannot stream.** `handlers.ts:133` reads the whole upstream body with `arrayBuffer()`, and
  `upstream.ts` aborts after 25 s. The proxy forwards only a few request headers (no `If-None-Match`) and a few
  response headers (no `ETag`), so ETag/304 caching does **not** work through it. A 204 reply does
  (`handlers.ts:133`). The request body cap is about 2 MB.
- **Vercel cannot hold WebSockets**, and the JWT cookies belong only to the frontend host, so a browser WebSocket
  straight to `api.topteacheracademy.com` has no credentials. Any later realtime option needs a single-use ticket
  minted through `/api/proxy`.
- **Redis is Upstash** (Frankfurt). Pay-as-you-go is billed per command. Each authenticated request costs about 2
  commands for DRF throttling. Nothing uses pub/sub.
- **Reusable pieces:**
  - `apps/common/contact_guard.py`: `detect_off_platform_contact()` and `validate_no_off_platform_contact`. It
    catches emails, phone numbers, WhatsApp/LINE/Kakao/WeChat/Telegram/Skype/Zoom/Meet/PayPal handles and
    obfuscation, and has adversarial tests. It can detect or reject but **cannot mask**.
  - `apps/notifications`: `notify()` takes ids-only payloads; keys such as `message`/`text`/`body` are rejected at
    `service.py:34`. Each new kind needs a golden snapshot.
  - Uploads: R2 presign, `upload_policy.py`, and the T3 quarantine -> commit flow (`teachers/assets.py`).
  - `PrivateAssetAccessAudit`, the precedent for an audited staff-access log.
- **Overlapping features:**
  - `SupportInquiry` (`users/models.py:57`) is a one-shot ticket that staff read only in Django admin.
  - `DisputeCase` is one per booking and is not a conversation.
  - Figma has a "Send message" button on the admin User and Tutor drawers with no screen behind it, and no chat
    screens at all.
- **Specs:** `COMPREHENSIVE_PAGE_INVENTORY_AND_SYSTEM_LOGIC.md:258` (workspace root) requires a strict ban on
  off-platform contact (WhatsApp/LINE) and an immediate report button.
- **Daily.co** has in-call messages only, with no history. It cannot be the chat.
- **Navigation:** the student and tutor mobile tab bars are full (5 items, `frontend/src/lib/appTabs.ts`).

## 3. Options considered

Prices were fetched 2026-10-18.

| Option | Verdict | Why |
| :--- | :--- | :--- |
| **Our Postgres + REST via the BFF + cheap polling** | **Chosen** | About $0. Keeps the cookie-only auth rule. Full control of contact blocking, safeguarding and audit. Message content stays in one place for GDPR / POPIA / APPI / PIPA. |
| Same + Ably signal-only realtime | Later upgrade (slice C6) | Free tier: 200 concurrent connections **and** 200 channels, best-effort support. Fine for a pilot, not for production. Standard is $29/month plus usage. The browser would hold a short-lived, subscribe-only token, which needs an ADR because it is an exception to the "no token in browser JS" rule. |
| Django Channels WebSockets / SSE | Rejected for now | Needs a separate ASGI service on Railway plus single-use tickets. On today's gunicorn, each open stream would hold one of the 8 request slots. 3-4 weeks of work and the highest ops burden. |
| Hosted chat services: Stream, TalkJS, Sendbird, CometChat | Rejected | About $240-$500/month at 10k users (Stream Start $399-499, TalkJS $279 from launch, Sendbird $349-399, CometChat $239+). Messages live with the vendor (DPAs and cross-border transfers). A vendor login token sits in the browser. Strong lock-in. Stream's off-platform detection is a paid add-on. |
| Twilio Conversations | Rejected | Now labelled "classic", no UI kit, and Twilio has retired chat products before. |
| Matrix / Rocket.Chat / Mattermost | Rejected | Separate user accounts and database to run. Built for team chat. End-to-end encryption works against the staff oversight we need. |

**How marketplaces do it** (research, partly unverified):
- Preply lets students message before a trial but blocks contact details and outside links, runs automatic spam
  detection, and has a report button on every message.
- Wyzant replaces phone numbers with Xs until the student has a payment method, and staff can lock threads.
- Upwork filters contact details until a contract exists.
- Cambly Kids routes communication through the parent.

## 4. Recommended design

### 4.1 Data model (`backend/apps/chat/models.py`, UUID primary keys, every timestamp `*_utc`)

| Model | Fields |
| :--- | :--- |
| `Conversation` | `kind` (`direct`, `support`); `student` FK User null; `tutor` FK **TeacherProfile** null; `requester` FK User null (support); `booking` FK null (context); `state` (`open`, `read_only`, `locked`, `closed`); `lock_reason`, `locked_by`, `locked_at_utc`; `legal_hold`; `last_seq`; `last_message_at_utc`; `created_at_utc`. Support only: `support_status` (`open`, `waiting_user`, `resolved`), `assignee` FK staff null, `category`, `staff_last_read_seq`. Check constraints per kind; partial unique (`student`, `tutor`) where `kind=direct`. |
| `ConversationParticipant` | `conversation`, `user`, `role` (`student`, `tutor`, `requester`), `last_read_seq`, `muted`, `joined_at_utc`. Unique (`conversation`, `user`). |
| `Message` | `conversation`, `seq` (unique per conversation), `sender` FK null (system), `sender_role` snapshot, `kind` (`text`, `system`, `attachment`), `body` (max 2,000 chars), `client_msg_id` (unique per sender, so a retried send is idempotent), `created_at_utc`, `hidden_at_utc`, `hidden_by`, `hidden_reason`. Append-only like the ledger: no editing at launch; moderation hides, erasure blanks. |
| `InboxState` | `user` (PK), `version` (bigint). Bumped for every recipient inside the send transaction; the sync endpoint reads only this row. |
| `MessageReport` | `message`, `reporter`, `reason` (choice), `note` (staff-only), `status`, `handled_by`, `handled_at_utc`. |
| `StaffConversationAccess` | `staff`, `conversation`, `reason` (choice) + `note`, `accessed_at_utc`. Mirrors `PrivateAssetAccessAudit`. |
| `BlockedSendAttempt` | `user`, `conversation`, `categories` (JSON), `created_at_utc`. **Never stores the text.** |
| `ChatRestriction` | `user`, `until_utc`, `reason`, `set_by`. A send ban. |
| `MessageAttachment` (C5) | `message`, private R2 key, `mime`, `size`, `sha256`, `scan_state`. |

**Booking.teacher mismatch.** `Booking.teacher` points to a TeacherProfile, while `VideoTrial.teacher` points to a
User. A direct conversation stores both sides explicitly (`student` User, `tutor` TeacherProfile). Participants are
Users (`tutor.user`), and VideoTrial maps through `teacher.teacher_profile`.

### 4.2 One way to send, one place for the rules

- `chat/services/send.py::send_message()` is the only code that writes a Message. It:
  - calls `policy.can_message()`;
  - takes `select_for_update(of=('self',))` on the Conversation;
  - increments `last_seq` and inserts the Message;
  - bumps `InboxState` for the recipients.
- A guard test forbids `Message.objects.create` anywhere else, in the same way as the booking-status guard.
- `chat/policy.py::can_message()` is the only place that decides who may message whom:

| Situation | Student -> tutor | Tutor -> student | Student/tutor -> staff | Staff -> anyone |
| :--- | :--- | :--- | :--- | :--- |
| No **paid** booking | No (questions go to support; see Q1) | No, never starts a thread | Yes (support) | Yes (support thread) |
| Paid booking, or last lesson < 90 days ago | Yes | Yes, in the existing thread | Yes | Audited oversight read; posts appear as "Sharon Support" system messages |
| > 90 days since last lesson | Read-only | Read-only | Yes | Yes |
| Tutor not `bookable()` / suspended | Read-only + "contact support" banner | Read-only | Tutor <-> support stays open | Yes |
| Tutor applied / rejected | n/a | n/a | Support only | Yes |
| User has `ChatRestriction` or is inactive | No | No | Support only (when restricted) | Yes |
| Minor (after Task 14.5) | Off until guardian consent; no attachments | Off | Guardian / support | Yes |

**"Paid" means** the booking is in one of these statuses: confirmed, in_progress, any completed_*, disputed,
no-show, interrupted, or cancelled after payment. **Do not copy the CRM rule** (`apps/crm/views.py:46-52`): it
accepts any booking, including `pending_payment`, so a 10-minute slot hold would unlock chat.

### 4.3 Contact details: block (not mask, not flag)

- Every message in a direct thread runs through `detect_off_platform_contact()`. On a hit:
  - the API replies 422 with a friendly explanation, and the client keeps the draft;
  - the categories (not the text) are recorded in `BlockedSendAttempt`;
  - three attempts in 24 h triggers `alert_staff()`.
- Why not mask: we would still store the raw text, and the recipient gets a garbled message.
- Why not just flag: the contact details would already have reached the other person, which is unacceptable when
  minors may be involved.
- Blocking matches how lesson memos and tutor profiles already behave.
- **Support threads are exempt**, so a student can give a PayPal e-mail for a refund.

### 4.4 Sync and polling (no WebSockets)

- `GET /api/v1/chat/sync/?since=<version>` replies **204** when nothing has changed. Otherwise it returns
  `{version, unread_total, conversations: [{id, last_seq, unread}]}`.
- Unread = `last_seq - last_read_seq`. Sending a message advances the sender's own read pointer.
- A thread fetches new messages with `?after_seq=N`. History uses keyset pagination with `?before_seq=` and a limit
  of 30.
- Intervals:
  - open, visible thread: every 10 s, slowing to 30 s after 2 minutes idle;
  - background: every 45 s +/- 10 s, together with the existing notification poll (`useNotifications.ts`); later
    merge both into one `GET /me/badges/`;
  - hidden tab: no polling.
- Throttle scope `chat_sync` at 30/min, failing closed; the client backs off on 503.
- **Load estimate.** Assumes 25% of online users have a thread open.

  | Users online at once | Requests per second | Upstash commands |
  | :--- | :--- | :--- |
  | 500 | about 17-24 | about 50/s |
  | 2,000 | about 77-94 | about 190/s, roughly 120M/month, about $240/month on pay-as-you-go |

  A 204 sync costs about 15-20 ms in-region, so 8 threads give a theoretical ceiling of about 400 requests per
  second. If Vercel functions run in the US and the backend in Frankfurt, the ceiling falls to about 65 per second.
- **Before C1 ships:**
  - pin Railway to an EU region and Vercel functions to `fra1`;
  - move Upstash to a fixed plan ($10-20/month);
  - at about 1,000 users online at once, raise gunicorn to `--threads 8` or add a replica.
- Tell users in the UI that messages may take a few seconds to arrive.

### 4.5 E-mail and in-app notification

- New notify kind `chat_unread`:
  - payload `{conversation_id}` only;
  - key `chat_unread:{conversation_id}:{last_seq_bucket}`.
- A Celery beat task runs every 5 minutes. It e-mails a recipient when a message has been unread for 15 minutes or
  more, the conversation is not muted, and it is outside quiet hours (22:00-08:00 in the user's IANA timezone).
- At most one e-mail per conversation every 6 hours.
- The e-mail shows the sender's first name and the number of messages, **never the message text**.
- Staff get `support_new` when a support thread is opened.
- Add a new optional "messages" category to the notification preferences.

### 4.6 Moderation and staff oversight

- Every message has a report button. A report creates a `MessageReport` and alerts staff.
- Staff can hide a message, lock or unlock a thread, and set a `ChatRestriction`.
- Opening any non-support thread asks staff for a reason and writes `StaffConversationAccess`, which is listed in
  an audit log.
- Asymmetric privacy: who reported a message and the report notes are staff-only. CRM dossier content never appears
  in chat serializers. Serializer tests enforce both.

### 4.7 Attachments (slice C5)

- Reuse the T3 flow: presign into a private quarantine prefix (for example `private/chat/{conversation}/`), then a
  commit step that checks conversation membership and sniffs the file's magic bytes.
- Allowed: images (JPEG/PNG/WebP, EXIF stripped on commit) and PDF, 5 MB maximum. **PDFs only once a virus scanner
  exists** (Q5).
- Downloads use 15-minute presigned GETs, authorised by membership and logged.
- Off in support threads by default, and off for minors.

### 4.8 Retention, data export (SAR) and erasure

- Retention, by extending `apps/bookings/retention.py`:
  - direct threads are purged 24 months after the last message;
  - support threads after 36 months;
  - skip anything under `legal_hold`, with an open report, or linked to a booking with an open `DisputeCase`.
- SAR: add `_extract_chat()` to `users/services/data_export.py`. Include the user's own conversations; exclude staff
  notes, report details and staff access logs about them.
- Erasure (Task 14.3): blank the user's message bodies and show the sender as "Deleted user". Keep the rows so `seq`
  stays intact. Legal hold overrides erasure.

## 5. API (`/api/v1/chat/`, explicit `permission_classes` on every view)

- **Users:**
  - `GET sync/`
  - `GET conversations/` (keyset on `last_message_at_utc`)
  - `POST conversations/`: `{tutor_id}` or `{booking_id}`; checked by the policy; idempotent get-or-create
  - `GET conversations/{id}/`
  - `GET conversations/{id}/messages/?after_seq|before_seq`
  - `POST conversations/{id}/messages/`: `{client_msg_id, body}`
  - `POST conversations/{id}/read/`: `{seq}`
  - `POST conversations/{id}/mute/`
  - `POST messages/{id}/report/`
  - `POST support/`: new ticket, `{category, body, booking_id?}`
  - `POST conversations/{id}/attachments/presign/` and `.../attachments/commit/` (C5)
- **Admin** (`/api/v1/admin/chat/`, `IsPlatformAdmin`):
  - `support/`: queue with filter, assign and status
  - `conversations/{id}/`: GET requires `?reason=` and is audited
  - `conversations/{id}/lock/` and `.../unlock/`
  - `messages/{id}/hide/`
  - `reports/` and `reports/{id}/resolve/`
  - `restrictions/`
  - `access-log/`

## 6. Frontend

- **Pages:**
  - `student/messages/page.tsx` and `student/messages/[id]/page.tsx`, with the same pair under `teacher/`. On mobile,
    the list and the thread are separate full-screen pages.
  - Admin: `admin/support/` (with `[id]`), `admin/conversations/[id]` (asks for a reason first),
    `admin/moderation/` (reports and restrictions).
- **Components** in `components/chat/`: `ConversationList`, `ThreadView`, `Composer` (shows the contact-block error
  inline and keeps the draft), `ReportDialog`, and the `useChatSync` hook.
- **Entry points:**
  - a Messages icon with an unread badge next to the bell in `components/AccountMenu.tsx` (no sixth tab);
  - "Message tutor" on lesson cards and booking detail;
  - "Message" on `/teacher/students` rows;
  - "Contact support" in the account menu, replacing the logged-in use of the contact form;
  - admin nav (`app/admin/layout.tsx`): "Support Inbox" and "Moderation". These also back the Figma "Send message"
    buttons.
- Keep `SupportInquiry` only for the public, logged-out contact form.

## 7. Build plan (Task 12.10)

Each slice gets its own ERR block (`PHASE_11_12_EXECUTION_PLAN.md` §4), a slice doc in `docs/slices/`, and a mutation
table in `docs/mutation/`. The new app must pass every guard in `backend/tests/guards/`, the OpenAPI contract test, and
regenerate `api.generated.ts`.

| Slice | Scope | Days | Tests / gates | Needed by |
| :--- | :--- | :--- | :--- | :--- |
| **C0** | ADR (polling, block policy, support in the same model) + models, migrations, `policy.py`, `send_message()` | 3 | migration-leaf and `select_for_update` guards; a test for every cell of the policy table; "no direct `Message.create`" guard | Soft launch |
| **C1** | API + sync/204 + throttles + OpenAPI + `gen:api` | 3-4 | contract test; concurrent-`seq` test on Postgres; idempotent `client_msg_id`; reuse the contact-guard adversarial tests | Soft launch |
| **C2** | Support inbox UI (user + admin) + `chat_unread` / `support_new` + digest task | 4 | notification goldens; ids-only payload; quiet hours on the fake clock | **Soft launch** |
| **C3** | Student <-> tutor UI + report / hide / lock / restrict + audited staff read | 4-5 | asymmetric-privacy serializer tests; audit row on every staff read; suspended tutor = read-only | Public launch |
| **C4** | Retention, SAR export, erasure hooks | 2 | retention tests including legal hold and open dispute | Public launch |
| C5 | Attachments (images; PDFs after a virus scanner) | 3-4 | magic bytes, EXIF strip, size/MIME, private prefix | Later |
| C6 | Ably signal-only realtime (subscribe-only token via the BFF; content still over REST) | 2-4 | no-network fakes; polling still works as the fallback | Only if more than about 1,000 users are online at once, or users complain about delay |

About 16-18 working days to public launch. C0-C2 (about 10 days) are the soft-launch part.

## 8. Open decisions for Anesu (recommended default in brackets)

1. **Q1.** Can students message a tutor *before* booking? [No at launch; pre-booking questions go to support. Later
   behind a `CHAT_PREBOOKING_ENABLED` flag: student-initiated only, at most 3 messages until the tutor replies.]
2. **Q2.** Are under-18s allowed before parental consent (Task 14.5) exists? [18+ only at launch, through the Terms
   and a sign-up checkbox. Student <-> tutor chat stays off for minors until guardian consent.] **Must be answered
   before C3 goes live.**
3. **Q3.** How long is chat kept? [24 months for tutor chats, 36 months for support; legal hold and disputes
   override.]
4. **Q4.** Can staff read tutor <-> student chats without a report? [Yes, with a mandatory reason and an audit log,
   disclosed in the privacy policy.]
5. **Q5.** Can tutors send PDFs (worksheets) in chat? [Images only until a virus-scan service is chosen.]
6. **Q6.** Should we switch Upstash to a fixed plan and pin Railway and Vercel functions to EU regions now? [Yes. It
   is cheap and also helps the existing notification polling.]

## 9. Risks

- **Polling cost and delay** if the backend and frontend run in different regions, or Upstash stays on
  pay-as-you-go. Fix both before C1.
- **The contact guard may block innocent messages** (times, prices, links to materials). Log the categories, review
  them weekly, and tune the patterns and tests.
- **Safeguarding:** no age data exists today. Q2 must be answered before C3.
- **One gunicorn replica:** slow upstream calls (up to 25 s) plus polling can use up all 8 request slots. Raise
  threads or add a replica at about 1,000 users online at once.
- **Not instant:** expect a 10-45 s delay until C6. Say so in the UI.
- **Scope creep:** typing indicators, edits, per-message read receipts and group chat stay out until after C6.

## 10. Sources (fetched 2026-10-18)

Pricing:
- [Ably pricing](https://ably.com/pricing) and [Ably free limits](https://ably.com/docs/platform/pricing/free)
- [Pusher Channels pricing](https://pusher.com/channels/pricing/)
- [Stream Chat pricing](https://getstream.io/chat/pricing/)
- [TalkJS pricing](https://talkjs.com/pricing/)
- [Sendbird pricing](https://sendbird.com/pricing/chat)
- [CometChat pricing](https://www.cometchat.com/pricing)
- [Twilio Conversations pricing](https://www.twilio.com/en-us/messaging/pricing/conversations-api)
- [Upstash Redis pricing](https://upstash.com/pricing/redis)

Marketplace rules:
- [Preply report button](https://help.preply.com/en/articles/5595326-report-message-button)
- [Wyzant phone masking](https://support.wyzant.com/students-parents/find-a-tutor/why-was-my-phone-number-removed-from-the-message-i-sent/)
- [Upwork pre-contract messaging](https://support.upwork.com/hc/en-us/articles/17995658941843--Get-to-know-each-other-before-a-contract)
- [Cambly tutor protection](https://support.cambly.com/hc/en-us/articles/360052497232-How-does-Cambly-protect-its-tutors-)

Daily.co:
- [Daily.co chat options](https://www.daily.co/blog/three-ways-to-add-chat-to-your-video-calls-with-the-daily-api/)
