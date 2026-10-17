# Mobile UI/UX audit and fix plan

**Date:** 2026-10-17. **Auditor:** Claude, using the `ui-ux-pro-max` rule set (`references/quick-reference.md`).
**Device:** real Redmi (model 23124RN87C, Android, Chrome), viewport **360 x 800 CSS px**, driven over wireless ADB + Chrome DevTools against **production** (`topteacheracademy.com`, `main` `37bd916`).
**Coverage:** 48 of 51 routes (public 17, student 12, tutor 11, admin 8). Not audited: `student/checkout/return`, `student/checkout/cancel`, `video-trial/[id]` (need a live payment / trial).

Status labels: every item below is **Implemented in code: no** unless stated. Nothing here has been changed yet.

## 1. How it was measured

Per page, in the real phone browser: horizontal overflow, tap targets under 44 px, text under 12 px, form inputs under 16 px,
images without `alt`, sticky/fixed elements covering >= 12 % of the screen, nested scroll regions, console errors, main-thread
script time, plus one screenshot per screen of scrolling.

**What is already good (keep it):** no horizontal page overflow on any page; no text under 12 px; no form input under 16 px
(no iOS zoom-on-focus); no console errors; images have `alt`; skip link present; primary buttons are 44 px+.

## 2. Global issues (fix once, every page benefits)

| # | Issue | Evidence | Rule | Fix (mobile only, desktop unchanged) |
|---|---|---|---|---|
| G1 | **Marketing footer is 2 to 3 screens tall on phones**, on every page incl. signed-in student/tutor/admin pages; on short pages it is longer than the content | every screenshot set | `content-priority`, `touch-density` | Footer link groups in a 2-column grid below `sm`, shorter blurb; **compact footer** (copyright + legal links in one row) inside `student/`, `teacher/`, `admin/` and auth pages |
| G2 | **No app navigation for signed-in users on phones.** Student/tutor areas use the public header; moving between Dashboard, Schedule, Wallet needs the avatar menu every time | student + tutor runs | `bottom-nav-limit`, `nav-hierarchy` | `lg:hidden` **bottom tab bar** (max 5: Home, Schedule, Book/Students, Vocabulary/Wallet, Profile) for student and tutor roles; hidden on desktop |
| G3 | **Page header pattern is cramped**: back button + mono "badge" + small label + title squeeze into ~280 px and wrap into 2-4 lines ("AVAILABILITY PLANNER / Recurring Weekly Matrix", "BK-5CDEC1B2 / Synchronous Lesson Pad", "ZAR CLEARING LEDGER") | tutor schedule, wallet, classroom, memo; admin pages | `compact-label-overflow`, `heading-line-balance` | One shared `PageHeader` component: back button + title on one row, eyebrow badge above; hide the secondary label below `sm`; `text-balance` on titles |
| G4 | **Cards nested in cards** (page > white card > tinted card > card) waste 30-50 px of width on a 360 px screen | classroom, memo, schedule, payout | `touch-density` | Drop outer card padding/border below `sm` (`p-3 sm:p-6`, `border-0 sm:border`) in the shared card wrappers |
| G5 | **Numeric fields open the text keyboard** (account number, branch code, ID number, 6-digit codes): `inputMode` is used only twice in the whole app | code grep + payout page | `input-type-keyboard`, `autofill-support` | `inputMode="numeric"`, `autoComplete="one-time-code"` for codes, `autoComplete` on name/email/password everywhere |
| G6 | **Cookie banner covers ~29 % of the first screen** and sits over the primary button on sign-in | sign-in (fresh browser) | `focus-not-obscured` | Compact one-line banner on phones (text + 2 buttons in a row; "Choose" behind a link) |
| G7 | **Signed-in users still see Sign in / Create account pages** (no redirect) | `/login`, `/register` while signed in | `back-behavior` | Redirect authenticated users to their dashboard (in `proxy.ts`, all widths) |
| G8 | Developer jargon on user screens ("Capture FX Context", "Immutable snapshots", "Synchronous Lesson Pad", "Executing an adjudication decision atomically...", "Command Center") | tutor wallet, classroom, admin | `content-priority` | Plain-language copy pass (all widths; copy only) |

## 3. Page-specific issues

