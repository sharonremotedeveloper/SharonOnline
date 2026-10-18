# Admin content management (materials + tutor training) - PENDING

**Status: PENDING - not built. To be handled later.** Recorded 2026-10-18 at Anesu's request after a scope check.
The four open questions were answered the same day (section 5); building is Wave 2 and has not started.
Page ID ADM-07 (curriculum editor) and Task 15.4 (materials editor) are open; nothing has been started.

Today an admin **cannot** add, edit, upload files for, publish or retire lesson materials or tutor training modules
from the web app. The only way is the Django back office at `https://api.topteacheracademy.com/admin/`
(Materials and Teachers > Training modules). That is how training module `how-lessons-work` was created on 2026-10-17.

## 1. What the scope promised

| Source | Promise |
| :--- | :--- |
| `STATEMENT_OF_WORK_SOW_ESL_2026_001.md:94-97` (workspace root) | Module 7 back office: "Materials CMS: Upload, edit, and categorize lesson plans and articles" (in Django admin). |
| SOW `:69-70` | Tutor training hub: required orientation videos and guideline modules, completion gates bookability. |
| SOW `:156` | Sharon supplies the initial curriculum for the 4 launch categories. |
| `COMPREHENSIVE_PAGE_INVENTORY_AND_SYSTEM_LOGIC.md:858-871` (ADM-07 `/admin/curriculum/editor`) | Block lesson editor with CEFR/category tags, vocabulary builder with audio upload, PDF worksheet generator on R2, Draft -> Review -> Published, WYSIWYG with preview. |
| `docs/TUTOR_STATUS_MACHINE.md:315,330` | Training content is Sharon's, written in Django admin; publish, then backfill, then switch the training gate on. |
| `docs/PRODUCTION_READINESS_PLAN.md:195` | Task 15.4 materials/curriculum editor (draft -> review -> publish, PDF generation) - open. |
| `docs/GAP_ANALYSIS_AND_LAUNCH_TIMELINE_2026-10-07.md:38` | ADM-07: no admin route; materials managed in Django admin only. |

Authors are Sharon / staff. Tutors were never meant to author content. No versioning was promised.

## 2. What exists today

| | Materials (`backend/apps/materials/`) | Training (`backend/apps/teachers/`) |
| :--- | :--- | :--- |
| Model | `Material`: title, slug, category (4), CEFR A1-C2, description, `content_html`, PDF, audio | `TrainingModule`: slug, title, summary, Markdown `body`, position, minutes, required, published; `TrainingProgress` per tutor |
| Publish control | `is_approved` only, **defaults to True** (new rows go live at once); no draft/review/retired state | `is_published`, defaults to False |
| API | Public read (approved only); staff `POST /materials/<id>/assets/commit/` attaches a PDF/audio (no app UI calls it); **no create/update/delete API** | Tutor read + complete only; **no staff API** |
| Uploads | Safe commit flow in `materials/assets.py` (quarantine prefix, ETag, type, 25 MB, magic bytes, random key); PDF and audio only, no images | **None** - text only, so the promised orientation videos are impossible |
| Web admin page | None (admin nav has 8 items, none for content) | None |
| Edited via | Django admin (`materials/admin.py`) and `seed_data` (4 seed materials) | Django admin (`teachers/admin.py`) |
| Shown to | `/materials`, `/materials/[slug]` (renders `content_html` as raw HTML) | `/teacher/training` (safe Markdown subset) |

## 3. Risks to fix when this is built (some apply already)

1. **Unsanitized lesson HTML (security).** `content_html` is rendered with `dangerouslySetInnerHTML`
   (`frontend/src/app/(public)/materials/[slug]/page.tsx:273`, `components/materials/SplitScreenReader.tsx:194`) and is
   not cleaned on the server; there is no Content-Security-Policy yet. Acceptable only while Sharon alone edits in Django
   admin. An in-app editor must sanitize on save (e.g. `nh3`) or store structured blocks.
2. **Django admin uploads bypass the file checks.** `pdf_file` / `audio_snippet_file` saved in Django admin go straight to
   public R2 with no type/size/magic-byte checks.
3. **Admins can presign straight into the public `materials/` prefix**, skipping quarantine. A new admin UI must always
   upload to `incoming/` and then commit.
4. **Training retirement rules are undefined.** Unpublishing a required module does not reopen completions; publishing a
   new required module does not re-gate tutors who already finished.

Safeguards to keep: `IsPlatformAdmin`, the commit checks in `materials/assets.py`, `apps/common/upload_policy.py`
(per-prefix size/type, 60-900 s presign expiry), the presign path-traversal guard and non-admin prefix allowlist.

## 4. Plan (Wave 2; decisions recorded in section 5, build not started)

1. **Training admin first** (small, on the launch path because training gates bookability):
   `/admin/training` - list, create, edit, reorder, publish/unpublish; Markdown with preview; an optional embedded
   YouTube video (decision 2) and an optional PDF through the safe upload flow; staff create/update API with tests;
   re-gating of all tutors when a required module is published (section 5.1).
2. **Materials admin second:** `/admin/materials` - draft/published state (new materials start as drafts), PDF/audio
   upload via the existing commit endpoint, server-side HTML sanitizing.
3. Later: PDF worksheet generator, versioning, structured vocabulary/discussion fields (the API returns empty lists today),
   image uploads.

## 5. Decisions (Anesu, 2026-10-18)

| # | Question | Decision | What it means for the build |
| :--- | :--- | :--- | :--- |
| 1 | Who authors content? | **Admins only, for now.** | Reuse `IsPlatformAdmin`; no content-editor role yet. Revisit if non-admin staff start writing content. |
| 2 | Training videos: our storage or embedded links? | **Embedded YouTube links, for now.** | No video uploads. Store a validated video ID (not free HTML or any URL): accept only `youtube.com/watch?v=`, `youtu.be/` and `youtube.com/embed/` URLs, keep the 11-character ID, render through `youtube-nocookie.com/embed/<id>` in a sandboxed iframe. The CSP (when added) must allow that origin in `frame-src`. Videos should be set to Unlisted on YouTube. |
| 3 | Materials workflow? | **Draft -> Published** (no review step). | Replace "approved by default" with an explicit state; new materials start as **Draft** and only Published ones are public. Existing approved rows migrate to Published. HTML sanitizing on save is still required (risk 1). |
| 4 | New required training module: who must complete it? | **All tutors**, including already-approved ones. | Changes the T6 rule "a module published later never takes a date away" (`teachers/training.py`). Design below. |

### 5.1 Design for decision 4 (to confirm while building Wave 2)

- When a required module is published (or an existing published module becomes required), every approved tutor who has
  not completed it loses `training_completed_at` (cleared in `teachers/training.py`, the only writer). While the training gate is on,
  `bookable()` then hides them from **new** bookings until they finish it. **Lessons already booked are not affected**: cancel,
  memo, attendance, escrow and payouts never consult `bookable()`.
- Completing the last outstanding required module stamps the date again (existing `complete_module` logic).
- Tutors stamped by `backfill_training_completed` have no progress rows, so the backfill must also record progress for the
  modules required at that moment; otherwise they could never be stamped again after a new module appears.
- The admin publish screen must show how many tutors will become unbookable and ask for confirmation before publishing.
  Tutors get a notification that new required training is waiting.
- Open detail: whether to add a grace period (e.g. 7 days before the gate applies). Default without one: the gate applies at once.
- Unpublishing or making a module optional never removes a tutor's completion.
- Check the production value of `TUTOR_TRAINING_GATE_ENABLED` before shipping; with the gate off, nothing above hides anyone.
