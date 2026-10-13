# Railway First-Time Setup and Current Deployment State (MANDATORY before any agent touches Railway)

**Applies to:** Claude, Codex, Antigravity/Gemini, and humans.
**Prerequisite:** read [`TOOL_ACCESS_AND_ACCOUNTS.md`](./TOOL_ACCESS_AND_ACCOUNTS.md). Railway must be used **only** under `sharonremotedeveloper@gmail.com`.

| Item | Value |
| :--- | :--- |
| Railway project ID | `816aac81-bae6-40c4-b2de-48dc68d55709` |
| Account | `sharonremotedeveloper@gmail.com` (nothing else) |
| Intended role | Hosts the Django API and Celery worker/beat (see `ENVIRONMENT_AND_TESTING.md` §4). Postgres = Neon, Redis = Upstash (not Railway add-ons unless Anesu decides otherwise). |
| Container source | `Project-files/backend/Dockerfile` |

**Read-only state checked 2026-10-14:** Railway identity matched `sharonremotedeveloper@gmail.com`. `SharonRailway` has `development` and `production` environments. The development API, worker, and beat services all have successful deployments from `develop` commit `dcaa9c7`; the production API service exists but its `dcaa9c7` deployment failed at `/api/health/`. No variables, secrets, domains, staged changes, or infrastructure were changed by this check.

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
railway link --project 816aac81-bae6-40c4-b2de-48dc68d55709   # bind this folder to the project
railway status                   # read-only: confirm project / environment / service
```

If `railway link` asks for an environment or service, pick the one Anesu names; if unsure, ask. Do not create new projects, environments or services without approval.

## 2. Expected services (to be confirmed by Anesu / filled in as built)

| Service | Command | Notes |
| :--- | :--- | :--- |
| Environment / service | Current read-only state | Evidence |
| :--- | :--- | :--- |
| development / `backend-api-development` | SUCCESS from develop / dcaa9c7; Railway domain `backend-api-development-development-9d0e.up.railway.app`; health check `/api/health/` | Deployment `12d3dd2a-8fed-477e-bea8-214b8bbccaba` |
| development / `celery-worker-development` | SUCCESS from develop / dcaa9c7 | Deployment `aff043fc-cf59-4e93-ac99-8eb6ebca9a9e` |
| development / `celery-beat-development` | SUCCESS from develop / dcaa9c7 | Deployment `426d93fe-9746-4db9-9317-c8d4b4935f73` |
| production / `backend-api-production` | FAILED from develop / dcaa9c7 at `/api/health/`; no Railway service domain; no live production worker/beat | Deployment `27aa82c3-ea07-4048-82e6-ef65dc87266a` |

Staged-but-not-deployed state observed read-only: development patch `192cc8f3-5894-404d-b390-9b706586a046` contains three Daily-related changes; production patch `3a580cef-6dfb-4e7b-ad36-6fd23d8a7ce2` contains six changes. Variable values were not read.

## 3. Variables & secrets

- Set via the Railway dashboard or `railway variables` by Anesu; see the variable names in `ENVIRONMENT_AND_TESTING.md` §2 / `.env.example`. `DATABASE_URL` points to Neon, `REDIS_URL` to Upstash.
- Never print, log, commit, or paste variable values. Listing variable *names* is fine; dumping values is not.
- Production must set `DJANGO_SETTINGS_MODULE=config.settings.production`, `DEBUG` off, a real `SECRET_KEY`, and payment gateways stay **sandbox** until Anesu authorizes live mode.

## 4. Deploy — approval required

`railway up`, redeploys, restarts, variable changes, domain changes, and deleting services/volumes/environments are outward-facing. **Do not run any of them without Anesu's explicit go-ahead in chat for that specific action**, and only after the §0 gate passes. Run `python manage.py check`, `makemigrations --check` and `pytest` first (collab Rule 6). Reading logs (`railway logs`) and `railway status` are safe once the gate passes.

## 5. Status

| Step | State |
| :--- | :--- |
| CLI installed (5.59.0) | Present |
| Account identity | **CONFIRMED 2026-10-14 by read-only Railway MCP identity check: `sharonremotedeveloper@gmail.com`** |
| `SharonRailway` project | **CONFIRMED 2026-10-14; development and production environments visible** |
| Current service/deployment state | **CONFIRMED 2026-10-14; see §2. No changes made.** |
| `railway link` to `816aac81-…` | Not checked or changed; local CLI linkage is not required for the read-only MCP evidence |