### Public
| # | Page | Issue | Fix |
|---|---|---|---|
| P1 | Home | **~19 screens long.** Hero trust bullets repeated in the yellow strip; full pricing block repeats `/pricing`; how-it-works repeats `/how-it-works`; large section gaps (`mt-20`) | Mobile: remove the duplicate trust strip, show 1 pricing teaser card + link instead of all packs, collapse "Why South African tutors" to 2 cards + "See more", section gap `mt-12 sm:mt-20`. Target <= 10 screens |
| P2 | Home | Tutor portrait is ~1.3 screens tall per card on phones; price + View button fall below the fold | `aspect-[4/3] sm:aspect-[4/5]` on the card photo (desktop keeps the portrait) |
| P3 | Home | Goal chips wrap awkwardly ("Daily / Conversation"); goal checklist 2-column too narrow ("Email / etiquette"); "Find tutors for this goal" wraps in its button | Chips: horizontal scroll row with snap on phones; checklist 1 column below `sm`; shorter button label on phones |
| P4 | Tutors list | **Filters take ~1.5 screens before the first tutor** (accent, 8 topic chips, 2 toggles) | Phone: "Filters (n)" button opening a bottom sheet; search stays visible; desktop keeps the panel |
| P5 | Tutor profile / Book | **Availability takes ~3.3 s** (`GET /bookings/slots/<id>/`, measured 3.27 s and 3.30 s for one tutor) so phones show a long skeleton | Backend: profile the slot generator (one tutor should be < 300 ms); add caching. All devices |
| P6 | Legal pages | Breadcrumb wraps into 4 lines; policy nav + "On this page" list take ~1.5 screens before the text; a sticky panel covers 42-64 % of the screen | Phone: hide breadcrumb middle items, collapse policy nav into a select, TOC into a `<details>`; sticky only from `lg` |
| P7 | Support | Placeholder cut off ("Question about PayPal che…"); "24/7 Dedicated Platform Support" claim | Shorter placeholders; copy check |
| P8 | Materials | Same filter-panel problem as P4 (category + level chips before content) | Same filter sheet component as P4 |
| P9 | Register | Timezone and **Country as free text** (defaults "US" for a Mauritius user); role toggle wraps | Country `select` (ISO list) + timezone `select` prefilled from the browser; shorter toggle labels on phones |

### Student
| # | Page | Issue | Fix |
|---|---|---|---|
| S1 | Dashboard | Section tabs wrap into a vertical list; card headers squeeze links into 4 lines ("Full / Lesson / Archive / (0)") | Tabs: horizontal scroll row; card header link moves under the title below `sm` |
| S2 | Lesson history | **Cards are cramped**: name, accent pill and date fight for ~150 px so the date wraps into 4 lines; empty "CEFR" badge; "No memo available" on every row | Stacked mobile layout (avatar + name row, then date row, then status); hide empty CEFR badge |
| S3 | Schedule | Cancelled/disputed lessons dominate; no Upcoming / Past split | Segmented control "Upcoming / Past" (all widths fine; default Upcoming) |
| S4 | Profile | Country free text ("US"); CEFR select truncated; Account ID UUID shown and wrapping beside the Save button (Save wraps to 2 lines) | Country select; remove/shorten Account ID; full-width sticky Save bar on phones |
| S5 | Classroom | Layout toggle ("Dual-Pane Stage") is meaningless on phones (no split); header cramped (G3); nested cards (G4) | Hide the layout toggle below `lg`; header + card fixes. (Video frame / status bar fixes already shipped: ERR-549) |
| S6 | Review | "Skip for now" squeezed to 3 lines beside the submit button; review is offered for a **disputed** lesson | Stack buttons full-width on phones; only offer review for completed lessons (logic, all widths) |

