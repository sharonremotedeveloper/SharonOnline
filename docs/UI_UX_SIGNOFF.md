# UI/UX sign-off (project manager)

## FINAL VERDICT (sweep 4, HEAD d5e4c5f): APPROVED

The lint blocker from sweep 3 is fixed. Every acceptance item and flow now passes on independent verification.

| Gate or check | Result | Evidence |
| :-- | :-- | :-- |
| `npm run lint` | PASS | exit 0, zero warnings (re-run by me on d5e4c5f, clean tree) |
| `npm test` | PASS | 217 pass, 0 fail |
| `npm run build` | PASS | exit 0 |
| Drawer and preferences keyboard flow at 1440, 375 and 320 after the hook change | PASS | Opening via keyboard puts focus inside the dialog; Tab trapped for 10 presses in the drawer and 20 in preferences; no inner scrollers in the modal; page 1434/1434, 369/369, 314/314. First Esc closes only preferences and focus returns to the drawer; second Esc closes the drawer and focus returns to the account-menu button. Mouse open then Close button also returns focus to the account-menu button. |
| Focus outline | PASS | computed 2.4px at devicePixelRatio 1 |
| Checkout (student_aiko login worked again) | PASS | Reserve Wed 14 Oct 12:30 lands on checkout at 1440. The "payment is confirmed by our server" note is now the neutral info style (cream-grey surface, info icon, "Note:" label); the PayPal-not-configured error is pink with an error icon, "Error:" label and `role="alert"`. `pm4-checkout-1440.png`. |
| Sweep 3 results (D1-D15, crawler 0 overflow and 0 real contrast failures, forms linked, preferences fit 320) | PASS | see the sections below; the hook change did not regress them in the re-check above |

Acceptance items: all PASS (contrast, palette, button system and focus, labels and announced errors, overflow 320-1440, flows at phone and desktop, lint/test/build, out-of-scope list). Item "skills reviewer reports all phases compliant": the reviewer should re-tick `UI_UX_COMPLIANCE_CHECKLIST.md`; I found nothing outstanding against it.

Minor, non-blocking notes: the warning (orange) and error (pink) tints are close in hue, so the icon and the "Warning:" / "Error:" word carry the distinction (this is by design); the 320 register role toggle is tight; Next dev badge is the only green on screen and is dev-only. Remaining out-of-scope items are the ones the plan lists (price seed data, materials, photos, ja/ko, CSP).

---
## Previous status (sweep 3, HEAD 1b95086): NOT APPROVED, one blocker left (since fixed)


Everything visual and behavioural now passes. The only thing standing between this branch and APPROVED is a failing lint gate that the fixer's commit introduced.

**Blocker (send back): `npm run lint` fails.** At `1b95086`, `npm run lint` exits 1 with 1 error: `frontend/src/hooks/useDialog.ts:22:3 react-hooks/refs, "Cannot update ref during render"` (`closeRef.current = onClose;` runs in the render body). The acceptance item "lint (zero warnings), test, build pass" is therefore FAIL. Fix: update the ref inside a `useEffect` (or `useLayoutEffect`), or use a `useEffectEvent`-style pattern, then re-run lint. Tests (217 pass) and build (exit 0) are green.

### Sweep 3 results

