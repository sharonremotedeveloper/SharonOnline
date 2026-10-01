# Neon First-Time Setup (MANDATORY before any agent touches Neon)

**Applies to:** Claude, Codex, Antigravity/Gemini, and humans.
**Prerequisite:** read [`TOOL_ACCESS_AND_ACCOUNTS.md`](./TOOL_ACCESS_AND_ACCOUNTS.md). Neon must be used **only** under `sharonremotedeveloper@gmail.com`.

| Item | Value |
| :--- | :--- |
| Neon project ID | `sweet-bonus-69458238` |
| Branch to link | `production` |
| Account | `sharonremotedeveloper@gmail.com` (nothing else) |
| Planned bucket | `sharonbucket` (`public_read`) |
| Planned function | `api` → `./hello.ts` |

---

## 0. Gate: confirm the account FIRST

```bash
neon --version        # must be 7.x or newer (older 4.x is the legacy CLI)
neon me               # read-only: shows the logged-in user
```

- `neon me` **Email must equal `sharonremotedeveloper@gmail.com`.** If it shows anything else (e.g. `anesu@intern-mail.metabox.technology`), or you are not logged in: **STOP. Do not run steps 2–7.** Tell Anesu, who runs `neon login` in a browser as the correct account (agents cannot and must not enter credentials). Do not use API keys or `neon profile` to work around this.
- After a successful check, append a line to §4 of `TOOL_ACCESS_AND_ACCOUNTS.md` and upgrade the Neon row to `CONFIRMED`.
- Re-run this gate at the start of every session and after any login change.

## 1. One-time setup (run in `Project-files/`)

Run in order. Steps already completed by another agent (check `git status` / `neon.ts` / `neon link` state) need not be repeated.

```bash
npm i -g neon@latest          # 1. install CLI (Volta/npm; verify with neon --version)
neon login                    # 1b. HUMAN ONLY: Anesu signs in as sharonremotedeveloper@gmail.com
neon skills -y                # 2. install Neon agent skills
neon mcp -y                   # 3. install/configure Neon MCP server for this machine
neon link --project-id sweet-bonus-69458238 --branch production -y   # 4. bind folder to project
neon config init              # 5. generate neon.ts
```

Re-run the **Gate (§0)** after `neon login` and before step 2.

## 2. Config files (step 6)

`neon.ts` (project root `Project-files/`):

```ts
import { defineConfig } from "@neon/config/v1";

export default defineConfig({
  auth: true,
  preview: {
    // Upgrade to a paid plan to enable AI Gateway for your project.
    // aiGateway: true,
    buckets: {
      sharonbucket: { access: "public_read" },
    },
    functions: {
      api: { name: "api", source: "./hello.ts" },
    },
  },
});
```

`hello.ts`:

```ts
export default async function hello(): Promise<Response> {
  return new Response("Hello from Neon Functions");
}
```

## 3. Deploy (step 7) — approval required

```bash
neon deploy
```

**`neon deploy` publishes to the linked `production` branch.** Do not run it without Anesu's explicit go-ahead in chat for that specific deploy, and only after the §0 gate passes. `public_read` on `sharonbucket` makes bucket contents publicly readable: never put private files (TEFL certificates, IDs, vetting documents) there; those belong in the private R2 vault (`PrivateMediaR2Storage`).

## 4. Rules while working with Neon

- Branch-first: for schema experiments, create a Neon branch, don't alter `production` directly. Destructive MCP tools (delete project/branch, reset, drop) need Anesu's explicit approval each time.
- Never print or commit connection strings, API keys, or tokens. `DATABASE_URL` lives in `.env` only.
- Log any failure in `ERROR_LOGS_AND_RESOLUTIONS.md` (`ERR-xxx`).
- Neon MCP tools require the same account check: confirm `neon me` / `list_organizations` matches before use.

## 5. Open question for Anesu

The backend is Django + Celery on Railway/Render with Neon as plain Postgres. `neon.ts` here also enables Neon Auth, Functions and Storage, which overlap with Django JWT auth and Cloudflare R2. Confirm intended scope before anything beyond the database is relied on in production.

## 6. Status

| Step | State |
| :--- | :--- |
| 1 CLI installed (7.0.3) | Done 2026-10-02 (Claude) |
| 1b Login as `sharonremotedeveloper@gmail.com` | Done 2026-10-02 (`neon me` verified) |
| 2 `neon skills` | Done 2026-10-02: project-level skills for claude-code, codex, antigravity (`.claude/skills`, `.agents/skills`, `skills-lock.json`) |
| 3 `neon mcp` | Done 2026-10-02: project-level OAuth MCP in `.mcp.json` (Claude) and `.codex/config.toml` (Codex), pinned to project `sweet-bonus-69458238`. **Antigravity has no project-level MCP**, so its user-level `~/.gemini/config/mcp_config.json` Neon entry is OAuth + pinned to the project (done). First use prompts a Neon sign-in: use `sharonremotedeveloper@gmail.com`. |
| 4–7 link / config init / neon.ts / deploy | Not started |

**Global Neon MCP entries** (API-key based, bound to the wrong org `Anesu`) were removed from `~/.claude.json` and `~/.codex/config.toml` on 2026-10-02. Do not re-add a global Neon MCP. After first OAuth sign-in, verify with `list_organizations`: it must return `org-lucky-pine-32944571`.
