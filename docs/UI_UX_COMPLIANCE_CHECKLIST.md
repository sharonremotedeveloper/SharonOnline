# UI/UX compliance checklist (Sharon Online frontend)

Written 2026-10-07 by the skills reviewer for `docs/UI_UX_AUDIT_FIX_PLAN.md` (branch `feature/landing-audit-fixes`).

**Sources.** The installed `ui-ux-pro-max` skill (`SKILL.md`, `references/quick-reference.md`, `references/pro-rules.md`, and `scripts/search.py` domains `ux`, `color`, `typography`, `landing`, `style`, plus `--design-system` for an ESL tutoring marketplace). It is the only UI/UX skill installed under `~/.claude/skills`; no installed plugin provides another UI skill (only `cloudflare` marketplaces). The Claude-bundled `artifact-design` and `dataviz` skills are not used here (they target generated artifacts and charts).

**Hues are ours, rules are the skill's.** The skill's recommended palettes (teal `#0D9488`, purple `#7C3AED`, green accents) were rejected by Anesu and are not used. Palette: cocoa, cream, orange, sun yellow, coral, peach, sky. No purple, green, teal, emerald or navy anywhere.

**Skill-vs-web notes.** The skill's 44pt/48dp touch rule is a native rule; for web it cites WCAG 2.2 SC 2.5.8 (24x24 CSS px minimum). The project plan chose 44px as the target. This checklist uses **44px = target (pass), 24px = hard floor (WCAG fail below)**. The skill's "16px body on mobile" is applied as: inputs 16px on phones (stops iOS zoom), body copy 16px, secondary copy 14px minimum.

How to read each rule: `Rule` | `Source` | `Check` | `Pass`. "Grep" commands run from `Project-files/frontend/src`. "Live" means a browser check (Playwright/Chrome MCP) at the stated width.

---

## A. Colour roles and pairings

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| A1 | Normal text (below 18.66px bold / 24px regular) has contrast >= 4.5:1 against its real background | ui-ux `color-contrast`, `color-accessible-pairs`, `contrast-readability` | Live: run the contrast crawler on every route per role; static: use the pairings table below | 0 failures |
| A2 | Large text (>= 24px, or >= 18.66px bold) >= 3:1 | `color-contrast` | Crawler | 0 failures |
| A3 | Meaningful icons, form-control borders, focus rings, chart marks >= 3:1 against adjacent colour | `pro-rules` "Icon Contrast", `focus-appearance`, `contrast-data` | Compute with the table; live computed-style check on `input`, `select`, `textarea`, `[type=checkbox]` borders | 0 failures |
| A4 | One semantic token per role (primary, secondary, accent, success, warning, info, error, surface, border, border-strong, focus). Components use tokens, not raw hex or default Tailwind palettes | `color-semantic`, `color-palette-from-product`, "Raw hex in components" anti-pattern | Grep: `grep -rEn "#[0-9A-Fa-f]{6}" . --include=*.tsx --include=*.ts` outside `tailwind.config.ts` and `globals.css` (OG image/PDF exceptions listed in the commit) | 0 raw hex in components; 0 `bg-\|text-\|border-` of `emerald\|green\|teal\|slate\|amber\|yellow\|rose\|blue\|red\|gray\|zinc\|neutral\|stone` plus a number |
| A5 | No purple/violet/indigo/fuchsia, no green/teal/emerald, no navy/slate-blue anywhere (CSS, TSX, SVG, OG image, email templates in the frontend) | Project plan, Anesu's decision | Grep both class names and hex (`#0e6f68`, `#0B3530`, `#0E2421`, `#f0f4f0`, `#657a73`, `#536963`, `#C3D7C8`, any hue 90-200 degrees) | 0 hits |
| A6 | Every Tailwind colour class resolves to a defined token (no silent no-op classes such as `bg-surface`, `text-success` if undefined) | `color-semantic` | Build and grep classes against `tailwind.config.ts`; or add `safelist` check script; live: computed `background-color` of modals/drawers is opaque (alpha 1) | 0 undefined classes; modals/drawers opaque |
| A7 | Status (success, warning, error, info) never relies on colour alone: icon and/or text label accompany it | `color-not-only`, `color-not-decorative-only` | Review every `Badge`, banner, form error, status chip; live: view in grayscale (`filter: grayscale(1)`) and confirm each status is still readable | 100% of statuses |
| A8 | Status text colours (success, warning, error, info) reach >= 4.5:1 on their own `-surface` and on white and cream | `contrast-feedback` | Table below; fixer records measured ratios in `tailwind.config.ts` comment | >= 4.5 on all three backgrounds |
| A9 | Disabled text and placeholder text are still >= 4.5:1 (WCAG exempts disabled, but project plan requires it; placeholders are not exempt) | `contrast-readability`; plan phase 2 | Crawler; grep `placeholder:` classes | Placeholder >= 4.5 on its field background; disabled >= 3:1 and clearly distinct |
| A10 | Gold/star colour is never text or a lone icon on light backgrounds (needs 3:1 as an icon; `gold` is 1.98 on cream) | `pro-rules` "Icon Contrast" | Grep `text-gold`, `text-accent-`, `fill-gold`; stars use a darker token (>= 3:1) or an ink outline | 0 gold text; star fill >= 3:1 or outlined |
| A11 | Text on sun yellow is `ink` or `cocoa`, never white, orange, coral or gold | Plan colour decisions | Grep `bg-(sun\|accent)` lines for `text-white\|text-primary\|text-coral\|text-gold` | 0 hits |
| A12 | Orange `primary` is text/link colour only on white, cream or cream-surface; never on sun, sky, peach, coral, cream-deep | Plan | Grep + table below | 0 hits |
| A13 | One dark family (cocoa) only: classroom stage, footer, admin shell, dark cards | `consistency`, `dark-mode-pairing` | Grep `slate-\|neutral-9\|bg-black\|gray-9`; live classroom screenshot | 0 non-cocoa dark surfaces |
| A14 | Scrims and overlays are measured against the real background and keep foreground >= 4.5 | `pro-rules` "Scrim and modal legibility" | Crawl open Modal, NotificationDrawer, cookie bar | Pass |
| A15 | If a dark variant is shipped (cocoa blocks count), its text pairs are checked separately: white/cream on cocoa >= 4.5 | `color-dark-mode`, `pro-rules` Light/Dark | Table below | Pass |
| A16 | Decorative dividers may stay light (< 3:1) only if they are not the sole boundary of an interactive control | `pro-rules` "Border and divider visibility" | Review cards that are clickable: border or shadow or hover state present | Pass |