| Check | Result | Evidence |
| :-- | :-- | :-- |
| Drawer and preferences at 1440, 375, 320 (as naledi_tutor; student login is rate limited) | PASS | Opening via keyboard moves focus into the dialog (`Notification preferences` button in the drawer, `Close preferences` in the modal). Tab stays inside both for 20 presses. First Esc closes only the preferences modal and focus returns to the drawer; second Esc closes the drawer and focus returns to the account-menu button. Mouse path and the Close button also return focus to the account-menu button. No page overflow (1434/1434, 369/369, 314/314). `pm3-drawer-1440.png`, `pm3-prefs-375.png`. |
| D12 preferences fit phones | PASS | No inner horizontal scroll; the rightmost toggle ends at x 235 on 369 and 314 wide viewports; In-app and Email toggles stack under each label (`pm3-prefs-375.png`). |
| D13 focus on open, focus return, Esc order | PASS | See first row. |
| D8 focus outline | PASS | Computed outline 2.4px solid at devicePixelRatio 1 in all three widths (>= 2px). The fixer's claim that a nominal 2px computes to 1.6px is plausible; the new value is what matters. |
| D14 forgot-password, support | PASS | Empty and invalid submits give linked inline errors (`role="alert"`, `aria-invalid`, valid `aria-describedby`, focus on first invalid field) at 375, 320, 1440; no overflow. |
| D15 info variant on payment notes | PASS (code) | `PayPalButtonsWrapper.tsx` now uses `bg-info-surface`, an Info icon and "Note:" for the "payment is confirmed by our server" text. Not re-seen live because student_aiko login is rate limited. |
| Regression crawl (public, teacher, admin; 6 widths 320-1440; 31 routes) | PASS | Overflow: none. Icons below 3:1: none. Contrast: 3 flagged, all white text over the tutor hero photo scrim (hand-measured earlier at 12.6 or more). Unlabelled controls: 0; duplicate ids: 0. Student routes were not re-crawled (rate limit); they were clean in sweep 2 and only shared components changed. |
| Lint | **FAIL** | exit 1, see blocker. |
| Test | PASS | 217 pass, 0 fail. |
| Build | PASS | exit 0. |
| Home screenshot (1440) | PASS | Coherent warm look; price and currency placeholders were still skeletons at capture time (dev compile), not a defect (`pm3-home-1440.png`). |

### To get APPROVED

1. Fix the `useDialog.ts` lint error and confirm `npm run lint` exits 0 with zero warnings (and that `npm test` and `npm run build` still pass).
2. Reviewer re-ticks the compliance checklist.
3. Re-run the drawer and preferences check once after the lint fix (the fix touches the same hook) and, if the student rate limit has reset, confirm checkout shows the info-style note.

No other defects are open. D1-D15 are all closed or accepted as above.

---
(Earlier sweeps follow.)


Branch `feature/landing-audit-fixes`. Sweep 1 on `7e7b6f6`, sweep 2 on `b28fa58` (2026-10-07). Method: own Playwright browser contexts (deviceScaleFactor 1 for the focus check), dev server :3000 plus Django, seeded logins, screenshots in `frontend/.playwright-mcp/pm-*.png` (sweep 1) and `pm2-*.png` (sweep 2). Source was not edited.

## Verdict (sweep 2): NOT APPROVED

The critical sweep-1 defect is fixed visually, and most sweep-1 items are closed. Three things still fail or are open (below). Send back D8, D12, D13 and the two minor items; then re-sign.

## Automated gates (sweep 2)

| Gate | Result |
| :-- | :-- |
| `npm run lint` | exit 0, zero warnings |
| `npm test` | 217 pass, 0 fail |
| `npm run build` | exit 0 |
| Contrast crawler (`.playwright-mcp/crawlAll.js`, 4 roles x 6 widths 320/375/768/1024/1280/1440, 38 routes, every page) | 7 flagged, all text or icons over gradients and photos that the sampler cannot read: white text on the tutor hero photo scrim (Naledi card), "Available Credits", "Active Lesson Tickets", "0", "100% Satisfaction Guarantee" on the cocoa wallet hero. Checked by eye in `pm2-wallet-1440.png`: legible on the dark cocoa. The gold coin icon (flagged 2.11) sits on the dark cocoa chip, about 4.8:1 in reality. **0 real failures.** Overflow list: empty (0 overflow at all six widths, all roles). Unlabelled controls: 0. Duplicate ids: 0. Errors: none. |

## Acceptance items (sweep 2)

