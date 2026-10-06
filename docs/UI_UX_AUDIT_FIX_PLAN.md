# UI/UX audit fix plan (frontend only)

Source: the 2026-10-07 two-agent audit (live browser + skill rules). Branch: `feature/landing-audit-fixes`.
Rules: frontend only; one commit per phase so Anesu can roll back; run `npm run lint`, `npm test`, `npm run build` before each commit; no purple, no green/teal anywhere (warm palette: cocoa, cream, orange, sun yellow, coral, peach, sky).

## Roles
| Agent | Job | Edits code? |
| :--- | :--- | :--- |
| Fixer | Executes phases 0-8 below, commits per phase, ticks the checklist | yes |
| Skills reviewer | Reads the ui-ux-pro-max skill (and other installed UI skills), writes the compliance checklist, then reviews each phase's diff against it and reports pass/fail | no |
| Project manager | Final gate: checks every item below is done and re-verified, runs the responsive + full-flow sweeps, signs off or sends items back | no (reports only) |

## Colour decisions (apply in phase 0, once)
One token per role, all text pairs >= 4.5:1 (large text / UI borders >= 3:1), measured not eyeballed.
- **Primary action**: cocoa pill, white text. Used for every main CTA (public, student, teacher, admin).
- **Accent**: sun yellow for highlights and chips. Text on sun is always `ink`, never white or orange.
- **Link / emphasis text**: `primary` orange (#C2410C) on cream or white only. Never on sun, sky or peach.
- **Success / warning / info**: new warm tokens (`success`, `warning`, `info` each with `-surface` and a text colour). No emerald, amber, green, teal, or default blue. Fixer picks hues, must record measured ratios.
- **Error**: `error` token; keep visually distinct from coral and orange (use icon + text, not colour alone).
- **Gold**: never as text or icon on light backgrounds (stars use a darker gold token or ink outline).
- **Borders**: form controls >= 3:1 (new `border-strong` token); decorative dividers can stay light.
- **Focus ring**: 2px+, visible on cream, white, cocoa and coloured blocks (`.on-dark` and coloured-block variants).
- **Dark surfaces**: one family only (cocoa). Classroom stage moves from navy/slate to cocoa.

## Phases
0. **Tokens**: add success/warning/info/border-strong/star tokens; remove or alias duplicates; define the missing `bg-surface`. Document in `tailwind.config.ts` comment.
1. **Critical**:
   - Classroom (`VideoSdkClassroom.tsx`): readable "Enter Classroom" (>= 4.5), cocoa stage instead of navy/slate, 44px targets.
   - Admin: badges and buttons with white on yellow/amber/rose/coral fixed (`ui/Badge.tsx`, `admin/dashboard`, `admin/layout`, vetting pages).
   - Undefined `bg-surface` (`vetting/page.tsx:615`, `NotificationDrawer.tsx:99,187`, `NotificationPreferencesModal.tsx:99`): real opaque background.
   - Forms: `htmlFor`/`id` on login, register, support, review; `aria-describedby` + `role="alert"` on errors.
   - Green: `teacher/apply/page.tsx` hex greens, `teacher/dashboard/page.tsx:168` teal gradient, all `emerald-*` classes (about 170) mapped to the new tokens.
2. **Contrast sweep**: muted text (about 21 places) to >= 4.5; "No times"/disabled text; placeholders; gold-on-light; orange-on-sun/sky/peach.
3. **Controls**: input/select/checkbox borders to `border-strong`; inputs 16px on phones; focus rings fixed where `focus:outline-none` has no replacement (`FlashcardDeck:208`, others found by grep); footer ring verified live.
4. **Button system**: collapse the 6 solid-button colours to primary (cocoa), secondary (outline), danger, and accent chip; consistent radius; visible hover.
5. **Touch and type**: targets under 44px (classroom, register, legal, materials, teacher schedule); 12px text raised to 14px+ for body-level content.
6. **Content and polish**: "Add 1 Credits" plurals, rating shown as 5.0 for 4.98, email-banner shown to staff, jargon, page margins, `LessonScheduler.tsx:265` `text-success`, `StarRating`, `materials/[slug]:286`, `review:190`, `ReviewRubricModal:119`, OG image colours.
7. **Behaviour**: `/teacher/power-guard` error state with heading and retry; stop repeated 401 `/api/session/me` console noise for anonymous visitors (frontend handling only).
8. **Verification**: re-run the live contrast crawler and static grep (no green/emerald/teal/purple hex, no undefined token classes), overflow sweep, keyboard pass.

## Acceptance (project manager checks all)
- [x] Zero contrast failures *(Phase 8 crawler, 6 widths x public/student/teacher/admin: 0 real failures; 7 flagged items are text on gradients/photos the crawler cannot sample, hand-measured: white on #5E3A25 9.96, sun-soft on cocoa 11.18, white on black/80 photo scrim >= 12.6; classroom not crawled live (needs a Zoom SDK session))* on the crawler, all roles (public, student, teacher, admin, classroom).
- [x] No green/teal/purple/emerald/navy *(static grep 0 hits for palette classes; 0 undefined token classes; remaining raw hex only in layout themeColor, selection colour and OG image)* left; no undefined Tailwind token classes.
- [x] One primary button style *(Button.tsx 4 variants; control borders measured 4.69:1 on white)*; every control border >= 3:1; focus visible everywhere.
- [x] Every label has a linked control *(crawler: 0 unlabelled controls, 0 duplicate ids; errors use role=alert and aria-describedby)*; errors announced.
- [x] No horizontal overflow *(crawler: 0 overflow at 320/375/768/1024/1280/1440 on 38 routes)* at 320, 375, 768, 1024, 1280, 1440 on public, student, teacher, admin pages.
- [ ] Full flows work at phone and desktop widths: sign in, browse tutors, tutor profile, pick a time, reserve, checkout, wallet, dashboard, account menu, notifications, tutor schedule, admin dashboard.
- [x] `npm run lint` *(lint 0 warnings, 217 tests pass, build ok)* (zero warnings), `npm test`, `npm run build` pass.
- [ ] Skills reviewer reports all phases compliant.
- [ ] Known non-frontend items listed as out of scope (lesson price vs pack price seed data, empty materials, real photos/testimonials, ja/ko localisation, CSP).
