# Phase 8 - Tasks 8.5 + 8.6: account recovery, e-mail verification, login by e-mail (reference)

**Date:** 2026-10-02 · **Status:** implemented, verified live (real browser against real servers) · Patterns taken from ECC `django-security`, `django-tdd`.

## 1. Endpoints (`/api/v1/auth/`)

| Endpoint | Auth | Behaviour | Throttle |
| :--- | :--- | :--- | :--- |
| `POST password-reset/` `{email}` | none | Always `202` + same body, account or not. Mail queued **after commit** (Celery), so timing does not leak either. Skips inactive / password-less accounts. | 5/h per IP **and** 3/h per address |
| `POST password-reset/confirm/` `{uid, token, new_password, new_password_confirm}` | none | Token valid once, 60 min. Runs the password validators with the user context. Sets `email_verified`, **blacklists every outstanding refresh token**. Bad uid / bad token / used / expired -> one generic `400 {token}`. | 10/h per IP |
| `POST password-change/` `{old_password, new_password, new_password_confirm}` | access token | Checks the old password, must differ, validators apply. Revokes **all** refresh tokens including the caller's: the client signs out (the UI does this). | 10/h per user |
| `POST verify-email/` | access token | (Re)queues the verification mail; no-op `202` when already verified. | 5/h per user |
| `POST verify-email/confirm/` `{token}` | none | Idempotent. Token = signed `{user, email}` valid 3 days; changing the address kills links sent to the old one. | 20/h per IP |
| `POST token/` `{username, password}` | none | `username` may now be an **e-mail** (case-insensitive). Resolved server-side to the one active matching account; unknown/ambiguous -> ordinary 401, identical to a wrong password. | `login` + per-identifier `login_user` |

`GET/PATCH me/` now returns `email_verified` (read-only). Changing `email` resets it to `false` and mails the new address.

## 2. Security decisions

- **Tokens:** reset = Django `PasswordResetTokenGenerator` (hash covers password hash + last_login => dies on use). Verification = `signing.dumps` with a dedicated salt, bound to the e-mail. The two are not interchangeable (tested).
- **Links** use `FRONTEND_BASE_URL`, never the request Host (tested with a poisoned Host/X-Forwarded-Host/Origin).
- **Tokens are minted inside the Celery task**, so they never sit in the broker/Redis payload (`args = user_id, kind`).
- **No enumeration** on reset request / confirm / login. (Registration still tells you an e-mail is taken - unavoidable without e-mail-first signup; throttled at 5/h.)
- **Usernames may no longer contain `@`** (new signups), so a username cannot impersonate an e-mail now that login accepts both.
- **E-mail send failures raise** `EmailDeliveryError` and the task retries with back-off (max 5); dev mock logs the link only when `DEBUG`.
- **Frontend:** reset/verify pages copy the one-time credential into memory and `history.replaceState` it out of the URL; `Referrer-Policy: no-referrer` + `Cache-Control: no-store` on those two routes.
- **Production guard** (`config/settings/guard.py`) now refuses to boot without an https `FRONTEND_BASE_URL` and a real `RESEND_API_KEY` (otherwise recovery mail silently never sends).

## 3. Config

| Var | Meaning |
| :--- | :--- |
| `FRONTEND_BASE_URL` | Public site URL; base of every e-mailed link. **Required in production** (https). |
| `RESEND_API_KEY`, `DEFAULT_FROM_EMAIL` | Real key required in production. Sender domain must be verified in Resend (Anesu). |
| `PASSWORD_RESET_TIMEOUT` (3600 s), `EMAIL_VERIFY_MAX_AGE` (3 d) | Settings, not env. |

Local dev without Redis: Celery tasks now run inline (`CELERY_TASK_ALWAYS_EAGER` when `REDIS_URL` is empty) and the mock mail, including the link, prints in the `runserver` console.

## 4. Known limits / follow-ups

- Verification is **not** enforced anywhere yet (login and booking still work unverified). Decide in Phase 9/10 whether booking/payment requires it.
- A password change leaves already-issued **access tokens** valid for up to 15 min (stateless JWT); refresh tokens are dead immediately.
- Duplicate e-mails created before the case-insensitive uniqueness fix: those addresses cannot log in by e-mail (they still can by username); no DB-level unique index yet.
- Resend sender domain/DNS (SPF/DKIM) must be set up before production; until then recovery mail only prints in dev.
- `GET /auth/me/` is used by the BFF to refresh the user; `email_verified` reaches the UI from there.
