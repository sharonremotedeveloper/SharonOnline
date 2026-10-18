# Admin content management (materials + tutor training) - PENDING

**Status: BUILT (Wave 2, 2026-10-19).** Recorded 2026-10-18 as pending; the four questions were answered the same day
(section 5) and Wave 2 built both halves: `/admin/training` and `/admin/materials` (section 6). Sections 1-4 describe the state
before Wave 2 and are kept for the record. What is still left for later is in section 6.3.
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

## 4. Plan (Wave 2; done, see section 6)

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

## 6. What Wave 2 built (2026-10-19)

### 6.1 Tutor training (`/admin/training`, `/admin/training/new`, `/admin/training/<id>`)

- Staff API `apps/admin_api/training_views.py` (`IsPlatformAdmin`; throttle `admin_read` / new `admin_content` 600/h):
  list with completion counts, tutor totals and the gate setting; create; edit; reorder (`POST /admin/training/reorder/`).
- Writes go through `teachers/training.py::save_module` (also used by Django admin's save, whose publish/required columns are no
  longer list-editable). When a module becomes published + required, every tutor holding a training date who has not completed
  it loses the date (section 5.1, no grace period). The API answers 409 `regate_confirmation_required` with the number of tutors
  until the admin confirms; each affected tutor gets the new mandatory notification `training_required` (e-mail + in-app).
  Unpublishing or making a module optional never takes anything away.
- Video: `TrainingModule.video_youtube_id` (migration `teachers/0015`). Only `parse_youtube_id` writes it (watch, youtu.be,
  embed, shorts links; anything else is a 400). Tutors and the admin preview embed it from `youtube-nocookie.com` in a sandboxed
  iframe (`components/training/TrainingContent.tsx`).
- Editor: title, web address, summary, minutes, YouTube link, required switch, Markdown body with a Preview tab; Save draft /
  Publish / Unpublish.

### 6.2 Lesson materials (`/admin/materials`, `/admin/materials/new`, `/admin/materials/<id>`)

- `Material.is_approved` became `is_published` with default **False** (migration `materials/0003`; existing rows keep their
  value, so everything public stayed public). Drafts are 404 on the public API.
- Lesson HTML is cleaned with `nh3` on every save (`Material.save`, `materials/sanitize.py`) and again when served, which fixes
  risk 1. Allowed: headings, paragraphs, bold/italic, lists, tables, quotes, links (http/https/mailto, `rel=noopener noreferrer
  nofollow`). Removed: scripts, styles, event handlers, forms, iframes, images.
- Staff API `apps/admin_api/material_views.py`: list (status filter, search, counts), create, edit, detach PDF/audio, delete
  drafts only (a published material must be unpublished first).
- Files: the page uploads to `incoming/<admin id>/...` and commits through the existing checked endpoint (risk 3 is avoided by
  the UI). Django admin's file fields are now read-only (risk 2).
- Editor: a small WYSIWYG (`components/admin/LessonHtmlEditor.tsx`: heading, paragraph, bold, italic, lists, links, HTML view);
  pasted text arrives as plain text. The public reader and the classroom reader now style lesson HTML with `.lesson-html`
  (globals.css): before, Tailwind's reset removed list bullets and heading sizes on the live site.

### 6.3 Still open (later)

- PDF attachments on training modules (decision 2 covered video only).
- PDF worksheet generator, versioning, structured vocabulary / discussion fields, image uploads (unchanged from section 4.3).
- A content-editor role if non-admin staff start writing (decision 1).
- Detaching or replacing a material file leaves the old object in R2 (no cleanup job yet).
- Admins can still presign any key (the web UI only uses `incoming/`); narrowing the admin presign allowlist is a follow-up.
- Unpublishing and republishing a required module does not notify the same tutor twice (notification key is per module and tutor).

### 6.4 Releasing Wave 2 to production (prepared 2026-10-19, NOT applied)

