# AI Agent & Developer Collaboration Protocol

This document defines the **mandatory rules of engagement and operational protocols** for all AI coding agents (**Claude**, **Codex**, **Antigravity/Gemini**) and human developers (**Anesu MUPESA**) working on Sharon's ESL Platform.

---

## 📜 Mandatory Rules for AI Coding Agents

### Rule 1: Context First — No Blind Edits
Before writing or modifying any code in `Project-files/`, every AI agent **MUST**:
1. Inspect [`docs/README.md`](./README.md) and [`docs/PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md).
2. Check the active sprint tasks in [`docs/PROGRESS_AND_ROADMAP.md`](./PROGRESS_AND_ROADMAP.md).
3. Inspect relevant source files to verify existing imports, model signatures, and route paths.

### Rule 2: Never Guess Schemas, Models, or API Contracts
- Do not guess field names, API parameters, or database relationships.
- Inspect the authoritative source in `Project-files/backend/apps/` or [`docs/ARCHITECTURE_AND_SCHEMA.md`](./ARCHITECTURE_AND_SCHEMA.md) before using a model or writing a serializer.

### Rule 3: No Superficial Symptom Patches
- **NEVER** resolve errors by masking symptoms, swallowing exceptions silently (`try...except: pass`), returning dummy fallback data, or deleting failing unit tests.
- When an error occurs, identify and fix the root cause breaking the underlying contract.

### Rule 4: Error Logging Obligation
- Any error, test failure, build error, or unexpected exception encountered during execution **MUST** be logged in [`docs/ERROR_LOGS_AND_RESOLUTIONS.md`](./ERROR_LOGS_AND_RESOLUTIONS.md) with its Error ID (`ERR-xxx`), root cause, and fix diff once resolved.

### Rule 5: Progress Update Obligation
- Upon successfully completing a task or sprint item:
  1. Mark the item as completed (`[x]`) in [`docs/PROGRESS_AND_ROADMAP.md`](./PROGRESS_AND_ROADMAP.md).
  2. Update component status indicators if applicable.

### Rule 6: Verification Requirement
- **NEVER** claim a task is complete until concrete runtime verification commands have passed:
  - **Backend**: `python manage.py check` & `pytest`
  - **Frontend**: `npm run build`
  - **Database**: `python manage.py makemigrations --check`

### Rule 7: ECC-main Pattern Library Reference
- A local pattern library is available at `c:\Dev\Active Projects\Notion\ECC-main\skills/`.
- When designing or implementing specialized modules (e.g. Django API security, Redis reservation locks, Next.js App Router patterns, or payment webhooks), agents are encouraged to read the corresponding skill directory in `ECC-main/skills/<skill-name>/` for production-grade architectural references.

---

## 🌿 Git Version Control & GitFlow Strategy

### 1. Branching Strategy (GitFlow)
- **`main`**: Production-ready, stable releases only.
- **`develop`**: Active integration branch where verified features and sprint items land.
- **`feature/*` or `fix/*`**: Task-specific branches created by AI agents and developers for individual features (e.g. `feature/jwt-auth`, `fix/redis-ttl`, `feature/zoom-oauth`).

### 2. Commit Message Standards
- Use **descriptive, free-form commit messages** clearly explaining what was added, updated, or fixed.
- Examples:
  - `Added JWT authentication for student and teacher login`
  - `Implemented 10-minute Redlock reservation lock in backend bookings service`
  - `Updated documentation suite with GitFlow version control strategy`
- Mandatory pre-commit verification: Always run `pytest` and `npm run build` before pushing commits to `develop` or `main`.

---

## 🤝 Hand-Off Protocol Between Claude, Codex, & Antigravity

When transferring work or starting a new session:

1. **State Summary**: State what phase/task was completed and what files were modified.
2. **Document Check**: Verify that `docs/PROGRESS_AND_ROADMAP.md` and `docs/ERROR_LOGS_AND_RESOLUTIONS.md` are updated.
3. **Branch Hygiene**: Verify that you are working on the correct `feature/*` branch and merging cleanly into `develop`.
