# Technical Architecture & Database Schema Specification

## 1. System Architecture & Topology

```javascript
[ Next.js 14 Frontend (Vercel / Cloudflare Pages) ]
    │ (SSR, ISR & Client UI: Profiles, Booking, Dashboards, Material Viewer)
    ▼
[ Cloudflare Edge Network (WAF, SSL, CDN, DDoS Protection) ]
    │
    ▼
[ Django 5.x REST API Service (Railway / Render / Docker Container) ]
    ├── Auth & Permissions (JWT / Session)
    ├── Slot Availability Engine (Strict UTC ISO 8601)
    ├── Booking & Escrow State Machine
    └── Material CMS & Category Engine
    │
    ├── [ PostgreSQL 16 Database (Neon Serverless / Docker Postgres) ]
    │       └── ACID Transactions & Strict Unique Constraints
    └── [ Redis 7 Cache & Broker (Upstash Serverless / Docker Redis) ]
            ├── Distributed 10-Minute Booking Reservation Locks (Redlock)
            └── Celery Background Task Queue
                    ├── Zoom Server-to-Server OAuth Meeting Creation
                    ├── Google Calendar v3 Event Injection
                    ├── Resend Email API (.ics calendar attachments)
                    └── Webhook Reconciliation & Ingestion Engine
```

---

## 2. Core Relational Database Schema (Django Models)

### 2.1 Users & Teacher Profiles (`apps/users` & `apps/teachers`)

#### `User` Model
- `id`: UUID (Primary Key)
- `email`: EmailField (Unique, Indexed)
- `role`: CharField Enum (`student`, `teacher`, `admin`)
- `country`: CharField (ISO 3166-1 alpha-2 code, e.g. `JP`, `ZA`)
- `timezone`: CharField (IANA Timezone string, e.g. `Asia/Tokyo`, `Africa/Johannesburg`)
- `google_calendar_token`: JSONField (OAuth tokens for calendar sync)
- `created_at` / `updated_at`: DateTimeField

#### `TeacherProfile` Model
- `user`: OneToOneField (`User`)
- `accent`: CharField Enum (`South African`, `British`, `American`, `International`)
- `intro_video_url`: URLField (Cloudflare Stream HLS URL)
- `price_per_25min_usd`: DecimalField (Default: `9.00`)
- `specialties`: JSONField (e.g. `['FreeTalk', 'Business', 'TOEIC']`)
- `is_verified`: BooleanField (Admin vetting status)
- `bio`: TextField