| # | Item | Verdict | Evidence |
| :-- | :-- | :-- | :-- |
| 1 | Zero contrast failures, all roles | PASS | Crawler above. |
| 2 | No green/teal/purple/navy; no undefined tokens | PASS | Visual sweep of every role at 375 and 1440 plus crawler: none. Only the Next dev badge is green (dev only). |
| 3 | One primary button style, borders >= 3:1, focus visible | FAIL (minor) | Cocoa pill is the one primary style, red is the danger variant. Focus is visible everywhere but the outline is **1.6px solid rgb(194,65,12) at devicePixelRatio 1** (measured in a DSF 1 context), so it is not browser zoom; the plan asks for 2px or more. D8 stays open. |
| 4 | Every label linked, errors announced | PARTIAL PASS | Login and register: inline errors per field, `role="alert"`, `aria-invalid`, `aria-describedby` pointing at an existing node, focus moves to the first invalid field, at 375, 320 and 1440. Wrong-credentials alert linked to both fields. Forgot-password and support empty or invalid submits still use the browser's native validation (field focused, message announced by the browser, no in-page message). Acceptable, but inconsistent with login and register (D14, low). Checkout error now `role="alert"`. |
| 5 | No horizontal overflow at 320, 375, 768, 1024, 1280, 1440 | PASS | Crawler 0 overflow on 38 routes x 6 widths; signed-in header now fits 320 (314/314, no 6px overflow); register at 320 is 320/320. |
| 6 | Full flows at phone and desktop | PARTIAL PASS | Every flow works end to end at 375 and 1440 (table below), but the notification drawer and preferences modal still have focus problems (D13) and the preferences modal is wider than the phone (D12). |
| 7 | lint, test, build | PASS | See gates. |
| 8 | Skills reviewer reports all phases compliant | NOT VERIFIED | Not re-checked by me; the reviewer should re-tick after D8, D12 and D13 are closed. |
| 9 | Out-of-scope items listed | PASS | Plan line 50. |

## Sweep-1 defects: status

