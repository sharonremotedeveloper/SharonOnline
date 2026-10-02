# Spec-Freeze Decisions D-1 .. D-12

**Updated:** 2026-10-02 · Answers marked ✅ were given by Anesu; the rest need Anesu + Sharon. Each open item has a recommendation so the answer can be a one-word "agree".

## Answered

| Ref | Decision | Consequence |
| :--- | :--- | :--- |
| D-1 ✅ | Platform-set flat retail price per currency | Phase 10 adds a price table; the ZAR rate is currently `ZAR_PER_USD` config (default 18.0). Trial lesson: **still open**. |
| D-2 ✅ | 80/20 split; platform bears gateway fees | Matches the ledger. PROJECT_CONTEXT's fixed R75 is superseded. Gateway fees post to 5030 out of the 20%. |
| D-5 ✅ | Tutor and student no-show at T+10; 5 min disconnect grace | Matches the current T+10 probe. Add the 5 min grace in Phase 9. |
| D-6 ◐ | **Gateway refund only** | Cancel window (>2h vs >24h) and tutor-cancel compensation still open. See conflict below. |

> **D-6 conflict to resolve.** "Gateway refund only" contradicts what the code does today: the Eskom outage and DEF-501 paths refund a *credit*, and D-7 (credit bundles) implies a wallet. Either (a) bundles are bought but only *unused* credits are refundable to the card, and operational failures (outage, DEF-501, tutor cancel) are refunded to the card too, or (b) wallet credit is allowed for operational failures. **Recommendation: (b)**, because partial card refunds are costly and slow, but it needs your call. Phase 10 task 10.7 depends on this.

## Open (recommendation first)

| Ref | Question | Recommendation |
| :--- | :--- | :--- |
| D-3 | Payout cadence + rail + maker-checker | Bi-weekly (matches code); bank EFT/ACB CSV export for MVP (no API cost); maker-checker **yes**, since one person should not both build and approve a payout batch. |
| D-4 | Memo SLA | 12h reminder, 24h deadline; late memo forfeits the tutor's pay for that lesson (code behaviour); memo does **not** block student escrow clearing; platform funds any apology credit. |
| D-7 | Credit bundles | Bundles of 5 / 10 / 20 at 0 / 5 / 10 % off; **no subscriptions in MVP**. |
| D-8 | Recording | Do **not** record in MVP (avoids consent/POPIA/APPI exposure and storage cost). If recorded later: 7-day retention, explicit consent. |
| D-9 | Zoom licensing | One licensed host per ~3 concurrent tutors with alternative hosts, to avoid per-tutor licence cost. Confirm with Zoom account limits. |
| D-10 | Stack | Backend Railway or Render (Docker), frontend Vercel, R2 for files, Django JWT (no Neon Auth). Domain `sharonesl.com` (already used in the R2 CDN config). |
| D-11 | Tutor vetting | Sharon interviews; TEFL certificate + SA ID document uploaded to the private vault and verified by an admin; background check done outside the platform for launch. |
| D-12 | Legal entity / VAT / POPIA officer / SARB | Needs an accountant and attorney. Not something engineering can decide. Blocks live-gateway cutover and Phase 14. |

## Engineering notes captured while doing Phase 7

- **R2 does not support presigned POST**, so uploads stay presigned PUT. The size cap is enforced by signing `Content-Length` into the URL (the client declares `size`, the server checks it against the policy cap).
- **Frontend has no token-refresh flow**, so the access token stays at 60 min. Move to 15 min in Phase 8 when refresh is built.
- The `sharon_user_role` cookie is client-set and only used for UI routing; the backend is the only security boundary.
- `.env.example` contains PayFast **sandbox** credentials (public values). Production must never reuse them; the settings guard now enforces this.
