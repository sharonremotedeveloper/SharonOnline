# Project Context & Domain Specifications

## 1. Executive Overview

**Sharon's ESL Marketplace Platform** is a high-reliability, mobile-first synchronous English tutoring marketplace designed to bridge international English learners in East Asia (Japan, South Korea) and Europe with vetted native and South African tutors.

The platform provides friction-free 25-minute synchronous video lessons, automated scheduling with strict timezone normalization, interactive curriculum reading, multi-currency escrow processing, and grid outage protection for South African tutors.

---

## 2. Business Model & Financial Unit Economics

| Metric | Specification | Note / Detail |
| :--- | :--- | :--- |
| **Retail Lesson Price** | **\$9.00 USD** per 25-minute session | Student payment via PayPal / PayFast |
| **Tutor Payout** | **R75 ZAR** (approx. \$4.17 USD @ R18/\$1) | Fixed base rate for verified tutors |
| **Gross Margin / Spread** | **~\$4.83 USD** (53.6%) | Platform margin before payment gateway fees |
| **Net Platform Margin** | **49.4%** | Post-gateway processing fees |
| **Payout Cadence** | **Monthly Batch (1st of month)** | Accumulated escrow released via EFT / Wise / PayPal |

---

## 3. Target User Segments & Persona Needs

### 3.1 Students (Japan, South Korea, Europe)
- **Primary Need**: High-speed, 10-second booking experience; local timezone scheduling; instant Zoom video room access without complicated app setup.
- **Payment Modes**: Credit Card, PayPal (USD/EUR/JPY), PayFast (ZAR).
- **Core Motivation**: Business English fluency, daily news discussions, TOEIC/IELTS test preparation.

### 3.2 Tutors (South Africa & Native English Speakers)
- **Primary Need**: Stable monthly income, clear schedule management, automated Zoom link generation, Eskom load-shedding protection buffers.
- **Payout Modes**: Direct South African Bank EFT, Wise, PayPal.
- **Operational Requirement**: Submission of 2-minute post-lesson memos (grammar corrections, vocabulary flashcards) within 12 hours of session completion.

### 3.3 Platform Owner / Admin (Sharon)
- **Primary Need**: Automated escrow clearance, dispute arbitration portal, zero video bandwidth overhead (using Zoom S2S OAuth API), and real-time session monitoring.

---

## 4. Core Domain Rules & Operational Guardrails

1. **Synchronous 25-Minute Unit**: Lessons strictly run in 25-minute slots starting on the hour or half-hour (e.g. 10:00–10:25, 10:30–10:55 UTC).
2. **Escrow Hold & Release**:
   - Student payment is held in platform escrow upon booking.
   - Escrow clears for tutor payout if: (a) Tutor joins session for at least 20 minutes (audited via Zoom Webhook), and (b) Tutor submits Lesson Memo within 12 hours.
3. **No-Show Policy**:
   - **Student No-Show**: Student credit is forfeited; tutor receives 100% payout.
   - **Tutor No-Show**: Student receives 100% refund + bonus credit; tutor penalized.
4. **Eskom Grid Resilience**: Tutors flag outage windows via the "Power Guard" module, automatically removing affected slots from public search.
5. **Private Student Dossier**: Tutors maintain private notes on student progress ("Notes to Remember") accessible only by the authoring tutor and Admin.

---

## 5. Key Domain Terminology

- **Slot**: A discrete 25-minute temporal window available for booking.
- **Redlock Lock**: A temporary 10-minute Redis lock (`SET slot:... NX EX 600`) held while a student completes checkout to prevent double-booking.
- **Lesson Memo**: Structured post-lesson feedback containing grammar notes, vocabulary lists, and homework.
- **Attendance Audit**: Automated join/leave timestamps ingested directly from Zoom webhooks.

## 6. Decisions recorded 2026-10-02 (Phase 7 spec freeze)

These supersede conflicting statements above (notably the fixed R75 tutor payout in §2). Full list and open items: `DECISIONS_D1_D12.md`.

- **D-1 Pricing:** platform-set flat retail price per currency (not tutor-set). Trial lesson undecided.
- **D-2 Tutor pay:** 80/20 split; the platform bears gateway fees from its 20%.
- **D-5 No-show:** tutor and student at T+10 minutes; 5 minute disconnect grace.
- **D-6 Refunds:** gateway refund only (cancel window and credit expiry still open; conflicts with credit refunds in the outage and DEF-501 paths, to be resolved before Phase 10).
- **Tutor signup:** self-registration as `teacher` is allowed but unverified and hidden until vetted; `admin` is never self-assigned. Since slice T1c the signup also creates the tutor profile in status `applied` (`docs/TUTOR_STATUS_MACHINE.md` §8); the tutor edits headline/bio/specialties at `/api/v1/teachers/me/`, while video, accent and documents change only through vetting.
- **Storage:** Cloudflare R2 bucket `esl-platform-assets` (public access off, no custom domain yet). Uploads are presigned PUT with a signed `Content-Length`.
