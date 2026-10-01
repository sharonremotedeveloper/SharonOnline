# Railway First-Time Setup (MANDATORY before any agent touches Railway)

**Applies to:** Claude, Codex, Antigravity/Gemini, and humans.
**Prerequisite:** read [`TOOL_ACCESS_AND_ACCOUNTS.md`](./TOOL_ACCESS_AND_ACCOUNTS.md). Railway must be used **only** under `sharonremotedeveloper@gmail.com`.

| Item | Value |
| :--- | :--- |
| Railway project ID | `816aac81-bae6-40c4-b2de-48dc68d55709` |
| Account | `sharonremotedeveloper@gmail.com` (nothing else) |
| Intended role | Hosts the Django API and Celery worker/beat (see `ENVIRONMENT_AND_TESTING.md` §4). Postgres = Neon, Redis = Upstash (not Railway add-ons unless Anesu decides otherwise). |
| Container source | `Project-files/backend/Dockerfile` |

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
| `api` | Gunicorn serving `config.wsgi` (settings `config.settings.production`) | Public domain; health check `GET /api/health/` |
| `celery-worker` | `celery -A config worker -l info -c 2 -Q celery,scheduler_beat,financial_escrow,notifications,critical_io` | Must consume all five queues |
| `celery-beat` | `celery -A config beat -l info` | Exactly one instance (beat is not horizontally scalable) |

Status: **none verified** — update this table after the first confirmed `railway status`.

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
| Login as `sharonremotedeveloper@gmail.com` | **BLOCKED — CLI currently logged in as `anesu@intern-mail.metabox.technology`; Anesu must re-login** |
| `railway link` to `816aac81-…` | Not done (blocked by gate) |
