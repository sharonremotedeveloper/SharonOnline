# Railway First-Time Setup and Current Deployment State (MANDATORY before any agent touches Railway)

**Applies to:** Claude, Codex, Antigravity/Gemini, and humans.
**Prerequisite:** read [`TOOL_ACCESS_AND_ACCOUNTS.md`](./TOOL_ACCESS_AND_ACCOUNTS.md). Railway must be used **only** under `sharonremotedeveloper@gmail.com`.

| Item | Value |
| :--- | :--- |
| Railway project ID | `e2b11747-5519-4139-bd34-a658affea42a` (`sharon-online-prod`) |
| Account | `sharonremotedeveloper@gmail.com` (nothing else) |
| Intended role | Hosts the Django API and Celery worker/beat (see `ENVIRONMENT_AND_TESTING.md` §4). Postgres = Neon, Redis = Upstash (not Railway add-ons unless Anesu decides otherwise). |
| Container source | `Project-files/backend/Dockerfile` |

**Current state checked 2026-10-15:** Railway identity is `sharonremotedeveloper@gmail.com`. The canonical production project is `sharon-online-prod` (`e2b11747-5519-4139-bd34-a658affea42a`), environment `production` (`dd70ab8a-91c2-47cb-ba27-cdab00a38d74`). API, worker, and Beat are pinned to exact SHA `d5608dd8019d9a1169052b3e81b83c30698dbaa0`; all three deployments succeeded. The API custom domain is `api.topteacheracademy.com`. Public `/api/ready/` and `/api/scheduler-ready/` both returned 200 `ready` with `Cache-Control: no-store` after Beat-to-worker execution. The historical identifiers below are audit history, not the active deployment.

---

## 0. Gate: confirm the account FIRST

```bash
railway --version       # CLI installed (5.59.0 at time of writing)
railway whoami          # read-only: shows the logged-in user
```

- The email shown **must equal `sharonremotedeveloper@gmail.com`**. If it shows anything else (e.g. `anesu@intern-mail.metabox.technology`) or you're logged out: **STOP. Do not link, deploy, or change variables.** Tell Anesu, who runs `railway login` in a browser as the correct account. Agents never enter credentials, and never use a `RAILWAY_TOKEN` or other token to bypass this.
- After a successful check, append a line to §4 of `TOOL_ACCESS_AND_ACCOUNTS.md` and upgrade the Railway row to `CONFIRMED`.
- Re-run this gate at the start of every session.

## 1. One-time setup (run in `Project-files/`)

```bash
npm i -g @railway/cli            # only if `railway` is missing
railway login                    # HUMAN ONLY: Anesu signs in as sharonremotedeveloper@gmail.com
railway whoami                   # re-run Gate §0
railway link --project e2b11747-5519-4139-bd34-a658affea42a   # bind this folder to the canonical production project only if explicitly authorized
railway status                   # read-only: confirm project / environment / service
```

If `railway link` asks for an environment or service, pick the one Anesu names; if unsure, ask. Do not create new projects, environments or services without approval.

## 2. Current services and historical audit

| Environment / service | Current state | Evidence |
| :--- | :--- | :--- |
| production / `backend-api-production` | SUCCESS, pinned `main` at `d5608dd`; custom domain `api.topteacheracademy.com`; Railway healthcheck stays liveness-only at `/api/health/` | Deployment `1978f8cd-4748-4b8f-b93b-d4462bd0a784`; public `/api/ready/` and `/api/scheduler-ready/` returned 200 |
| production / `celery-worker-production` | SUCCESS, pinned `main` at `d5608dd`; new heartbeat task registered, received and completed | Deployment `a61cfd7a-cf7b-4fa7-a88d-69370ebbf677` |
| production / `celery-beat-production` | SUCCESS, pinned `main` at `d5608dd`; heartbeat dispatched at 20:19 UTC | Deployment `6e8e4056-3af6-4d68-a02c-3a066def3d51` |

The earlier development `dcaa9c7` deployments (`12d3dd2a`, `aff043fc`, `426d93fe`) and production `b33743a` deployments (`8ddf565b`, `2ba3fe91`, `562b5055`) were past checkpoints, not current state. Re-read provider status before relying on any deployment ID. No variable values were printed during this release.

## 3. Variables & secrets

- Set via the Railway dashboard or `railway variables` by Anesu; see the variable names in `ENVIRONMENT_AND_TESTING.md` §2 / `.env.example`. `DATABASE_URL` points to Neon, `REDIS_URL` to Upstash.
- Never print, log, commit, or paste variable values. Listing variable *names* is fine; dumping values is not.
- Production must set `DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG` off, a real `SECRET_KEY`, and payment gateways stay **sandbox** until Anesu authorizes live mode.

