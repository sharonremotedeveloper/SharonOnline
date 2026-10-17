# Admin content management (materials + tutor training) - PENDING

**Status: PENDING - not built. To be handled later.** Recorded 2026-10-18 at Anesu's request after a scope check.
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

## 4. Proposed plan (not approved yet)

1. **Training admin first** (small, on the launch path because training gates bookability):
   `/admin/training` - list, create, edit, reorder, publish/unpublish; Markdown with preview; optional video and PDF
   attachments through the safe upload flow; staff create/update API with tests.
2. **Materials admin second:** `/admin/materials` - draft/published state (new materials start as drafts), PDF/audio
   upload via the existing commit endpoint, server-side HTML sanitizing.
3. Later: PDF worksheet generator, versioning, structured vocabulary/discussion fields (the API returns empty lists today),
   image uploads.

## 5. Open questions for Anesu (decide before building)

1. Who authors content: only Sharon, or other staff/content editors? If others, add a content-editor role with no access
   to money, disputes or tutor approval.
2. Training videos: upload to our storage, or embed YouTube/Vimeo links (simpler, cheaper)?
3. Materials workflow: Draft -> Review -> Published (a second person checks), or Draft -> Published?
4. A new required training module: must already-approved tutors complete it before their next booking, or new tutors only?
