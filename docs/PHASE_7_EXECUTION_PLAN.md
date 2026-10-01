# Phase 7 Execution Plan - Security emergency + spec freeze

**Created:** 2026-10-02 · **Author:** Claude (lead architect) · **Design input:** system-design agent review of the real source · **Parent:** `PRODUCTION_READINESS_PLAN.md` §Phase 7

## 1. Decisions taken for this stage (Anesu, 2026-10-02)

| Ref | Decision |
| :--- | :--- |
| Tutor self-signup | Allowed as `teacher`, unverified; hidden from public list until vetted. `admin` is never self-assignable. |
| Uploads | Switch to **presigned POST** (server-enforced `content-length-range` + content-type). |
| JWT lifetime | Check the frontend refresh flow first; 15 min only if refresh exists, else keep 60 min and flag for Phase 8. |
| **D-1** | Platform-set flat retail price per currency (not tutor-set). Trial lesson not decided. |
| **D-2** | 80/20 split (matches ledger). Platform bears gateway fees from its 20%. |
| **D-5** | No-show: tutor T+10, student T+10, 5 min disconnect grace. |
| **D-6** | **Gateway refund only** (no wallet credit on cancellation). Cancel window and credit expiry still open. |
| D-3, D-4, D-7..D-12 | Not yet answered. Options and a recommendation are in `DECISIONS_D1_D12.md`. |

## 2. Corrections to the original task text (found by reading the code)

1. 7.2/7.3 "match against PaymentTransaction" was impossible: checkout persisted nothing and `PaymentTransaction` was only created from attacker-controlled webhook fields. Fix: checkout persists an `INITIALIZED` transaction with expected amount/currency and a `merchant_reference`.
2. `.env.example` has `PAYFAST_*`/`PAYPAL_*` but no settings read them. Checkout hardcoded merchant id `10000100`.
3. `base.py` hardcodes `DEBUG = False`, so fail-fast belongs in `production.py`, not base. `wsgi/asgi/celery` should default to production.
4. `BLACKLIST_AFTER_ROTATION` is inert until `token_blacklist` is installed.
5. Real IDORs beyond the list: CRM dossier PATCH lets any teacher edit any student; admin without a profile silently uses `TeacherProfile.objects.first()`; `ReportOutageView` can be repeated for repeated refunds; `TeacherAvailabilityManageView` 500s without a profile.
6. Public webhooks are authenticated by signature, not by JWT; throttling is per-IP.

## 3. Task order (dependencies)

`7.10 → 7.4 → 7.5 → 7.7 → 7.1 → 7.6 → 7.9 → 7.8 → 7.2 + 7.3 (together, shared migration)`; then docs (decision sheet, roadmap, error log).

Every task: failing test first, then fix, then full `pytest`. New test files: `test_security_auth.py`, `test_permission_matrix.py`, `test_settings_guard.py`, `test_upload_hardening.py`, `test_payment_verification.py`.

| Task | Change | Key tests |
| :--- | :--- | :--- |
| 7.10 | `.gitignore` for `.mcp.json`, `.claude/`, `.codex/`, `.agents/`, `.env*`. **Anesu** inspects those files for tokens (agent does not read secret files). | n/a |
| 7.4 | `production.py` fail-fast validator (secret key, hosts, CORS, CSRF origins, Zoom secret); Zoom webhook fails closed with no secret; remove `SECRET_KEY` fallback; wsgi/asgi/celery default to production. | settings-guard subprocess tests |
| 7.5 | `IsAuthenticated` default, JWT-only auth; explicit `AllowAny` on login; `IsTeacher`/`IsStudent` no longer pass on `is_staff`. | every URL declares permissions; anon 401 on protected, public endpoints open |
| 7.7 | `token_blacklist` app, `POST /auth/logout/`, frontend logout posts refresh token. | logout blacklists refresh |
| 7.1 | Register: role ∈ {student, teacher}, email required + unique (case-insens.); `UserSerializer.role` read-only. | role=admin rejected; PATCH role ignored |
| 7.6 | Scoped throttles (login 5/min, register 5/h, upload 30/h, webhooks 120/min, anon/user defaults). | 429 after limit |
| 7.9 | Presigned POST with per-prefix content-type + size policy, `expires_in` clamp, trailing-slash prefix. | bad type / prefix rejected |
| 7.8 | CRM dossier requires a shared booking; admin must pass `teacher_id`; `TeacherDetailView` verified-only; TEFL URL fallback removed; outage idempotency; permission matrix. | IDOR tests |
| 7.2 | PayFast ITN: signature (passphrase), source IP, server postback, amount/currency/merchant match against persisted `INITIALIZED` tx. | valid/bad-sig/IP/amount/postback |
| 7.3 | PayPal `verify-webhook-signature`, server-side capture lookup, no default amount, only `PAYMENT.CAPTURE.COMPLETED`. | valid/bad-sig/amount/currency |

Gateway HTTP goes through an injectable client (`apps/payments/gateways/`) so tests never touch the network. There is no "fake gateway" setting that could leak to production.

## 4. Exit criteria

- `pytest` green (baseline 74 + new), `manage.py check` and `makemigrations --check` clean, `npm run build` passes.
- No self-service path to `admin`; no unauthenticated payment confirmation; production refuses to boot with dev settings.
- Roadmap + `ERROR_LOGS_AND_RESOLUTIONS.md` updated. 7.10 and the D-decisions remain open for Anesu where noted.