### Colour pairings: allowed and forbidden (exact hex from `frontend/tailwind.config.ts`)

Ratios computed with the WCAG relative-luminance formula (script kept in the reviewer's scratchpad, reproducible: `L = 0.2126R + 0.7152G + 0.0722B` on linearised sRGB, ratio `(L1+0.05)/(L2+0.05)`). Rows = foreground, columns = background. **Bold** = passes 4.5 (text). Plain = fails text; the 3-4.49 range passes only for large text / UI.

| Foreground (hex) | white `#FFFFFF` | cream `#FFF8F2` | cream-deep `#F4E7DA` | cream-surface `#FFF4EA` | cocoa `#4A2C1A` | sun `#FFDE3D` | sun-soft `#FFF3A8` | coral `#FF6B4A` | coral-soft `#FFD6CB` | sky `#9ED8FF` | sky-soft `#DDF1FF` | peach `#FFD9C4` | peach-soft `#FFEDE2` | primary `#C2410C` |
| :- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| white `#FFFFFF` | 1.00 | 1.05 | 1.21 | 1.08 | **12.60** | 1.33 | 1.13 | 2.82 | 1.33 | 1.53 | 1.16 | 1.31 | 1.14 | **5.18** |
| ink `#2D2521` | **15.02** | **14.28** | **12.37** | **13.86** | 1.19 | **11.28** | **13.33** | **5.33** | **11.25** | **9.81** | **12.95** | **11.43** | **13.21** | 2.90 |
| ink-muted/500 `#6B5B53` | **6.47** | **6.15** | **5.33** | **5.97** | 1.95 | **4.86** | **5.74** | 2.30 | 4.85 (**ok**) | 4.23 | **5.58** | **4.92** | **5.69** | 1.25 |
| ink-faint/light/400 `#8A746A` | 4.39 | 4.17 | 3.61 | 4.05 | 2.87 | 3.29 | 3.89 | 1.56 | 3.29 | 2.87 | 3.78 | 3.34 | 3.86 | 1.18 |
| ink-300 `#B8A89F` | 2.30 | 2.18 | 1.89 | 2.12 | **5.48** | 1.73 | 2.04 | 1.23 | 1.72 | 1.50 | 1.98 | 1.75 | 2.02 | 2.25 |
| cocoa `#4A2C1A` | **12.60** | **11.98** | **10.38** | **11.63** | 1.00 | **9.46** | **11.18** | 4.47 | **9.44** | **8.23** | **10.86** | **9.59** | **11.08** | 2.43 |
| primary orange `#C2410C` | **5.18** | **4.92** | 4.26 | **4.78** | 2.43 | 3.89 | **4.60** | 1.84 | 3.88 | 3.38 | 4.46 | 3.94 | **4.55** | 1.00 |
| primary-hover `#9A3412` | **7.31** | **6.95** | **6.02** | **6.74** | 1.72 | **5.49** | **6.49** | 2.59 | **5.47** | **4.77** | **6.30** | **5.56** | **6.42** | 1.41 |
| terracotta `#A94332` | **5.94** | **5.65** | **4.89** | **5.48** | 2.12 | 4.46 | **5.27** | 2.11 | 4.45 | 3.88 | **5.12** | **4.52** | **5.22** | 1.15 |
| error `#B83232` | **5.93** | **5.64** | **4.88** | **5.47** | 2.12 | 4.45 | **5.26** | 2.11 | 4.44 | 3.88 | **5.11** | **4.51** | **5.22** | 1.15 |
| success `#52705A` (grey-green, see note) | **5.49** | **5.22** | **4.52** | **5.07** | 2.29 | 4.12 | **4.87** | 1.95 | 4.11 | 3.59 | **4.73** | 4.18 | **4.83** | 1.06 |
| gold `#E7A83E` | 2.09 | 1.98 | 1.72 | 1.92 | **6.04** | 1.57 | 1.85 | 1.35 | 1.56 | 1.36 | 1.80 | 1.59 | 1.83 | 2.48 |
| coral `#FF6B4A` | 2.82 | 2.68 | 2.32 | 2.60 | 4.47 | 2.12 | 2.50 | 1.00 | 2.11 | 1.84 | 2.43 | 2.14 | 2.48 | 1.84 |
| sun `#FFDE3D` | 1.33 | 1.27 | 1.10 | 1.23 | **9.46** | 1.00 | 1.18 | 2.12 | 1.00 | 1.15 | 1.15 | 1.01 | 1.17 | 3.89 |
| sky `#9ED8FF` | 1.53 | 1.45 | 1.26 | 1.41 | **8.23** | 1.15 | 1.36 | 1.84 | 1.15 | 1.00 | 1.32 | 1.16 | 1.35 | 3.38 |

(Row/column values for `ink-muted` on coral-soft: 4.85 passes. Surfaces tinted for status: `error-surface #FDF0EE`, `success-surface #EEF3EC`, `gold-surface #FAF0DC`, `cocoa-surface #FFF6CC` all give ink 13.3-13.8, cocoa 11.1-11.6, ink-muted 5.7-5.95, primary 4.58-4.76, error 5.24-5.47, success 4.85-5.05.)

#### Allowed text/background pairs (use these)

| Use | Text on background | Ratio |
| :- | :- | :-: |
| Body / headings, everywhere | ink on white, cream, cream-surface, cream-deep | 12.4-15.0 |
| Secondary text, captions | ink-muted `#6B5B53` on white, cream, cream-surface, cream-deep, sun, sun-soft, peach, peach-soft, sky-soft | 4.86-6.47 |
| Primary CTA | white on cocoa (plan: cocoa pill) | 12.60 |
| Orange-button alternative if used | white on primary `#C2410C` | 5.18 |
| Link / emphasis | primary `#C2410C` on white, cream, cream-surface (also sun-soft 4.60, peach-soft 4.55) | 4.55-5.18 |
| Hover link | primary-hover `#9A3412` on any light surface | 4.77-7.31 |
| Accent chip / highlight | ink or cocoa on sun `#FFDE3D` | 9.46 / 11.28 |
| Coloured blocks | ink on coral `#FF6B4A` 5.33; ink or cocoa on sky 9.81 / 8.23; ink or cocoa on peach 11.43 / 9.59; ink on coral-soft 11.25 | all pass |
| On cocoa (dark) | white 12.60, cream-deep `#F4E7DA`, sun 9.46, sky 8.23, gold 6.04, ink-300 5.48, accent-600 `#C79B00` 4.87 | all pass |
| Error text | error `#B83232` on white, cream, error-surface | 5.47-5.93 |
| Gold as ornament only | gold on cocoa 6.04 | ok as decoration or star on dark |

#### Forbidden pairs (fail text contrast; any use is a bug)

| Pair | Ratio | Why / fix |
| :- | :-: | :- |
| white on sun, sky, peach, sun-soft, sky-soft, cream, any `-soft` | 1.05-1.53 | Use ink |
| white on coral `#FF6B4A` | 2.82 | Use ink on coral (5.33) or switch to cocoa button |
| white on gold `#E7A83E` / amber | 2.09 | Use ink on gold; or cocoa text on gold 6.04 |
| ink on primary orange | 2.90 | Use white on primary |
| cocoa on coral | 4.47 | Misses 4.5 by 0.03; use ink on coral |
| primary orange on sun | 3.89 | Large text only; use cocoa or ink |
| primary orange on sky | 3.38 | Do not use |
| primary orange on peach | 3.94 | Do not use |
| primary orange on coral-soft | 3.88 | Do not use |
| primary orange on cream-deep `#F4E7DA` | 4.26 | Fails text; use primary-hover (6.02) |
| primary orange on sky-soft | 4.46 | Misses by 0.04; use primary-hover (6.30) |
| ink-muted on coral | 2.30 | Do not use |
| ink-muted on sky `#9ED8FF` | 4.23 | Fails; use ink (9.81) |
| **ink-faint/ink-light/ink-400 `#8A746A` as text on any surface** | 4.39 white, 4.17 cream, <=4.05 others | Fails 4.5 everywhere. Text must be ink-muted `#6B5B53` or darker. Reserve `#8A746A` for borders/icons (>= 3:1 on white/cream) |
| ink-300 `#B8A89F` as text on light | 1.89-2.30 | Decoration only; legal only on cocoa (5.48) |
| gold `#E7A83E`, gold-bright `#D4A84B`, accent-600 `#C79B00`, sun, sky, coral as text on white/cream | 1.27-2.82 | Never text on light; stars: darker token or outline |
| terracotta/error/success on sun, coral-soft, sky | 3.58-4.46 | Fails text; use on white/cream/surfaces only |
| cocoa-border `#EFE0A0`, divider `#E4D3C6`, cream-300 as a **control** border | 1.26-1.46 | Decorative only; controls need border-strong |
| Current control border `#D8B7A5` (Button secondary, Input) | 1.87 white / 1.78 cream | **Fails 3:1** for form controls |
| Candidate `border-strong` `#8A746A` | 4.39 white / 4.17 cream / 3.61 cream-deep | Passes 3:1 on all light surfaces; recommended value |

Note on `success #52705A`: it measures fine (5.49 on white) but its hue is a grey-green. The plan says "no green"; the fixer must pick a warm success hue (e.g. a deep sky-blue or ink/cocoa with a check icon) and re-measure. Same for `Badge.tsx`'s border `#C3D7C8` (green).

---

## B. Accessibility

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| B1 | Every interactive element shows a visible focus indicator >= 2px, >= 3:1 against its surroundings, not clipped | `focus-states`, `focus-appearance` | Live keyboard Tab pass across each page type (public, auth, student, teacher, admin, classroom); grep `focus:outline-none` and `outline-none` | Every `focus:outline-none` has a `focus-visible:` ring/outline replacement on the same element; 0 exceptions (known: `FlashcardDeck.tsx:208`, `review/page.tsx:190`, `ReviewRubricModal.tsx:119`, `admin/teachers/page.tsx:84`) |
| B2 | Focus ring colour works on every surface: orange on cream/white; yellow on cocoa (`.on-dark`); cocoa ring on sun/coral/sky blocks (orange on sun only 3.89) | `focus-appearance`, plan | Live: Tab to a link inside each coloured block, screenshot, measure ring vs adjacent pixel | >= 3:1 everywhere; `.on-dark` applied to all cocoa areas |
| B3 | Focused element is never hidden by sticky header, cookie bar or drawers | `focus-not-obscured` (WCAG 2.2 AA) | Live: Tab down a long page with the cookie bar and sticky header present; `scroll-padding-top` set | Focused control fully or mostly visible |
| B4 | Skip link to `#main` exists, first in tab order, visible on focus; `main` receives focus on route change | `skip-links`, `focus-on-route-change` | Live: Tab once on load; navigate between routes and read `document.activeElement` | Pass (skip link exists in `app/layout.tsx`; verify visibility and route-change focus) |
| B5 | Heading hierarchy is sequential, one `h1` per page | `heading-hierarchy` | Live script listing `h1..h6` per route | 1 h1; no skipped levels |
| B6 | Icon-only buttons and links have `aria-label` (or visible text); decorative icons beside text are `aria-hidden="true"`; selected/pressed/expanded state exposed (`aria-expanded`, `aria-pressed`, `aria-current`) | `aria-labels`, `icon-context`, `pro-rules` "Contextual Semantics" | Grep `<button` without text children; live accessibility tree | 0 unnamed controls |
| B7 | Meaningful images have specific `alt`; decorative images `alt=""` | `alt-text` | Grep `<img`/`next/image` without `alt`; live | 0 missing alt |
| B8 | Errors, toasts and live updates are announced: `role="alert"` or `aria-live` for errors, `aria-live="polite"` for toasts, no focus steal | `aria-live-errors`, `toast-accessibility`, `contextual-live-badge-updates` | Grep `role="alert"\|aria-live` (baseline has 22 hits; the count of form error blocks must match); live with screen-reader tree | Every error container has role or live region |
| B9 | Modals/drawers: focus trapped, Escape closes, focus returns to trigger, visible close control, `aria-modal`, labelled | `escape-routes`, `modal-escape`, `focus-management` | Live: open Modal, NotificationDrawer, NotificationPreferencesModal, classroom device dialog | Pass all four behaviours |
| B10 | Reduced motion respected (CSS and any JS animation/autoplay) | `reduced-motion`, `auto-rotation-controls` | Live with `prefers-reduced-motion: reduce` emulation; grep `animate-` and carousels | No movement > fade; carousels pause/stop; `globals.css` block present (it is) |
| B11 | Authentication allows paste and password managers: `autocomplete="current-password"/"new-password"/"username"/"email"`, no paste blocking | `accessible-authentication` | Grep `type="password"` and `onPaste` | Every auth input has `autocomplete`; 0 paste blockers |
| B12 | Drag-only interactions have a button/keyboard alternative | `dragging-alternative` | Grep `draggable\|onDrag` | 0 drag-only controls |
| B13 | Language: `<html lang>` set; localised text marks `lang` where it switches | WCAG (skill `accessibility` guidance) | Live `document.documentElement.lang` | Set |
| B14 | Zoom not disabled: viewport has no `maximum-scale=1` / `user-scalable=no`; layout works at 200% zoom and with text enlarged | `viewport-meta`, `dynamic-type` | `app/layout.tsx` viewport export; live 200% zoom at 1280 wide | Pass; no loss of content |
| B15 | Colour is not the only state cue (selected tab/slot, active nav, errors, availability) | `color-not-only` | Live grayscale check on schedule picker, nav, tabs | Each state distinguishable |

## C. Forms

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| C1 | Every input/select/textarea has a visible `<label>` linked by `htmlFor`/`id` (or wrapping label); placeholder is never the label | `form-labels`, `input-labels` | Grep: count of `<input\|<select\|<textarea` vs `htmlFor`; live: `document.querySelectorAll('input,select,textarea')` where `labels.length===0` and no `aria-label` | 0 unlabelled controls (baseline: 76 controls, 69 `<label`, 10 `htmlFor`: not satisfied) |
| C2 | Generated ids are unique (use `useId()`, not slugified label text, which collides when two fields share a label) | `form-labels` | Live duplicate-id scan: `[...document.querySelectorAll('[id]')]` duplicates | 0 duplicate ids (note `ui/Input.tsx` derives id from label) |
| C3 | Errors appear next to the field, are linked with `aria-describedby`, field gets `aria-invalid="true"`, container has `role="alert"` or live region | `error-placement`, `aria-live-errors` | Grep: `aria-describedby` and `aria-invalid` counts versus error `<p>` blocks (baseline 0 and 1: fails) | Every error `<p>` has an id referenced by its input |
| C4 | After failed submit with several errors: focus moves to a linked error summary (or first invalid field when no summary); inline errors remain | `error-summary`, `focus-management` | Live: submit empty login/register/support/tutor-apply and read `document.activeElement` | Pass |
| C5 | Error text states cause and fix, never just "Invalid input"; includes recovery path | `error-clarity`, `error-recovery` | Review strings on auth, checkout, booking, apply | Pass |
| C6 | Validate on blur, not on each keystroke; no errors on pristine fields | `inline-validation` | Live: type into email and observe | Pass |
| C7 | Required fields marked with text ("required") or `*` + `aria-required`/`required`; legend explains the mark | `required-indicators` | Grep `required`; live | Pass |
| C8 | Semantic input types and mobile keyboards: `type=email/tel/number`, `inputmode`, `autocomplete` tokens (`given-name`, `email`, `tel`, `bday`, `cc-*` not used) | `input-type-keyboard`, `autofill-support`, `redundant-entry` | Grep inputs without `type`/`autoComplete` | 0 plain text inputs for email/phone/number |
| C9 | Control border >= 3:1 against its surround; focus changes more than colour alone (ring + border) | `pro-rules` Icon Contrast; plan `border-strong` | Computed-style script: `getComputedStyle(el).borderColor` vs parent background | >= 3.0 (current `#D8B7A5` = 1.87: fail) |
| C10 | Field height >= 44px; text size in inputs >= 16px on phones (no iOS zoom) | `touch-friendly-input`, `readable-font-size` | Live at 375: `getComputedStyle(input).fontSize`, `getBoundingClientRect().height` | font-size >= 16px; height >= 44px |
| C11 | Checkboxes/radios have >= 24px hit area including label (label clickable), 44px target preferred | `web-target-size`, `touch-target-size` | Live click-target size of label+input | >= 44px high row (24px floor) |
| C12 | Password fields offer show/hide toggle (accessible name, `aria-pressed`) | `password-toggle` | Live | Present on login, register, reset |
| C13 | Submit shows loading state, disables during request, shows success or failure | `submit-feedback`, `loading-buttons` | Live with throttled network | Pass |
| C14 | Helper text persistent under complex inputs, linked with `aria-describedby` | `input-helper-text` | Review | Pass |
| C15 | Disabled vs read-only distinguishable; disabled has `disabled` attribute and 0.38-0.6 opacity but text still legible (A9) | `disabled-states`, `read-only-distinction` | Review `disabled:` classes | Pass |
| C16 | Group related fields with `fieldset`/`legend` (radio groups, time pickers) | `field-grouping` | Grep radio/checkbox groups | Each group has legend/`role="group"` + label |
| C17 | Destructive actions confirm; multi-step flows show progress and back | `confirmation-dialogs`, `multi-step-progress` | Review tutor apply (5 steps), cancel booking | Pass |

## D. Controls and buttons

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| D1 | One primary CTA per view, style = cocoa pill with white text; secondary visibly subordinate (outline) | `primary-action`, plan | Live: count solid-filled buttons per viewport; grep `Button` variants | <= 1 primary per section |
| D2 | Only four solid colour variants exist: primary (cocoa), secondary (outline), danger, accent chip. `gold` / `teal` / custom `bg-*` button classes removed | Plan phase 4, `consistency` | `components/ui/Button.tsx` variants list; grep `bg-(gold\|emerald\|amber\|teal)` on `<button\|<a` | 4 variants; 0 ad-hoc coloured buttons |
| D3 | Button text contrast >= 4.5 in every state (default, hover, active, disabled, focus) | `color-contrast`, `state-clarity` | Compute each state's pair | Pass all states |
| D4 | Hover, active/pressed and disabled are visually distinct; pressed does not shift layout; hover is not the only affordance | `state-clarity`, `press-feedback`, `hover-vs-tap`, `pro-rules` "Stable Interaction States" | Live hover and press screenshots; grep `active:translate` (1px nudge is acceptable, scale > 1.05 is not) | Distinct; 0 hover-only functionality |
| D5 | Consistent radius (pills for buttons, one radius scale for cards/inputs) and icon family (one stroke width, outline only or filled only per level) | `consistency`, `icon-style-consistent`, `elevation-consistent` | Grep `rounded-` variety; icon imports | <= 3 radii in use per component class |
| D6 | `cursor-pointer` on every clickable non-link element; non-interactive elements do not look clickable | `cursor-pointer` | Grep `onClick` on `div`/`span`; live | Pass; prefer `<button>` |
| D7 | Clickable things are real `button`/`a` (not `div onClick`) and have the right role; links navigate, buttons act | `system-controls`, `pro-rules` "Semantic native controls" | Grep `<div[^>]*onClick` | 0 (or with `role`+`tabIndex`+key handlers) |
| D8 | Loading and disabled states on async buttons; no double-submit | `loading-buttons` | Review `isLoading` use on checkout/reserve | Pass |
| D9 | No emoji used as icons (structural or status) | `no-emoji-icons` | Grep emoji ranges in TSX | 0 as icons |

## E. Typography

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| E1 | Body text 16px (1rem) minimum on mobile; secondary 14px minimum; nothing below 12px, and 12px only for non-essential labels (badge, timestamp) | `readable-font-size`, `font-scale` | Grep `text-\[(9\|10\|11)px\]`, `text-xs` (baseline: 447 `text-xs` uses; each must be non-essential metadata); live: computed font-size histogram per route | 0 under 12px; body paragraphs >= 16px; `text-xs` only for non-body |
| E2 | Line-height 1.5-1.75 for body; headings 1.1-1.3 | `line-height` | Computed `line-height / font-size` | Body >= 1.5 |
| E3 | Line length 35-60 chars mobile, 60-75 desktop for long copy (`max-w-prose`/`max-w-2xl`) | `line-length`, `line-length-control` | Live measure widest paragraph | <= 75ch |
| E4 | Type scale is consistent (12, 14, 16, 18, 24, 32...); no stray `text-[13px]`-style values | `font-scale` | Grep `text-\[[0-9]+px\]` | 0 arbitrary sizes outside scale |
| E5 | Font pairing intact: DM Sans (UI/body) + Lora (display/serif), self-hosted via `next/font`, `font-display: swap` | `font-pairing`, `font-loading` | `app/layout.tsx`; Network tab; no FOIT | Pass |
| E6 | Weight hierarchy: headings 600-700, body 400, labels 500 | `weight-hierarchy` | Spot-check | Pass |
| E7 | Tabular figures for prices, timers, tables | `number-tabular` | Grep `tabular-nums` on price/timer components (`LessonPriceLabel`, wallet, payouts, classroom timer) | Present |
| E8 | Headings wrap balanced; long tokens (emails, URLs) wrap without overflow (`overflow-wrap:anywhere`, `min-w-0` on flex children) | `heading-line-balance`, `long-token-wrapping`, `truncation-strategy` | `globals.css` has `text-wrap: balance`; live at 320 with long email | No overflow; truncation has full text via tooltip/title |
| E9 | Letter-spacing not tightened on body; all-caps eyebrows only for short labels | `letter-spacing` | Grep `tracking-` | Pass |

## F. Touch targets and spacing

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| F1 | Every pointer target >= 44x44 CSS px (project target); never below 24x24 (WCAG 2.5.8 floor) unless inline-in-text or sufficiently spaced | `touch-target-size`, `web-target-size` | Live script: `getBoundingClientRect()` of all `a,button,[role=button],input,select,[tabindex]` at 375 and 1280, excluding inline text links | 0 under 24; 0 under 44 on mobile viewport for primary controls; list exceptions |
| F2 | Hit area can exceed the visual icon (padding or pseudo-element) | `touch-target-size`, `no-precision-required` | Icon buttons: `p-2.5` or `min-h-11 min-w-11` | Pass |
| F3 | >= 8px gap between adjacent targets (`gap-2`+), not `gap-0/1` | `touch-spacing`, `touch-density` | Live: nearest-neighbour distance on mobile toolbars, calendar slots, star ratings, pagination | >= 8px |
| F4 | 4/8px spacing rhythm (Tailwind 1/2/3/4/6/8...), no arbitrary `p-[13px]` | `spacing-scale`, `8dp spacing rhythm` | Grep `\[[0-9]+px\]` in padding/margin/gap | Mostly 0; list exceptions |
| F5 | Page gutters >= 16px at 320-640, wider gutters on larger screens; consistent container (`max-w-6xl/7xl mx-auto`) | `container-width`, `Adaptive gutters` | Live: left offset of `main` content at each width | >= 16px phone; same max-width on sibling pages |
| F6 | Section spacing tiers consistent (e.g. 16/24/32/48/64) | `Section spacing hierarchy` | Visual review | Pass |
| F7 | Fixed/sticky bars reserve space; content not hidden; safe-area insets honoured (`env(safe-area-inset-*)`) for fixed bottom CTAs/cookie bar | `fixed-element-offset`, `safe-area-awareness` | Live at 375 scroll to bottom; cookie bar over footer links | Nothing hidden |
| F8 | z-index from a defined scale | `z-index-management` | Grep `z-\[` | No arbitrary z-index above scale |

## G. Responsive

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| G1 | No horizontal page scroll at 320, 375, 768, 1024, 1280, 1440 | `horizontal-scroll`, plan acceptance | Live: `document.documentElement.scrollWidth <= innerWidth` on every route per role | 0 overflow (also report the offending element) |
| G2 | Mobile-first breakpoints (375/768/1024/1440); layouts re-flow instead of shrinking | `mobile-first`, `breakpoint-consistency` | Review `sm:/md:/lg:` order; live | Pass |
| G3 | Viewport meta present, no zoom lock; `min-h-dvh` rather than `100vh` on mobile (baseline `body{min-height:100vh}`) | `viewport-meta`, `viewport-units` | `app/layout.tsx`; `globals.css` | No zoom lock; replace `100vh` with `100dvh` (minor) |
| G4 | Tables/wide data (admin, payouts, ledger) scroll inside their own container or reflow to cards, never the page | `horizontal-scroll`, `responsive-chart` | Live 375 on admin tables | Contained |
| G5 | Core content first on mobile; secondary content collapsed | `content-priority` | Review landing, tutor profile, scheduler | Pass |
| G6 | Landscape phone (667x375) usable; no fixed element covers > 25% of height | `orientation-support` | Live 667x375 | Pass |
| G7 | Images: width/height or aspect-ratio set (no CLS), `next/image` with `sizes`, lazy below fold, WebP/AVIF | `image-dimension`, `image-optimization`, `lazy-load-below-fold` | Lighthouse CLS < 0.1; grep `<img` | CLS < 0.1 |
| G8 | Layout survives 200% text size and long translations (ja/ko/de) without clipping | `dynamic-type`, `compact-label-overflow` | Live zoom 200%; long strings | No clipped controls |
| G9 | Chips/badges wrap before shrinking labels | `chip-collection-reflow` | Live tutor card tags at 320 | Pass |

## H. Motion

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| H1 | Micro-interactions 150-300ms; modals/drawers <= 400ms; exits ~60-70% of enter | `duration-timing`, `exit-faster-than-enter` | Grep `duration-`, `animate-` | In range; one shared set of tokens |
| H2 | Animate `transform`/`opacity` only; no width/height/top/left animation, no layout shift | `transform-performance`, `layout-shift-avoid` | Grep `transition-all` (acceptable on small controls), `animate-[...]` | No layout animation |
| H3 | Motion has meaning (state change, feedback), 1-2 animated elements per view, no decorative parallax | `motion-meaning`, `excessive-motion`, `parallax-subtle` | Visual review | Pass |
| H4 | Reduced-motion media query collapses animations and scroll-behavior (present in `globals.css`); JS-driven motion also checks it | `reduced-motion`, `motion-sensitivity` | Emulate reduce; check Framer/GSAP use | No motion remains |
| H5 | Animations are interruptible and never block input | `interruptible`, `no-blocking-animation` | Live rapid toggling of drawers/accordions | Pass |
| H6 | Press feedback within 100ms; subtle scale only (0.95-1.05) | `press-feedback`, `scale-feedback`, `tap-feedback-speed` | Live | Pass |
| H7 | Loading: skeleton for > 1s waits, spinner for short; empty and error states exist | `progressive-loading`, `empty-states`, `error-state-chart` | Throttle network on tutors, bookings, wallet | Each list has loading, empty, error states |
| H8 | Auto-rotating content has pause/stop, stops on focus/hover and reduced motion | `auto-rotation-controls` | Landing carousels/testimonials | Pass or no auto-rotation |

## I. Navigation

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| I1 | Current location highlighted (not by colour alone) and exposed with `aria-current="page"` | `nav-state-active` | Grep `aria-current`; live | Present in header, student/teacher/admin sidebars |
| I2 | Nav items have text labels (icons optional); icon-only only for well-known utilities with `aria-label` | `nav-label-icon` | Review header and mobile nav | Pass |
| I3 | Navigation placement and order are the same across pages of a role; no mixed patterns at one level (tabs + sidebar + bottom nav) | `navigation-consistency`, `avoid-mixed-patterns`, `adaptive-navigation` | Compare layouts | Pass |
| I4 | Mobile nav <= 5 top-level items, desktop sidebar for dashboards (>= 1024) | `bottom-nav-limit`, `adaptive-navigation` | Count | <= 5 on mobile bar |
| I5 | Back is predictable; scroll, filters and form state restored; no silent resets to home | `back-behavior`, `state-preservation`, `back-stack-integrity` | Live: filter tutors, open profile, press Back | State preserved |
| I6 | Every key screen has a stable URL (tutor profile, booking, checkout step, filters in query) | `deep-linking` | Check routes and query-string filters | Pass |
| I7 | Destructive/session actions (log out, delete account, cancel booking) visually separated from normal nav | `destructive-nav-separation` | Account menu | Pass |
| I8 | Unavailable destinations explain why instead of vanishing | `empty-nav-state` | Role-gated menu items | Pass |
| I9 | Breadcrumbs on pages 3+ levels deep (admin vetting detail, materials/[slug]) | `breadcrumb-web` | Review | Pass |
| I10 | Footer, help/support link in the same relative place on all pages | `consistent-help` (WCAG 3.2.6) | Compare | Pass |

## J. Content and polish

| # | Rule | Source | How to check | Pass threshold |
| :- | :- | :- | :- | :- |
| J1 | Plain-English copy; no developer jargon ("escrow", "state machine", "payload", "UTC", raw enum values, ids) in student/tutor UI | `error-clarity`; plan phase 6 | Grep UI strings for jargon list; live read-through | 0 jargon in non-admin pages |
| J2 | Plurals and numbers formatted correctly ("1 credit", rating `5.0` vs `4.98` consistent, prices via `lib/currency.ts`, locale-aware dates in the user's timezone) | `number-formatting`, plan | Grep `Credits` literals; live | 0 "1 Credits" |
| J3 | Empty states give a message and an action | `empty-states` | Throttle/clear data | Pass |
| J4 | Success is confirmed (toast/inline) and auto-dismisses 3-5s; undo for destructive bulk ops | `success-feedback`, `toast-dismiss`, `undo-support` | Live | Pass |
| J5 | Staff-only banners/links not shown to students/tutors (email banner shown to staff only) | Plan phase 6 | Live as each role | Pass |
| J6 | Brand consistency: same logo, one icon style, copy tone; no placeholder/lorem | `consistency`, `style-match` | Visual review | Pass |
| J7 | Stars/ratings use text alternative ("Rated 4.9 out of 5") | `alt-text`, `aria-labels` | Live `StarRating` | Pass |
| J8 | OG/social image and favicon use palette tokens only | Plan phase 6 | `app/opengraph-image*`, `icon*` | No green/navy |

---

## Verification toolkit (copy/paste)

```bash
# static (run in Project-files/frontend/src)
grep -rEn "(bg|text|border|ring|from|via|to|fill|stroke|outline|divide|placeholder)-(emerald|green|teal|purple|violet|indigo|fuchsia|slate|amber|yellow|rose|blue|red|gray|zinc|neutral|stone|lime|cyan|sky)-[0-9]+" .   # sky-NNN only if not defined
grep -rEn "#[0-9A-Fa-f]{6}\b" . --include=*.tsx --include=*.ts
grep -rEn "focus:outline-none" . | grep -v "focus-visible"
grep -rEn "text-ink-(faint|light|400|300)" .
grep -rEn "text-(gold|accent-[3-6]00)" .
grep -rEn "bg-(sun|accent)[^\"]*text-(white|primary)" .
```
```js
// live (paste in console per page)
const l=h=>{const c=h.match(/\d+(\.\d+)?/g).slice(0,3).map(n=>{n/=255;return n<=.03928?n/12.92:((n+.055)/1.055)**2.4});return .2126*c[0]+.7152*c[1]+.0722*c[2]};
const cr=(a,b)=>{const[x,y]=[l(a),l(b)].sort((p,q)=>q-p);return (x+.05)/(y+.05)};
// overflow
document.documentElement.scrollWidth>innerWidth
// small targets
[...document.querySelectorAll('a,button,[role=button],input,select,textarea')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&(r.width<44||r.height<44)}).length
// unlabelled controls
[...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby'))
// duplicate ids
(ids=>ids.filter((x,i)=>ids.indexOf(x)!==i))([...document.querySelectorAll('[id]')].map(e=>e.id))
```

---

## Baseline review (2026-10-07, working tree of `feature/landing-audit-fixes` at `b13d16c` + the fixer's uncommitted edits)

State when reviewed: HEAD `b13d16c`, with 132 files changed and uncommitted (`git diff --stat`), including `tailwind.config.ts` (+59 lines); the fixer is mid-change. Counts below are from the working tree and will move. All greps from `frontend/src`.

### Already complies
- **Skip link** to `#main` present (`app/layout.tsx:46`), `main` has `tabIndex={-1}` (B4, route-change focus plausible).
- **Global focus ring**: `:focus-visible { outline: 2px solid #C2410C; outline-offset: 3px }` with a `.on-dark` yellow variant (`#FFDE3D` on cocoa 9.46:1) (B1, B2 partially). Orange ring on cream 4.92 passes.
- **Reduced motion** block in `globals.css` (B10, H4); `touch-action: manipulation` on buttons (tap delay).
- **Heading balance** `text-wrap: balance` (E8); fonts self-hosted via `next/font`, DM Sans + Lora (E5).
- **Viewport** export exists (`app/layout.tsx:28`); verify no zoom lock (B14, G3).
- **Core text pairs are strong**: ink on white/cream 14-15:1, ink-muted `#6B5B53` 5.3-6.5, white on cocoa 12.6, white on primary orange 5.18, ink on sun 11.3 (A1).
- **Button sizes** `min-h-[40|48|52px]`; Input `min-h-[48px]`, `text-base` (16px) so no iOS zoom (C10 passes for `ui/Input`); `ui/Input` links label by `htmlFor`/`id` (C1 for this component).
- **No purple/violet/indigo/fuchsia** anywhere in `src` (A5 purple part: 0 hits) and no `teal-NNN` classes.
- An `ErrorState` component exists and `role="alert"|aria-live` appears 22 times (B8 partial).
- Dev tokens `success`, `error` defined; `cocoa` brand dark documented in `tailwind.config.ts`.

### Does not comply (baseline counts; owner phase in brackets)
1. **Green/teal hex still present** [phase 1]: `app/teacher/apply/page.tsx` lines 93-105 (`#f7f8f5`, `#0E2421`, `#657a73`, `#536963`, `#0e6f68`, `#d6ded9`, `#f0f4f0`); `app/teacher/dashboard/page.tsx:168` gradient `#0B3530 ... #082622`; `components/ui/Badge.tsx:28` border `#C3D7C8`. A5 fail.
2. **`emerald-` classes: 103 occurrences; `amber-`: 113; `yellow-/rose-`: 29; `blue-`: 13; `red-`: 8; `green-`: 1; `gray/zinc`: 4** [phase 0/1/4]. A4/A5 fail (plan said about 170 emerald; the fixer has already reduced it, working tree).
3. **`slate-` / navy classroom: 53 occurrences in 10 files** (`VideoSdkClassroom.tsx:374-377` `bg-slate-950/80`, `bg-slate-900`, `border-slate-700`; `login`, `forgot-password`, `reset-password`, `materials`, `history`, `vocabulary`, `teacher/students`, `teacher/training`, `InteractiveWordTooltip`) [phase 1/2]. A13 fail.
4. **Undefined token classes**: `bg-surface` used 4 times (`admin/teachers/vetting/page.tsx:615`, `NotificationDrawer.tsx:99,187`, `NotificationPreferencesModal.tsx:99`) with no `surface` key in `tailwind.config.ts`, so modals/drawers render transparent [phase 0/1]. A6 fail. (`text-success`/`bg-success` resolve; 39 uses, check hue per A5.)
5. **Control borders fail 3:1**: `Input.tsx` and `Button` secondary use `#D8B7A5` = **1.87:1** on white, 1.78 on cream. Need `border-strong` (candidate `#8A746A`: 4.39 white / 4.17 cream / 3.61 cream-deep) [phase 3]. C9 fail.
6. **`ink-faint/ink-light/ink-400 #8A746A` used as text 33 times** (4.39 on white, 4.17 on cream, lower elsewhere): fails 4.5 [phase 2]. Input placeholder uses `placeholder:text-ink-faint` (fail). A1/A9 fail. Fix by remapping those tokens to `#6B5B53` or darker for text.
7. **Gold as text/icon on light: 48 `text-gold|accent-300..600` uses** (gold 1.98:1 on cream) [phase 2]. A10 fail. `StarRating` and review pages must move to a darker star token.
8. **`focus:outline-none` 60 times vs `focus-visible` 13**: unresolved cases without a replacement ring include `FlashcardDeck.tsx:208`, `review/page.tsx:190`, `ReviewRubricModal.tsx:119`, `admin/teachers/page.tsx:84` [phase 3]. `ui/Input` replaces outline with a `focus:ring-2` (acceptable, uses primary ring on white 5.18). B1 partial.
9. **Forms**: 76 form controls, 69 `<label>`, only 10 `htmlFor`, **0 `aria-describedby`, 1 `aria-invalid`**; `ui/Input` error `<p>` has no id/`role="alert"` and the id is slugified from label text (collision risk) [phase 1]. C1/C2/C3/C4 fail.
10. **Button system has 6 variants** (`primary`, `secondary`, `quiet`, `destructive`, `gold`, `teal` where "teal" is actually cocoa) and primary is orange `bg-primary`, not cocoa; `destructive` hover uses raw `#952828`; `gold` variant uses `text-ink` on `#E7A83E` (ratio 7.6, passes) but is a 5th solid colour [phase 4]. D1/D2 fail against the plan.
11. **Small text**: `text-xs` 447 uses; no sub-12px arbitrary sizes found (`text-[9-11px]` = 0, good) [phase 5]. E1 needs a per-usage review for body-level content.
12. **Touch targets**: `Button` sm `min-h-[40px]` is below 44; only ~39 explicit 44px-class hits, ~3 small `p-1`/`h-6..8` button patterns (`review/page.tsx:190` and `ReviewRubricModal.tsx:119` star buttons are `p-1`) [phase 5]. F1 fail.
13. **Focus-ring contrast on yellow/coral blocks**: global ring is orange; on sun it is 3.89 (just passes 3:1), on coral 1.84 (fails). Needs a cocoa ring variant for coloured blocks [phase 3]. B2 partial.
14. **Success token `#52705A` and `success-surface #EEF3EC` are grey-green** and `Badge` success border `#C3D7C8` is green: need warm replacement and re-measurement [phase 0]. A5 fail. No `warning`, `info`, `border-strong` or star tokens yet in the committed config (fixer's uncommitted `tailwind.config.ts` diff may add them: re-review at phase 0 commit).
15. **`primary-hover` etc. duplicates**: `ink` has 3 identical aliases (`faint`, `light`, `400` all `#8A746A`; `muted` = `500`), `cocoa` has 2 (`hover`/`deep`/`700`/`800` identical): clean up at phase 0 (A4).
16. **Raw hex in components**: 11 files with `#RRGGBB` in TSX/TS, 26+ occurrences (`#4A2C1A`, `#D8B7A5`, `#E7A83E`, `#8A5B14`, `#952828`, etc.) [phase 0/4]. A4 fail.
17. **Not yet checked live** (code-only baseline; the fixer's mid-edit state made a crawl unreliable): horizontal overflow (G1), actual contrast crawler results (A1), responsive flows, keyboard pass, motion durations, heading order, route-change focus. These are for the phase reviews and the final gate.

---

## Review plan per phase (for resuming the reviewer with SendMessage)

Send the commit SHA (or `git diff <prev>..<sha>`); I will run the checks below and answer PASS/FAIL per rule number, with file:line evidence.

| Phase | Verify (rule ids) | Method |
| :- | :- | :- |
| 0 Tokens | A4, A5, A6, A8, A10, A13, C9 | Read `tailwind.config.ts` diff; recompute every new token pair with my script (success, warning, info, border-strong >= 3:1, star >= 3:1, focus); confirm `surface` defined and duplicates aliased; no green/teal/purple hue; ratios recorded in the comment |
| 1 Critical | A1, A5, A6, A7, A13, B9, C1-C4, F1 (classroom) | Diff + grep for emerald/green/teal hex and `slate-`; open classroom/admin/login/register/support/review in the browser; keyboard-submit empty forms and read focus and `aria-describedby`; modal opacity |
| 2 Contrast sweep | A1, A2, A9, A10, A11, A12 | Re-grep `text-ink-(faint|light|400|300)`, `text-gold`, orange-on-sun; run the live crawler across roles; list remaining failing pairs |
| 3 Controls | B1, B2, B3, C9, C10, C11, D4 | Grep `focus:outline-none`; compute border contrast; Tab pass with screenshots on cream, cocoa, sun, coral; 375px input font-size and height |
| 4 Buttons | D1-D5, A3 | Read `ui/Button.tsx` and grep ad-hoc `bg-*` on buttons/links; confirm four variants, white-on-cocoa 12.6, states measured |
| 5 Touch & type | E1, E4, F1-F4, G1 | Live target-size script at 375 and 1280; count `text-xs` in body-level copy; overflow at 320 |
| 6 Content | J1-J8, B7, E7 | Grep plural/jargon strings; screenshot staff vs student banner; check OG image colours; `StarRating` text alternative |
| 7 Behaviour | H7, C5, B8 | `/teacher/power-guard` heading + retry; console for repeated 401 on anonymous load (frontend handling only) |
| 8 Verification | all | Full crawler, static greps, overflow at 6 widths x 4 roles, keyboard pass, lint/test/build results |

The reviewer reads only; any needed fix is reported back to the fixer, not edited.
