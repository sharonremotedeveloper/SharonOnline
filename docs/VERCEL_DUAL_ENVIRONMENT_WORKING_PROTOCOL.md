# Vercel Dual-Environment Deployment Working Protocol

**Status:** Planned, not yet implemented

**Scope:** The Sharon Online deployment stream for:

- development on a Vercel-generated URL;
- production on `topteacheracademy.com`;
- separate development and production backend/provider resources; and
- promotion of the exact tested development code to production.

This document is mandatory for every agent and human collaborator who works on this deployment stream.

## 1. Shared-branch rule

All agents working on this deployment stream work in the **same shared branch**. Do not create separate feature branches or isolated worktrees for this part unless Anesu explicitly changes this rule in chat.

The shared branch is the active deployment branch named in the current progress report. Before starting work, every agent must confirm the branch name and current commit with:

```powershell
git status --short --branch
git rev-parse HEAD
```

Agents must not reset, force-push, rewrite history, or discard another agent's changes. Pull or inspect the latest shared-branch state before editing. If two changes overlap, stop and report the conflict instead of resolving it by deleting or reverting another agent's work.

The repository's normal product policy still applies: `develop` is integration and `main` is production. The shared deployment branch is for coordinated preparation; promotion to `main`, production deployment, DNS changes, account changes, and secret changes require Anesu's explicit approval.

## 2. Mandatory progress reporting

Progress reporting is an acceptance requirement for this stream, not an optional status update.

Every agent must post a report before beginning work, after each meaningful checkpoint, and before stopping. The report must be added to the current progress document or the linked deployment work log, and must include:

1. agent name and timestamp;
2. shared branch and starting commit;
3. exact scope attempted;
4. files changed, or `none` for read-only work;
5. commands and focused checks run;
6. results, including counts and failure output summaries;
7. environment/resource touched (`dev`, `prod`, or `none`);
8. blockers, owner decisions, and approval needed;
9. next action and handoff owner; and
10. whether the work is complete, partial, blocked, or unverified.

Never report “deployed”, “production-ready”, or “verified” when only local tests or a build passed. Distinguish local checks, CI, hosted development checks, provider checks, production checks, and DNS cutover.

## 3. Required progress record

The lead agent must maintain a dated progress table in [`PROGRESS_AND_ROADMAP.md`](./PROGRESS_AND_ROADMAP.md) under the Vercel dual-environment workstream. At minimum, keep these fields current:

| Field | Required value |
| :--- | :--- |
| Current shared branch | Exact branch name |
| Current commit | Exact SHA |
| Development deployment | Vercel deployment URL and SHA, or `not deployed` |
| Development backend | Railway service/release and SHA, or `not deployed` |
| Production deployment | Vercel/Railway release and SHA, or `not deployed` |
| Database migration | Version, target environment, and release SHA |
| Provider checks | Each provider with `not started`, `passed`, `failed`, or `blocked` |
| DNS/domain | Registrar, DNS authority, Vercel attachment, TLS status |
| Verification gates | Passed gates and outstanding gates |
| Blockers/decisions | Owner, decision required, and stop condition |
| Last update | Timestamp and agent |

Failed commands and unexpected behavior must also be recorded in [`ERROR_LOGS_AND_RESOLUTIONS.md`](./ERROR_LOGS_AND_RESOLUTIONS.md) with an `ERR-xxx` identifier.

## 4. Work coordination

Before editing:

1. Read `PROJECT_CONTEXT.md`, `AI_AGENT_COLLABORATION_RULES.md`, this document, and the current progress report.
2. Read the current deployment/account documents, especially `TOOL_ACCESS_AND_ACCOUNTS.md`, `RAILWAY_SETUP.md`, and `ENVIRONMENT_AND_TESTING.md`.
3. Check the shared branch status and recent changes.
4. Announce the intended files and scope in the progress report.
5. Check whether another agent is editing the same files.

During editing:

- Keep changes small and reviewable.
- Do not put secrets in files, logs, commits, or reports.
- Do not use production credentials for development verification.
- Do not connect development to production databases, Redis, R2, email, payments, OAuth clients, Daily, or webhooks.
- Do not deploy, change DNS, create accounts, change billing, or alter provider settings without the required owner approval and account confirmation.

Before handoff:

- update the progress table;
- list every file changed;
- record focused checks and their exact result;
- record anything not tested;
- identify the next agent and next safe action.

## 5. Deployment architecture to implement

Use two Vercel projects connected to the same repository:

- development: Vercel-generated URL only;
- production: `topteacheracademy.com`, with an owner-approved `www` redirect policy.

The Next.js server-side BFF must remain the only browser-to-Django path. Production must require `INTERNAL_API_URL`; it must not fall back to `NEXT_PUBLIC_API_URL` or localhost. Add tests that reject missing, localhost, browser-visible, or cross-environment API targets.

Development and production must have separate Railway API/worker/beat services, Neon databases, Upstash databases, R2 credentials, Daily credentials/webhooks, Google OAuth clients/callbacks, Resend secrets, and payment credentials. PayPal and PayFast remain sandbox-only until Anesu explicitly authorizes live mode.

The production compose file is not itself proof of a hosted contract. Hosted services must have explicit commands, health checks, environment-variable contracts, source SHA or immutable image digest, worker/beat compatibility, and a separate one-shot migration release.

## 6. Promotion rule

The required release path is:

1. Work on the shared deployment branch.
2. Merge the reviewed changes into `develop`.
3. Run CI and record the exact tested `develop` SHA.
4. Deploy that SHA to development Vercel, Railway, workers, beat, and the intended development database migration release.
5. Complete hosted development and provider-sandbox acceptance.
6. Promote the same SHA to `main` using a history-preserving merge/fast-forward where possible.
7. If a merge method creates a new commit, promote the immutable artifact created from the tested SHA and record its source SHA, tree hash, image digests, Vercel deployment IDs, Railway release IDs, and migration version.
8. Run production gates and obtain explicit cutover approval.

Never deploy a moving branch name and call that exact-code promotion.

## 7. Completion standard

This deployment stream is complete only when the progress report shows:

- development and production resource separation verified;
- server-only API boundary tests passing;
- cookie, proxy, CORS, CSRF, and cross-environment isolation checks passing;
- deep health, structured errors, uptime alerts, backups/PITR, restore drill, and rollback verified;
- provider callbacks and secrets distinct per environment;
- migrations tested using expand/contract compatibility;
- `topteacheracademy.com` DNS/TLS and `www` policy verified;
- exact tested source/artifact identity proven across Vercel, API, worker, beat, and migrations; and
- all owner decisions and stop conditions resolved.

Until then, report the stream as `in progress`, `blocked`, or `unverified`—never complete.