## 4. Deploy — approval required

`railway up`, redeploys, restarts, variable changes, domain changes, and deleting services/volumes/environments are outward-facing. **Do not run any of them without Anesu's explicit go-ahead in chat for that specific action**, and only after the §0 gate passes. Run `python manage.py check`, `makemigrations --check` and `pytest` first (collab Rule 6). Reading logs (`railway logs`) and `railway status` are safe once the gate passes.

## 5. One-shot production migration release

The migration job is a separate Railway release using the same backend image and
exact source SHA as the API/worker/beat release. It must not be attached to the
API startup command and must not share a pooled application connection.

Use this command for the one-shot service/release command:

```text
python scripts/run_production_migrations.py --apply
```

The release must provide these environment variables through Railway's
encrypted variable store (never in source or logs):

```text
DJANGO_SETTINGS_MODULE=config.settings.production
DATABASE_URL_UNPOOLED=<Neon direct/unpooled URL>
PRODUCTION_MIGRATION_APPROVED=true
```

`run_production_migrations.py` maps the explicit unpooled URL to Django's
`DATABASE_URL` only inside the child migration process. It refuses local/Docker
targets, refuses to run without the exact production settings module, requires
an explicit approval flag for `--apply`, and accepts no arbitrary Django
migration arguments (`--fake`, `--run-syncdb`, or a partial target). `--plan`
is the non-applying preview mode.

Before setting `PRODUCTION_MIGRATION_APPROVED`, review the plan against the
expand/contract policy and confirm a current Neon restore point/backup through
the owner-controlled database workflow. This implementation does not run a
migration, create a restore point, change Railway, or alter provider
infrastructure. Do not use this path for destructive schema changes; split
those into an explicitly reviewed, backwards-compatible release first.

The job is complete only after its exit code, exact source SHA, migration plan
or applied version, and target environment are recorded. A successful local
test or image build is not production migration evidence.

## 6. Status

| Step | State |
| :--- | :--- |
| CLI installed (5.59.0) | Present |
| Account identity | **CONFIRMED 2026-10-15 by read-only Railway MCP identity check: `sharonremotedeveloper@gmail.com`** |
| Canonical production project | **CONFIRMED 2026-10-14; `sharon-online-prod` / `e2b11747-5519-4139-bd34-a658affea42a`** |
| Current service/deployment state | **CONFIRMED 2026-10-15; all three production services SUCCESS on exact SHA `d5608dd`** |
| `railway link` to the canonical project | Not checked or changed; local CLI linkage is not required for MCP evidence |

## 7. Production scheduler freshness and external check

`GET /api/scheduler-ready/` is separate from the API liveness and database/Redis
readiness endpoints. Beat dispatches `apps.notifications.tasks.scheduler_heartbeat_task`
every 60 seconds onto `scheduler_beat`; the production worker consumes that queue
and writes a timestamped Redis key with a 180-second TTL. The API returns generic
`ready` only while the last executed task is at most 150 seconds old. The Redis
read is cached for 30 seconds per API process and has a bounded child-process
deadline. A 503 indicates a missing/stale heartbeat or an unavailable check;
it does **not** identify which of Beat, broker, worker, or Redis failed.

Never use this endpoint as Railway's restart healthcheck: a scheduler outage
should page an operator, not restart an otherwise healthy API. The production
uptime GitHub Actions workflow on the repository default branch checks the
public site, `/api/ready/`, and `/api/scheduler-ready/` every ten minutes.
It is credential-free and best-effort: scheduled Actions can be delayed or
skipped, so it is not a strict availability SLA. The Sharon GitHub account has
Actions notifications for failed workflows enabled on GitHub and by email.
Workflow `384771384` was active and manual dispatch `38631600839` succeeded
on 2026-10-15. Scheduled run `38674318881` subsequently passed all three
checks, but recent runs were spaced about 30-40 minutes apart despite the
ten-minute cron. No failure notification has been induced or received.

On a failed check, inspect the exact workflow run and time, then the canonical
Railway project/service IDs and deployment-specific API, worker, and Beat logs.
Check whether Beat emitted the task, whether the worker received and completed
it, and whether Redis was reachable. Recheck the public endpoint after the
next Beat interval; the API may cache a failed result for up to 30 seconds.
Do not change secrets, restart services, or switch the API healthcheck based on
one failed scheduled run. Record the incident and evidence in
`ERROR_LOGS_AND_RESOLUTIONS.md` and `PROGRESS_AND_ROADMAP.md`.
