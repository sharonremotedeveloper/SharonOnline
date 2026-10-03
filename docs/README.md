# Sharon's ESL Marketplace Platform — Master Documentation Hub

Welcome to the central technical and operational documentation hub for **Sharon's ESL Marketplace Platform**.

This documentation suite is engineered to serve as a single source of truth for all human developers (**Anesu MUPESA**) and collaborating AI coding agents (**Antigravity/Gemini**, **Claude**, **Codex**).

---

## 🗺️ Documentation Sitemap & Quick Links

| Document | Purpose & Description | Target Audience |
| :--- | :--- | :--- |
| 📖 [**`PROJECT_CONTEXT.md`**](./PROJECT_CONTEXT.md) | Business model, target market (Japan/Korea students & SA tutors), pricing spread, and core domain rules. | All Collaborators |
| 📐 [**`ARCHITECTURE_AND_SCHEMA.md`**](./ARCHITECTURE_AND_SCHEMA.md) | Comprehensive system architecture, Django models schema, Redis locking engine, Zoom/GCal APIs, and Cloudflare topology. | Lead Architect & AI Agents |
| 🗺️ [**`MASTER_MODULE_ROADMAP_AND_ARCHITECTURE.md`**](./MASTER_MODULE_ROADMAP_AND_ARCHITECTURE.md) | Exhaustive 11-module master delivery roadmap, sub-stages, completion tracking, and Phase 2 deferral ledger. | Lead Architect & All Agents |
| 🎨 [**`UI_VERTICAL_SLICE_MIGRATION_PLAN.md`**](./UI_VERTICAL_SLICE_MIGRATION_PLAN.md) | Technical guide for vertical slice migration of Figma React UI into Next.js 14 App Router (Slices 0 to 8). | Frontend Devs & AI Agents |
| 🚀 [**`PROGRESS_AND_ROADMAP.md`**](./PROGRESS_AND_ROADMAP.md) | 6-Phase delivery roadmap, current sprint status, component progress matrix, and 46-view master inventory. | Lead Architect & AI Agents |
| ⚡ [**`ERROR_LOGS_AND_RESOLUTIONS.md`**](./ERROR_LOGS_AND_RESOLUTIONS.md) | Standardized error ledger (`ERR-xxx`) tracking stack traces, root cause analysis, code fix diffs, and resolution status. | All AI Agents & Devs |
| 🤖 [**`AI_AGENT_COLLABORATION_RULES.md`**](./AI_AGENT_COLLABORATION_RULES.md) | Mandatory protocol for AI agents (Claude, Codex, Antigravity) and human devs on updating docs, logging errors, and code quality. | All AI Agents |
| 🧭 [**`PRODUCTION_READINESS_PLAN.md`**](./PRODUCTION_READINESS_PLAN.md) · [**`PHASE_10_EXECUTION_PLAN.md`**](./PHASE_10_EXECUTION_PLAN.md) | The Phase 7-16 task list with status, and the detailed plan for what is being built next (real payments). Start here to see what to work on. | Lead Architect & All Agents |
| 📅 [**`BOOKING_STATE_MACHINE.md`**](./BOOKING_STATE_MACHINE.md) · [**`BOOKING_HOLDS.md`**](./BOOKING_HOLDS.md) · [**`BOOKING_LIST.md`**](./BOOKING_LIST.md) · [**`ZOOM_ATTENDANCE.md`**](./ZOOM_ATTENDANCE.md) · [**`LESSON_REVIEWS.md`**](./LESSON_REVIEWS.md) | How a booking moves, holds its slot, is listed, and is verified against Zoom attendance; how reviews stay private. | Backend & AI Agents |
| 💸 [**`CANCELLATION_AND_REFUNDS.md`**](./CANCELLATION_AND_REFUNDS.md) · [**`SETTLEMENT_PATHS.md`**](./SETTLEMENT_PATHS.md) · [**`DECISIONS_D1_D12.md`**](./DECISIONS_D1_D12.md) | The money policy (cancel, reschedule, refunds, credit expiry, strikes), where every outcome's money goes, and the product decisions behind them. | Backend, Finance & AI Agents |
| ⚙️ [**`ENVIRONMENT_AND_TESTING.md`**](./ENVIRONMENT_AND_TESTING.md) | Local environment setup, environment variables, Pytest execution, Next.js build verification, and deployment specs. | Engineering Team |

---

## ⚡ Quickstart Context for AI Agents & Collaborators

Before writing code or making architectural changes, all collaborators must execute the following workflow:

1. **Read Context**: Check [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md) and [`ARCHITECTURE_AND_SCHEMA.md`](./ARCHITECTURE_AND_SCHEMA.md).
2. **Check Roadmap**: Review active sprint tasks in [`PROGRESS_AND_ROADMAP.md`](./PROGRESS_AND_ROADMAP.md).
3. **Follow Collaboration Rules**: Enforce rules defined in [`AI_AGENT_COLLABORATION_RULES.md`](./AI_AGENT_COLLABORATION_RULES.md).
4. **Log Errors**: Record any encountered bugs or runtime failures in [`ERROR_LOGS_AND_RESOLUTIONS.md`](./ERROR_LOGS_AND_RESOLUTIONS.md).
5. **Verify**: Execute automated tests (`pytest backend/`, `npm run build --prefix frontend`) before claiming task completion.
