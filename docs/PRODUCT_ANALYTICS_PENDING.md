# Product analytics (PostHog and others) - PENDING, UP FOR DISCUSSION

**Status: PENDING - nothing installed, tool choice not decided.** Recorded 2026-10-18 at Anesu's request.
PostHog is the leading candidate; other analytics tools are open for discussion before anything is built.

## 1. What exists today

- **No analytics or monitoring code anywhere.** No PostHog, Google Analytics, Vercel Analytics, Plausible, Mixpanel or
  Sentry in `frontend/package.json`, `frontend/src`, `backend/requirements.in` or `backend/config` (checked 2026-10-18).
- **Consent is collected but unused.** `frontend/src/components/legal/CookieBanner.tsx` stores
  `{ analytics, marketing }` in `localStorage` key `sharon_cookie_consent_v1`; no code reads it yet. Any analytics tool
  must load only after `analytics === true` and stop when the visitor withdraws consent.
- **The cookie policy already promises this shape** (`frontend/src/content/legal/policies.ts`, section 2C): optional
  "Performance & Analytics" cookies and "No Third-Party Ad Trackers". The policy must name the chosen tool(s) once decided.
- Error monitoring (Sentry) is a separate open item: Task 13.4 in `PRODUCTION_READINESS_PLAN.md`.

## 2. What we would want to learn (draft, to agree)

- **Booking funnel:** tutors page -> tutor profile -> slot picked -> checkout -> confirmed, with drop-off per step and
  per country (Japan, Korea, Europe, South Africa).
- **Lessons:** classroom joined, video connection failures, lesson completed, memo read, review left.
- **Tutor funnel:** register -> application steps 1-5 -> submitted -> approved -> training done -> first lesson.
- **Phones vs desktop:** where mobile users struggle (follows the 2026-10 mobile UX work).
- **Retention:** students who book a second lesson within 14 / 30 days.

## 3. Options to discuss

| Tool | Good for | Notes |
| :--- | :--- | :--- |
| **PostHog** (leading candidate) | Product analytics, funnels, session replay, feature flags, A/B tests in one tool | Free tier is generous; EU cloud region available (GDPR); can be routed through our own domain so ad blockers do not drop events. Session replay must mask inputs and be off on payment, classroom and ID-upload pages. |
| Vercel Web Analytics / Speed Insights | Page views and real-user performance (Core Web Vitals) | One-click on Vercel, cookieless; no funnels or user journeys. Could sit beside PostHog. |
| Plausible / Umami | Simple, cookieless traffic stats | Privacy-friendly and may need no consent banner; no product funnels. |
| Google Analytics 4 | Marketing attribution, Google Ads | Heaviest privacy burden (consent mode, data transfers); conflicts with the "no ad trackers" wording unless the policy changes. |
| Sentry | Errors and crashes, frontend and backend | Not analytics, but usually set up at the same time; already planned as Task 13.4. |

## 4. Rules any choice must follow

1. **Consent first:** no analytics script or cookie before the visitor opts in via the existing banner (POPIA, GDPR,
   Japan APPI). Cookieless tools still need the privacy policy updated.
2. **No personal data in events:** use the internal user UUID, never e-mail, name or phone. Never send lesson content,
   memos, private tutor notes, reviews, bank details, ID documents or payment data.
3. **Exclusions:** no session replay or autocapture on checkout/payment, the Daily.co classroom, tutor ID/TEFL uploads,
   payout settings and admin pages.
4. **Security headers:** the analytics domain must be allowed in the Content-Security-Policy when CSP is added, and in
   the Permissions-Policy where relevant (see the Daily.co iframe incident).
5. **Data location and retention:** prefer EU hosting; set a retention period; add the vendor to the privacy policy and
   any data-processing records.
6. **Server-side events** for facts the browser cannot be trusted with (payment captured, lesson completed): send from
   Django/Celery, keyed by user UUID, never blocking the request if the vendor is down.

## 5. Open questions for Anesu

1. PostHog alone, or PostHog + Vercel Speed Insights (performance), or a cookieless tool only?
2. Do we want session replay at all (useful for UX, heavier privacy duty)?
3. EU or US data region?
4. Will Google Ads / marketing attribution be needed soon (decides whether GA4 is on the table)?
5. Who looks at the dashboards, and which 3-5 numbers matter most at launch?

## 6. Proposed first step (once decided)

Frontend PostHog behind the consent banner, events for the booking funnel only, EU region, inputs masked, replay off
or limited to public pages; privacy and cookie policy updated in the same change; then server-side events for payments
and completed lessons.