Vercel deploys the website from `main`, but the production API on Railway only changes with Anesu's explicit go-ahead
(`RAILWAY_SETUP.md` sections 4-5). Until the backend release is done, `/admin/training` and `/admin/materials` show their error
state (only admins see them); every other page works with the old API.

**Release SHA:** `59e3e52a5bfa08784fc7109bb5c8da7f78085b3b` on `main`. It contains exactly two backend commits on top of what
production runs: `775fc05` (Wave 2) and `59e3e52` (expand-only migrations). Read-only Railway check on 2026-10-19 (project
`sharon-online-prod` `e2b11747-...`, environment `production` `dd70ab8a-...`):

| Service | ID | Running now |
| :--- | :--- | :--- |
| `backend-api-production` | `268c83bb-0d01-42a4-a63e-187d5fa90983` | `78226cc` (2026-10-17) |
| `celery-worker-production` | `a1ea5a9f-ca7a-4b2a-b745-9b058237aebb` | `e534795` (2026-10-15) |
| `celery-beat-production` | `31ce61d3-d333-4bac-9e6e-42e7f276777e` | `e534795` (2026-10-15) |
| `production-migrations-b33743a` (one-shot) | `cdc25acb-eb33-4ded-bd90-679b4398fcfd` | `b33743a`, plan-only, `PRODUCTION_MIGRATION_APPROVED` empty |

Both running SHAs are ancestors of `59e3e52`; the push of `main` did not start a Railway deployment. Production has
`TUTOR_TRAINING_GATE_ENABLED=1`, so after this release a newly published required module hides untrained tutors from new
bookings at once (after the admin confirms the count). The release itself re-gates nobody: only a save through
`training.save_module` does, and the existing module `how-lessons-work` is untouched.

**Expected migration plan** (production reached the migration leaf on 2026-10-14 and no migration was added between `b33743a`
and `775fc05`):

```text
materials.0003_material_is_published   -- state-only rename (db_column='is_approved'); no SQL
teachers.0015_training_module_video    -- ALTER TABLE "teachers_trainingmodule"
                                           ADD COLUMN "video_youtube_id" varchar(11) DEFAULT '' NOT NULL;
```

Both are expand-only: the running `78226cc` API keeps working after they are applied. CI ran them on PostgreSQL.

**Steps (each needs Anesu's go-ahead; nothing below has been done):**

1. Recovery point: create a Neon child branch of `production` in project `SharonOnline` (`sweet-bonus-69458238`), as on
   2026-10-14 (`pre-production-migrations-b33743`).
2. Plan: deploy the migration service at commit `59e3e52` with its existing start command
   (`python scripts/run_production_migrations.py --plan`, approval flag still empty) through `serviceInstanceDeployV2`
   (`serviceId cdc25acb-...`, `environmentId dd70ab8a-...`, `commitSha 59e3e52a5bfa08784fc7109bb5c8da7f78085b3b`). Read its log: it must list exactly the two
   migrations above. Anything else: stop.
3. Apply: set `PRODUCTION_MIGRATION_APPROVED=true` and the start command to `... --apply` on that service only, deploy it once at
   `59e3e52`, read the log; deploy once more to see `No migrations to apply.`; then set the start command back to `--plan` and
   clear the flag.
4. Release: deploy `backend-api-production`, `celery-worker-production` and `celery-beat-production` at `59e3e52` (the image
   installs the new `nh3` dependency from `requirements.lock`).
5. Verify: `/api/health/`, `/api/ready/`, `/api/scheduler-ready/` return 200; `GET /api/v1/materials/` still lists the same
   published materials (none today); Anesu signs in as admin on the phone and opens `/admin/training` and `/admin/materials`
   (lists load; nothing is created or published as part of the check).
6. Rollback: redeploy the three services at `78226cc` / `e534795`. The schema needs no rollback: both migrations are
   expand-only and the old code ignores them.
