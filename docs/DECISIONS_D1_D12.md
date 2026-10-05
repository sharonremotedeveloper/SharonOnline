# Spec-Freeze Decisions D-1 .. D-12

**Updated:** 2026-10-02 · Answers marked ✅ were given by Anesu; the rest need Anesu + Sharon. Each open item has a recommendation so the answer can be a one-word "agree".

## Answered

| Ref | Decision | Consequence |
| :--- | :--- | :--- |
| FX ✅ (2026-10-03) | EUR/JPY to ZAR valuation: admin-maintained rate table first (option C), provider feed later; block EUR/JPY checkout on a missing or >24 h old rate; capture uses the rate stamped at checkout and never fails on staleness; platform carries FX risk between payment and payout | `payments.FxRate`, `payments/services/fx.py`, `/admin/fx-rates/`. Tax treatment (capture-day vs average rate) is for the accountant (D-12). |
| D-1 ✅ | Platform-set flat retail price per currency | Implemented in Task 10.1: `payments.LessonPrice` (one row per currency, edit in admin). **Provisional launch prices: USD 9.00, EUR 8.50, ZAR 162.00, JPY 1350 - Anesu to confirm.** Trial lesson: **still open**. |
| D-2 ✅ | 80/20 split; platform bears gateway fees | Matches the ledger. PROJECT_CONTEXT's fixed R75 is superseded. Gateway fees post to 5030 out of the 20%. |
| D-5 ✅ | Tutor and student no-show at T+10; 5 min disconnect grace | Matches the current T+10 probe. Add the 5 min grace in Phase 9. |
| D-6 ✔ | **Gateway refund only; student cancel >2h free, <=2h forfeits; credits expire in 30 days; the rest as recommended in `CANCELLATION_AND_REFUNDS.md`** | Decided 2026-10-03 (Anesu: the 2 h window, 30-day expiry and "best recommendation" for reschedule / tutor cancel / late-cancel pay / outage). Implemented in Task 9.6. Open for confirmation: 30-day expiry on purchased packs, zero outage pay, breakage accounting. |
| D-8 ✅ (2026-10-04) | Recording: **lessons are not recorded in the MVP**. Sharon signed this off in writing, so the SOW M3 "7-day video purge" deliverable moves to after the MVP launch (if recording is ever added: 7-day retention, explicit consent) | Zoom meetings are created with `auto_recording: "none"` (slice Z1). No recording purge is built now; only the 90-day attendance-payload purge (slice R1). |

> **D-6 conflict (resolved: gateway refund everywhere; the student may convert a pending refund to wallet credit).** "Gateway refund only" contradicts what the code does today: the Eskom outage and DEF-501 paths refund a *credit*, and D-7 (credit bundles) implies a wallet. Either (a) bundles are bought but only *unused* credits are refundable to the card, and operational failures (outage, DEF-501, tutor cancel) are refunded to the card too, or (b) wallet credit is allowed for operational failures. **Recommendation: (b)**, because partial card refunds are costly and slow, but it needs your call. Phase 10 task 10.7 depends on this.

## Open (recommendation first)

| Ref | Question | Recommendation |
| :--- | :--- | :--- |
| D-3 | Payout cadence + rail + maker-checker | Bi-weekly (matches code); bank EFT/ACB CSV export for MVP (no API cost); maker-checker **yes**, since one person should not both build and approve a payout batch. |
| D-4 | Memo SLA | 12h reminder, 24h deadline; late memo forfeits the tutor's pay for that lesson (code behaviour); memo does **not** block student escrow clearing; platform funds any apology credit. |
| D-7 | Credit bundles | Bundles of 5 / 10 / 20 at 0 / 5 / 10 % off; **no subscriptions in MVP**. |
| D-9 | Zoom licensing | One licensed host per ~3 concurrent tutors with alternative hosts, to avoid per-tutor licence cost. Confirm with Zoom account limits. **Z1 note (2026-10-05): with the single host account the code ships today (`HostPicker` -> `ZOOM_HOST_USER_ID`, default `me`), concurrent lessons collide on one licence: LAUNCH BLOCKER until this is decided and `pick_host` allocates from a pool (`docs/ZOOM_ATTENDANCE.md`).** |
| D-10 | Stack | Backend Railway or Render (Docker), frontend Vercel, R2 for files, Django JWT (no Neon Auth). Domain `sharonesl.com` (already used in the R2 CDN config). |
| D-11 | Tutor vetting | Sharon interviews; TEFL certificate + SA ID document uploaded to the private vault and verified by an admin; background check done outside the platform for launch. |
| D-12 | Legal entity / VAT / POPIA officer / SARB | Needs an accountant and attorney. Not something engineering can decide. Blocks live-gateway cutover and Phase 14. |

## Engineering notes captured while doing Phase 7

- **R2 does not support presigned POST**, so uploads stay presigned PUT. The size cap is enforced by signing `Content-Length` into the URL (the client declares `size`, the server checks it against the policy cap).
- **Frontend has no token-refresh flow**, so the access token stays at 60 min. Move to 15 min in Phase 8 when refresh is built.
- The `sharon_user_role` cookie is client-set and only used for UI routing; the backend is the only security boundary.
- `.env.example` contains PayFast **sandbox** credentials (public values). Production must never reuse them; the settings guard now enforces this.
