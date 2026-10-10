# Production video trial readiness

Status checked 2026-10-10. This is a release checklist for two real users to sign in as tutor and student and join one Daily.co classroom. It is not a claim that production is live.

## Current state

- `develop` has the Daily classroom and a development checkout shortcut. The development API deployed commit `8cc6ee1` successfully; later CI fixes are on `develop` at `643a516`.
- `main` is still at `261077c`, 215 commits behind `develop` as of this check. The Daily implementation is not on `main`.
- Railway production contains a staged `backend-api-production` service from `main`, with root directory `backend`, health check `/api/health/`, and two staged Neon connection variables. It has no successful deployment, production Redis service/URL, or configured Daily variables.
- The production settings deliberately force `TEST_BOOKINGS_ENABLED=False`. The development-only checkout button must not be used as a production free-booking switch.
- A confirmed development booking can be reached from the development preview, but it is scheduled for 2026-10-12. Daily's join window starts 15 minutes before the booked start and closes 30 minutes after the end.

## Release gates

1. Make the latest `develop` commit green in CI. Required checks include backend, generated contract, frontend, lint, PostgreSQL, Redis, and dependency audit. Merge the verified commit into `main`; do not deploy an unverified SHA.
2. Provision a distinct production Redis URL. Do not point production at the development Redis or Neon database.
3. Configure Railway production secrets and non-secret settings. `backend/config/settings/guard.py` is the source of truth; at minimum it requires a strong Django key, public host and HTTPS origins, frontend base URL, Resend, Daily API key/domain/webhook secret, Eskom key, encryption keyrings, R2 private bucket, proxy count, alert recipients, refund backend, and training gate. Production also requires `DATABASE_URL` and `REDIS_URL`. Keep values in Railway, never in Git or this file.
4. Review the existing Railway staged changes before accepting them. Apply migrations against the production Neon branch before routing traffic; check health and the deployed commit. Add a production worker/beat if attendance and fulfillment tasks are to be verified.
5. Confirm Vercel Production tracks `main`, uses `frontend` as root, has production session/API URL settings, and deploys the same release commit. Verify the public site uses the production Railway URL, not the development API.
6. Provide a controlled production video-only booking path for named test users. The current `confirm-test` endpoint is intentionally disabled in production. A production trial must avoid a public free-booking switch and must not create payable tutor earnings or refund liabilities for a test session. Until that path exists, do not claim the production video trial is ready.
7. Configure the Daily webhook for the production backend's canonical endpoint, with its matching HMAC secret. Confirm signature validation and received join/leave events.

## Two-user acceptance test

1. Create the controlled test session for a near-term time, using separate tutor and student accounts. Confirm both accounts can sign in on the production site and see their respective classroom links for the same session.
2. Within the server-enforced join window, have both users open their classroom links in separate browsers or devices. Confirm distinct Daily tokens, one shared room, two visible participants, audio/video in both directions, and clean leave/rejoin.
3. Check backend logs and attendance records for signed Daily join/leave webhooks. Confirm no payment, wallet debit, refund, or tutor payout is created by this video-only trial.

The deployment is complete only after these observations are recorded with the release commit and public URLs.