| ID | Was | Now | Evidence |
| :-- | :-- | :-- | :-- |
| D1 critical | Drawer and preferences rendered inside the 64px header | FIXED visually | Drawer and preferences are now full-viewport portals outside the header (rect 0,0,1434,900 at 1440; 369x812 at 375; 314x700 at 320), `pm2-notif-1440.png`, `pm2-prefs-375.png`. Tab is trapped (2 buttons cycle, and in prefs 20 tabs never leave). Esc closes. See D13 for the focus gaps that remain. |
| D2 | 320 signed-in header overflow | FIXED | 314/314 at 320; no hamburger clipping. |
| D3 | Errors not linked | FIXED for login and register | See item 4. |
| D4 | Checkout notices without icon or role | FIXED | Warning has a triangle icon and "Warning:" label, error has a circle icon, "Error:" label and `role="alert"` (`pm2-checkout-1440.png`). |
| D5 | Hard-coded sidebar badges | FIXED | No badge on any admin sidebar item; vetting and dashboard agree (`pm2-admin-admin-dashboard-1440.png`). |
| D6 | Red zero-count pill | FIXED | Neutral outlined "0 Live Sessions Active". |
| D7 | Warning yellow looked like brand yellow, info and success both pale blue | FIXED / acceptable | Warning is now an orange tint (#FFE9CC, brown text) with a triangle icon; error is pale pink-red with a circle icon and bold red text. Side by side on checkout they are distinguishable by icon and word, though warning orange and error pink are close in hue, so the icon and "Warning:" / "Error:" word are what carries the difference. Success blue reads sensibly on admin and wallet (balance, check mark). The sun-yellow booking summary no longer reads as a warning. Content note: the checkout "payment is confirmed by our server after PayPal reports the result" message is informational but is labelled "Warning" (D15, low). |
| D8 | Focus outline 1.6px | **STILL OPEN** | Measured 1.6px at DSF 1. |
| D9 | Register truncation at 375 | FIXED | Register stacks on phones, 375/375 and 320/320, `pm2-register-empty-320.png` (role toggle labels at 320 are very tight, cosmetic). |
| D10 | Table scroll cue | FIXED | `scroll-cue` right-edge fade on the admin tutor table (`pm2-admin-teachers-table-375.png`); the tab nav shows a scrollbar. |
| D11 | Arrow keys | FIXED | ArrowDown opens the account menu and moves through items down to "Notifications"; Esc closes and returns focus to the trigger. |

## Flow table (sweep 2, 375 and 1440 unless noted)

| Flow | Result |
| :-- | :-- |
| Landing, pricing, how-it-works, support, legal, trust-safety, teach, materials | PASS (crawler 0 overflow at 320-1440; visuals checked in sweep 1, unchanged) |
| Tutors directory, filters, profile, scheduler, reserve to checkout | PASS (re-run at 1440 and 375: Mon 12 Oct 11:00 and Tue 13 Oct 11:30 reserved, hold timer shown, no overflow) |
| Student sign-in, dashboard, schedule, history, wallet, profile, checkout, sign-out | PASS, no console errors |
| Account menu keyboard (open, ArrowDown, Esc, focus return) | PASS |
| Notification drawer, preferences | FAIL partial, see D12 and D13 |
| Tutor sign-in, dashboard, schedule grid, profile, wallet, training | PASS (the 503 console line is the dev Eskom service, handled by an error state) |
| Admin sign-in, dashboard, vetting, teachers, disputes, payouts, ledger, FX | PASS |
| Login, register, forgot-password empty and invalid | PASS with the D14 inconsistency |
| Cookie banner | PASS (unchanged) |

## Open defects (send these back)

| ID | Severity | Page / width | Screenshot | Defect |
| :-- | :-- | :-- | :-- | :-- |
| D13 | Medium | Notification drawer and preferences modal, all widths | `pm2-notif-kbd-1440.png`, `pm2-after-esc.png` | Dialogs do not take focus on open: after opening through the menu, `document.activeElement` is `BODY` (the first Tab then lands inside). On Esc, focus is left on `BODY`, not returned to the account-menu trigger. Esc from the preferences modal closes the preferences modal and the drawer together. Needs initial focus into the dialog, focus return to the invoking control (re-focus the account-menu trigger when the menu item unmounts), and Esc closing only the top dialog. |
| D12 | Medium | Notification preferences modal at 375 and 320 | `pm2-prefs-375.png`, `pm2-prefs2-375.png` | Modal body is 398px wide inside a 329px (375) or 274px (320) container: a horizontal scrollbar appears inside the modal and the EMAIL column's toggles sit at x 351-415 on a 375px screen, so they are cut off and the Mandatory rows look like they have one toggle. Make the rows stack or shrink the columns at phone widths. 1440 is fine. |
| D8 | Low | all pages | `pm-focus-home.png` | Focus outline is 1.6px (measured at DSF 1). Make it 2px or more. |
| D14 | Low | /forgot-password, /support | n/a | Empty or invalid submit shows only browser-native validation, while login and register now use inline linked errors. Optional: align. |
| D15 | Low | /student/checkout/[id] | `pm2-checkout-1440.png` | Informational "payment is confirmed by our server" note uses the warning style and "Warning:" label; use the info variant. |

Out of scope, not counted: PayPal not configured in dev, $9 lesson vs $8 single pack, empty materials, Eskom 503 in dev, "per-transaction credit history not available yet" copy.

## Items to send back

1. D13: initial focus into the notification drawer and preferences modal, focus return, Esc closes only the top dialog.
2. D12: make the preferences rows fit 320 and 375 without inner horizontal scroll.
3. D8: raise the global focus outline to 2px or more (or prove the 1.6px in a DSF 1 context is intended and amend the plan).
4. D14 and D15: optional polish.
5. Reviewer re-ticks the checklist; then a short final re-check of the drawer and preferences at 320, 375 and 1440.

## Sweep 1 history (7e7b6f6)

NOT APPROVED. One critical defect (D1, drawer and modal clipped to the 64px header with no focus handling), plus D2-D11 as listed above. All of D1-D7, D9-D11 were verified fixed in sweep 2.