### Tutor
| # | Page | Issue | Fix |
|---|---|---|---|
| T1 | **Availability (schedule)** | **The weekly hours matrix shows 1.5 days on a phone**; every row needs horizontal scrolling; this is the tutor's core task | Phone: **day picker** (Mon...Sun pills) + one day's hour list as full-width toggles; desktop keeps the matrix |
| T2 | Training module | **Markdown `###` headings shown as raw text** (renderer does not handle `###`) | Fix the renderer (all widths); content shows "(provisional)" to tutors: owner copy decision |
| T3 | Memo | Full booking UUID pill wraps; long form with no sticky submit; submit label wraps | Short `BK-` ref only; sticky full-width submit bar on phones; autosave draft (`form-autosave`) |
| T4 | Wallet | "R0,00" and "R0.00 ZAR" formats on the same page; jargon (G8) | One money formatter; copy pass |
| T5 | Payout settings | Numeric keyboards (G5); code input truncated beside its button; placeholder "e.g. Sharon Mupesa" | Stack code input + button on phones; neutral placeholder |
| T6 | Dashboard | "Today's Class Schedule" header + pill cramped | G3/S1 header fix |

### Admin (staff mostly use desktop: lower priority)
| # | Page | Issue | Fix |
|---|---|---|---|
| A1 | Vetting | **Rubric 1-5 buttons ~32 px** (21 small targets); **raw LaTeX `$\ge 3$` / `$\ge 12/20$` in the rubric text** (all widths) | 44 px score buttons; plain text ">= 3" |
| A2 | All admin | Sidebar becomes a clipped horizontal tab strip ("Tutor Vett…") with a visible scrollbar; public footer below | Admin section select/drawer on phones; compact footer (G1) |
| A3 | Roster / ledger / payouts | Wide tables scroll sideways inside cards | Card list below `md` for tables (desktop keeps tables) |
| A4 | Disputes | Destructive actions ("Release 100% to Tutor", "100% Refund") styled like neutral buttons, no confirm | Danger styling + confirm step (all widths) |

## 4. Fix plan (in order)

Each phase is one small commit set on `develop`, verified, then promoted on approval.

1. **[x] Phase 1 - global shell (G1, G2, G6, G7)** - *Implemented, tested (362 frontend tests), deployed (develop `c84827c`, main `36eb63e`), verified on the Redmi at 360 px and at 1440 px emulation, and on the live site (admin redirect, compact footer).* compact footer for app areas + 2-column public footer on phones; student/tutor bottom tab bar (`lg:hidden`); compact cookie banner; signed-in redirect off auth pages.
2. **[x] Phase 2 - tutor core (T1, T2, T3, A1)** - *Implemented, tested (366 frontend tests), deployed (develop `15c6aa9`, main `98d5859`); verified on the Redmi at 360 px and at 1440 px (local build), live rubric re-checked on the phone (44x44 buttons, plain text).* availability day-picker on phones; markdown heading fix; memo sticky submit + short ref; rubric text.
3. **Phase 3 - discovery (P1-P4, P8, P5):** shorter mobile home, card photo ratio, chips, filter bottom sheet for tutors/materials; slot API performance (backend).
4. **Phase 4 - forms and keyboards (G5, P9, S4, T5):** `inputMode`/`autoComplete`, country/timezone selects, sticky save bars, stacked code fields.
5. **Phase 5 - polish (G3, G4, G8, S1-S3, S5, S6, T4, T6, P6, P7, A2-A4):** shared `PageHeader`, card padding, copy pass, history card layout, legal page collapse, admin tables/nav, dispute confirmations.

## 5. Not breaking desktop

- **Mobile-first, additive only:** phone styles go in the base classes; today's desktop look is preserved by putting it behind `sm:`/`md:`/`lg:` prefixes. New mobile-only components are wrapped in `lg:hidden` (or `md:hidden`); the existing desktop components get `hidden lg:block` instead of being replaced.
- **Same data and handlers:** mobile variants reuse the existing data hooks and submit functions; no API or state changes except the listed logic fixes (G7, S6, T2, A4, P5).
- **Every phase is checked at 360 px (the Redmi) and at 1440 px desktop** with before/after screenshots of each touched page, plus `npm run lint`, `npm test`, `tsc`, CI, and the phone audit script re-run (no new overflow, small targets or console errors).
- Promotion to `main` only after both widths look right.

## 6. Non-mobile defects found during the audit

- Training markdown `###` not rendered (T2); vetting rubric shows raw LaTeX (A1).
- Slot availability API ~3.3 s for a single tutor (P5).
- Lesson review offered for a disputed booking (S6).
- Price shown as $9.00 on the home hero and $8.00 for the single-lesson pack on the same page (open owner pricing decision).
- Test tutor profile says "Math Teacher / Maths", "Teaches from United States", stock photo (data, not code).