#### `TeacherAvailability` Model
- `teacher`: ForeignKey (`TeacherProfile`)
- `day_of_week`: SmallIntegerField (0=Monday ... 6=Sunday)
- `start_time` / `end_time`: TimeField (Stored in teacher's local timezone for recurring projection)

---

### 2.2 Materials CMS (`apps/materials`)

#### `Material` Model
- `id`: UUID (Primary Key)
- `title`: CharField
- `slug`: SlugField (Unique, Indexed)
- `category`: CharField Indexed (`Daily News`, `FreeTalk`, `Business`, `Interview Prep`)
- `cefr_level`: CharField Enum (`A1`, `A2`, `B1`, `B2`, `C1`, `C2`)
- `content_html`: TextField (Interactive article text, vocabulary cards, discussion questions)
- `pdf_file_url`: URLField (Cloudflare R2 download URL)
- `is_approved`: BooleanField

---

### 2.3 Booking & Escrow State Machine (`apps/bookings`)

#### `Booking` Model
- `id`: UUID (Primary Key)
- `teacher`: ForeignKey (`TeacherProfile`)
- `student`: ForeignKey (`User`)
- `material`: ForeignKey (`Material`, Nullable)
- `class_type`: CharField Enum (`individual` [25 min], `group` [max 6])
- `status`: CharField Enum (`pending_payment`, `confirmed`, `in_progress`, `completed`, `cancelled_student`, `cancelled_teacher`, `disputed`)
- `start_time_utc` / `end_time_utc`: DateTimeField (Stored strictly in UTC)
- `zoom_meeting_id` / `zoom_join_url` / `zoom_start_url` / `zoom_password`: CharField / URLField
- `teacher_gcal_event_id`: CharField
- **Database Constraint**:  
  `UniqueConstraint(fields=['teacher', 'start_time_utc'], condition=Q(status__in=['confirmed', 'in_progress', 'completed']))`

---

### 2.4 Attendance Auditing & Lesson Memos

#### `LessonMemo` Model
- `booking`: OneToOneField (`Booking`)
- `feedback_text`: TextField (Grammar corrections & speaking feedback)
- `vocabulary_words`: JSONField (List of words practiced)
- `homework`: TextField

#### `AttendanceAudit` Model
- `booking`: ForeignKey (`Booking`)
- `participant_email`: EmailField
- `join_time_utc` / `leave_time_utc`: DateTimeField
- `total_minutes`: PositiveIntegerField (Ingested from Zoom Webhooks `meeting.participant_joined` and `meeting.participant_left`)

---

### 2.5 Multi-Currency Payments & Ledger (`apps/payments`)

#### `PaymentTransaction` Model
- `booking`: ForeignKey (`Booking`)
- `gateway`: CharField Enum (`payfast` [ZAR], `paypal` [USD/EUR/JPY])
- `gateway_reference`: CharField (Unique transaction reference from provider)
- `amount` / `currency`: DecimalField / CharField
- `status`: CharField Enum (`initialized`, `success`, `failed`, `refunded`)
- `raw_webhook_payload`: JSONField

---

### 2.6 Student-Tutor Dossier & Asymmetric Reviews

#### `StudentTutorDossier` Model (`apps/crm`)
- `teacher`: ForeignKey (`TeacherProfile`)
- `student`: ForeignKey (`User`)
- `private_notes`: TextField (Confidential teacher notes)
- `updated_at`: DateTimeField
- **Security Rule**: Excluded from student-facing serializers; accessible only by authoring teacher and Admin.

#### `LessonReview` Model (`apps/reviews`)
- `booking`: OneToOneField (`Booking`)
- `student`: ForeignKey (`User`)
- `teacher`: ForeignKey (`TeacherProfile`)
- `rating_score`: PositiveSmallIntegerField (1–5 stars)
- `written_feedback`: TextField (Visible to teacher and Admin only; hidden from student public view)
- `admin_flagged`: BooleanField

---

## 3. Concurrency Control & Webhook Idempotency

### 3.1 Distributed 10-Minute Booking Reservation Lock (Redlock)
To prevent double-booking race conditions when multiple students attempt to book the same slot:
```python
# Redis Lock Execution (10-minute TTL)
lock_acquired = redis_client.set(
    f"booking:slot:{teacher_id}:{start_time_utc}",
    student_id,
    nx=True,
    ex=600  # 10 minutes TTL
)
if not lock_acquired:
    raise ConflictError("This slot is currently reserved by another student.")
```

### 3.2 Webhook Idempotency Engine
```python
@transaction.atomic
def process_payment_webhook(gateway, transaction_id, raw_payload, status):
    tx, created = PaymentTransaction.objects.select_for_update().get_or_create(
        gateway_reference=transaction_id,
        defaults={'gateway': gateway, 'status': status, 'raw_webhook_payload': raw_payload}
    )
    if not created and tx.status == PaymentTransaction.Status.SUCCESS:
        return {"status": "already_processed"}  # Prevents duplicate processing
```

---

## 4. Timezone Standardization Protocol

1. **Database Universal Storage**: All timestamps stored strictly in **UTC (ISO 8601)** (`YYYY-MM-DDTHH:MM:SSZ`).
2. **Recurring Availability Projection**: Teachers specify availability in their local IANA timezone; Celery projected slots translate concrete UTC dates 14 days forward using `zoneinfo`.
3. **Browser Localized Rendering**: Next.js automatically formats UTC dates into the student's local browser timezone (`Intl.DateTimeFormat().resolvedOptions().timeZone`).

---

## 5. Cloudflare R2 Asset Storage & Zero-Egress Delivery Architecture

### 5.1 Asset Partitioning & Storage Classes
| Asset Namespace | Access Tier | Storage Backend | Delivery Endpoint | Expiration / Caching |
| :--- | :--- | :--- | :--- | :--- |
| `materials/pdfs/*` | Public CDN | `MediaR2Storage` | `https://assets.sharonesl.com/materials/pdfs/...` | Edge Cache (1 year) |
| `materials/audio/*` | Public CDN | `MediaR2Storage` | `https://assets.sharonesl.com/materials/audio/...` | Edge Cache (1 year) |
| `teachers/avatars/*` | Public CDN | `MediaR2Storage` | `https://assets.sharonesl.com/teachers/avatars/...` | Next.js Image Optimizer |
| `teachers/audio/*` | Public CDN | `MediaR2Storage` | `https://assets.sharonesl.com/teachers/audio/...` | HTML5 Audio Streaming |
| `private/vetting/*` | **Private** | `PrivateMediaR2Storage` | Presigned S3 GET URL | 15 minutes (900s TTL) |

### 5.2 Zero-Egress Economics & S3 Compatibility
- **Zero Bandwidth Surcharge**: Cloudflare R2 provides \$0.00 / GB egress fees, eliminating AWS S3 data transfer costs across global student/teacher traffic.
- **Header Sanitization**: Cloudflare R2 does not support AWS S3 ACL headers; `default_acl = None` is enforced across all custom storage backends.
- **Presigned URL Service**: `POST /api/v1/integrations/r2/presigned-url/` authenticates and issues direct-to-R2 upload and download presigned URLs with strict namespace RBAC enforcement.
- **Zero-Drift Offline Fallback**: In local development environments without R2 credentials, Django seamlessly falls back to `django.core.files.storage.FileSystemStorage` (`MEDIA_URL = '/media/'`).

