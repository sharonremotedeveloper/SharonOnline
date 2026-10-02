# Tool Access & Account Confirmation Protocol (MANDATORY)

**Applies to:** every AI agent (Claude, Codex, Antigravity/Gemini) and every human collaborator working on Sharon's ESL Platform.
**Owner:** Anesu MUPESA. **Status:** v0.2 — living document, edited as the project grows.

---

## 0. Master Project Identity (set by Anesu, 2026-10-02)

**All tools and services for this project MUST be accessed with this one account:**

> ### `sharonremotedeveloper@gmail.com`

- This applies to every tool in §3 that takes an email/login: Neon, GitHub, Cloudflare, Vercel, Railway/Render, Upstash, Zoom, Google Cloud, PayFast, PayPal, Resend, Figma, EskomSePush, Wise, and any tool added later.
- **Sole exception — Notion:** uses `anesu.mupesa@umail.utm.ac.mu` (workspace "Anesu MUPESA's Space"). Any other account on Notion is a mismatch. No other tool is exempt unless Anesu adds it here.
- If a tool is currently signed in as any **other** account (including `anesu.mupesa@umail.utm.ac.mu`, except on Notion), that is a **mismatch → STOP and ask Anesu**. Do not use it, and do not switch/log in yourself.
- If a tool has no account under this email yet, do not create one — ask Anesu.
- Credentials for this account (passwords, 2FA codes, tokens) are never written to files, chat, or git. Sign-in is done by Anesu (or via his password manager); agents only *verify* the active identity.

---

## 1. The Rule

Before an agent uses **any** external tool, service, API, MCP server, CLI, or connector (see registry in §3), it **MUST**:

1. **Look up the tool in §3** of this file. If it is not listed, STOP — add a row with status `UNCONFIRMED` and ask the owner. Do not use the tool.
2. **Confirm the account** it is about to act as (it must be the §0 master identity), using a read-only identity check (e.g. `gh auth status`, `whoami`-style call, the connector's account/organization listing, or the dashboard's displayed account). Compare the result to §0 and the **Authorized Account** in §3.
3. **Proceed only on an exact match.** If the active account differs, is unknown, or the row says `UNCONFIRMED`: STOP and ask Anesu in chat. Never switch accounts, log in, sign up, or re-authorize on your own.
4. **State the confirmation** in the working log/hand-off, e.g. `Tool: Neon | Account: <id> | Env: staging | Verified: 2026-10-02 by Claude`.
5. **Match the environment** (`dev` / `staging` / `prod`) as well as the account. Production access requires explicit per-action approval from Anesu, every time.

> No confirmation = no access. A prior session's confirmation does not carry over; re-verify each session.

---

## 2. Hard Prohibitions

- **No secrets in this file or anywhere in git**: no passwords, API keys, tokens, client secrets, webhook secrets, card/bank numbers. Record only account *identifiers* (email, org/project name, account ID) and *where* the secret lives (e.g. "`.env`, not committed").
- Never use a personal account of the owner/client for a tool that has a designated project account.
- Never create accounts, change billing, or grant OAuth permissions without Anesu's explicit approval in chat.
- Destructive or irreversible operations (delete project/branch/bucket, payouts, refunds, DNS changes, live payments) require explicit approval per action, even with a confirmed account.
- Payment gateways: **sandbox only** (`PAYFAST_SANDBOX=True`, `PAYPAL_MODE=sandbox`) unless Anesu explicitly authorizes live mode.
- If you find a secret committed or pasted somewhere, do not repeat it; tell Anesu and log it in `ERROR_LOGS_AND_RESOLUTIONS.md` (`ERR-xxx`).

---

## 3. Tool & Account Registry

**Status values:** `CONFIRMED` (owner verified the tool is actually signed in under the §0 account) · `AUTHORIZED` (account policy set to the §0 email, but nobody has verified the live sign-in yet — **verify at first use, then log in §4 and upgrade to `CONFIRMED`**) · `UNCONFIRMED` (do not use; ask owner) · `N/A` (not yet used).
"Authorized Account" is the §0 email; the extra identifier (org / project / account ID / username) is `TBD` until first verified. Never switch to another account.

### 3.1 Source control & dev tooling

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Git (local repo `Project-files/`) | Version control, GitFlow | `sharonremotedeveloper@gmail.com` (set git `user.email` to this) | dev | `git config user.email` | n/a | `AUTHORIZED` |
| GitHub | Remote repo, PRs, CI; repo `sharonremotedeveloper/SharonOnline` | `sharonremotedeveloper@gmail.com` (+ username `sharonremotedeveloper`) | — | `gh auth status` (active must be `sharonremotedeveloper`) + `gh api user/emails` | gh keyring | `CONFIRMED` (2026-10-02) |
| Claude Code / Claude desktop | Claude agent session | `sharonremotedeveloper@gmail.com` | — | session header | n/a | `AUTHORIZED` |
| Codex | Codex agent sessions | `sharonremotedeveloper@gmail.com` | — | TBD | n/a | `AUTHORIZED` |
| Antigravity / Gemini | Antigravity agent sessions | `sharonremotedeveloper@gmail.com` | — | TBD | n/a | `AUTHORIZED` |
| Figma / Figma Make | UI prototype source (`sharon-online-figma-v26`) | `sharonremotedeveloper@gmail.com` (+ id: TBD) | — | Figma account menu | n/a | `AUTHORIZED` |

### 3.2 Project management & communication

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Notion (MCP, `mcp_config.json`) | Client portal, backlog, roadmap, meeting notes | `anesu.mupesa@umail.utm.ac.mu` (workspace "Anesu MUPESA's Space") — **sole exception to §0** | — | Notion MCP user/workspace lookup | MCP OAuth | `AUTHORIZED` |
| Zoom (MCP plugin) | Dev-assist only; **not** the product's Zoom API | `sharonremotedeveloper@gmail.com` (+ id: TBD) | — | connector status | MCP auth | `AUTHORIZED` (currently failing auth — needs reconnect by Anesu) |

### 3.3 Platform infrastructure (product runtime)

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Neon Postgres | Staging/prod database; project `sweet-bonus-69458238`; setup in [`NEON_SETUP.md`](./NEON_SETUP.md) | `sharonremotedeveloper@gmail.com` (+ project `sweet-bonus-69458238`) | staging / prod | `neon me` / Neon `list_organizations` | `.env` `DATABASE_URL` | `CONFIRMED` for CLI (2026-10-02; org `org-lucky-pine-32944571`, project `sweet-bonus-69458238`). Neon MCP is **project-level only** (`.mcp.json`, `.codex/config.toml`; Antigravity user-level OAuth entry), OAuth sign-in as Sharon, pinned to the project. Global Neon MCP entries (which pointed at another org) were removed 2026-10-02 — do not re-add them. |
| Upstash Redis | Staging/prod cache, locks, Celery broker | `sharonremotedeveloper@gmail.com` (+ id: TBD) | staging / prod | Upstash console account | `.env` `REDIS_URL` | `AUTHORIZED` |
| Cloudflare (R2 + DNS/CDN) | Asset storage `esl-platform-assets`, `assets.sharonesl.com`; dashboard `https://dash.cloudflare.com/c3f9198712a0df8a75049e7d5374b1dd` | `sharonremotedeveloper@gmail.com` (+ account ID `c3f9198712a0df8a75049e7d5374b1dd`) | staging / prod | Dashboard URL account ID matches; `npx wrangler whoami` shows email + account ID | `.env` `CLOUDFLARE_R2_*` | `AUTHORIZED` |
| Vercel | Frontend hosting | `sharonremotedeveloper@gmail.com` (+ id: TBD) | staging / prod | `vercel whoami` | Vercel env | `AUTHORIZED` |
| Railway | Backend API + Celery worker/beat hosting; project `816aac81-bae6-40c4-b2de-48dc68d55709`; setup in [`RAILWAY_SETUP.md`](./RAILWAY_SETUP.md) | `sharonremotedeveloper@gmail.com` (+ project `816aac81-bae6-40c4-b2de-48dc68d55709`) | staging / prod | `railway whoami` | Railway variables | `AUTHORIZED` — **BLOCKED**: CLI logged in as another account (see §4) |
| Docker (local) | Local multi-container stack | local machine | dev | `docker info` | n/a | `N/A` |

### 3.4 Third-party APIs used by the product

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Zoom Server-to-Server OAuth app | Meeting provisioning + attendance webhooks | `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev / staging / prod | Zoom Marketplace app page | `.env` `ZOOM_*` | `AUTHORIZED` |
| Google Cloud (Calendar API v3) | Teacher 2-way calendar sync | `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev / staging / prod | GCP console project | `.env` / OAuth client | `AUTHORIZED` |
| PayFast | ZAR payments | `sharonremotedeveloper@gmail.com` (+ id: TBD) — **sandbox only** | sandbox | PayFast sandbox dashboard | `.env` `PAYFAST_*` | `AUTHORIZED` |
| PayPal | USD/EUR/JPY payments | `sharonremotedeveloper@gmail.com` (+ id: TBD) — **sandbox only** | sandbox | PayPal developer dashboard | `.env` `PAYPAL_*` | `AUTHORIZED` |
| Resend | Transactional email (.ics) | `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev / staging / prod | Resend dashboard | `.env` `RESEND_API_KEY` | `AUTHORIZED` |
| EskomSePush | Load-shedding schedules | `sharonremotedeveloper@gmail.com` (+ id: TBD) | prod | provider dashboard | `.env` | `AUTHORIZED` |
| Wise | Tutor payouts (future) | `sharonremotedeveloper@gmail.com` (+ id: TBD) | — | — | — | `N/A` |

---

## 4. Confirmation Log (append-only)

One line per confirmation or change. Newest last. Do not delete entries.

| Date | Agent | Tool | Account confirmed | Env | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-10-02 | Claude | (file created) | — | — | Registry initialised; all accounts pending owner input. |
| 2026-10-02 | Claude | ALL | `sharonremotedeveloper@gmail.com` set as the single master identity by Anesu | — | Rows moved to `AUTHORIZED`; live sign-ins not yet verified per tool. |
| 2026-10-02 | Claude | Notion | `anesu.mupesa@umail.utm.ac.mu` | — | Anesu: Notion is the only exception to the master identity. |
| 2026-10-02 | Claude | Neon CLI | **MISMATCH**: `neon me` showed `anesu@intern-mail.metabox.technology` (expected `sharonremotedeveloper@gmail.com`) | — | Stopped. No link/MCP/deploy done. Anesu must re-login. |
| 2026-10-02 | Claude | Railway CLI | **MISMATCH**: `railway whoami` showed `anesu@intern-mail.metabox.technology` (expected `sharonremotedeveloper@gmail.com`) | — | Stopped. No link/deploy/variables touched. Anesu must re-login. |
| 2026-10-02 | Claude | Cloudflare | account ID `c3f9198712a0df8a75049e7d5374b1dd` recorded from dashboard URL supplied by Anesu | — | Identifier only; login/API token still needed and not yet verified. |
| 2026-10-02 | Claude | Cloudflare plugin | installed `cloudflare@cloudflare` (v1.0.1) at **project scope** (`.claude/settings.json`); marketplace `cloudflare` added at user level | — | Brings skills + remote MCP `https://mcp.cloudflare.com/mcp` (OAuth). Not yet signed in/verified: on first use sign in as `sharonremotedeveloper@gmail.com` and confirm account ID `c3f9198712a0df8a75049e7d5374b1dd` before any action. Claude-only; Codex/Antigravity not configured. |
| 2026-10-02 | Claude | Cloudflare MCP (Codex, Antigravity) | added `https://mcp.cloudflare.com/mcp` (OAuth, no key): Codex via project `.codex/config.toml`; Antigravity via user-level `~/.gemini/config/mcp_config.json` (no project-level support) | — | Same rule: first sign-in must be `sharonremotedeveloper@gmail.com`, account ID `c3f9198712a0df8a75049e7d5374b1dd`. Not yet verified. |
| 2026-10-02 | Claude | Cloudflare R2 keys | Anesu states R2 S3 keys are already in `Project-files/.env` | — | `.env` exists; contents deliberately not opened or checked by Claude. |
| 2026-10-02 | Claude | GitHub CLI | `sharonremotedeveloper` (email verified `sharonremotedeveloper@gmail.com`) | — | Anesu completed device login; account now active. `gh` also holds `anesu-metabox` and `Mupesa` — **always check the active account before use**. |
| 2026-10-02 | Claude | Neon CLI | `sharonremotedeveloper@gmail.com` (org `org-lucky-pine-32944571`) | — | `neon me` verified after Anesu's re-login. Project `sweet-bonus-69458238` belongs to this org. |
| 2026-10-02 | Claude | Neon MCP (global) | **MISMATCH**: `list_organizations` returned org `Anesu` (`org-misty-band-32565604`) | — | Static API-key MCP in `~/.claude.json` belongs to another account. Left untouched; not to be used. Project-level OAuth MCP added in `.mcp.json`. |
| 2026-10-02 | Claude | Neon MCP config | removed global Neon entries (`~/.claude.json`, `~/.codex/config.toml`); replaced Antigravity's `~/.gemini/config/mcp_config.json` Neon entry with OAuth + `projectId=sweet-bonus-69458238` | — | Per Anesu: Neon must be local to this project and belong to Sharon. OAuth sign-in on first use must be as `sharonremotedeveloper@gmail.com`; verify via `list_organizations` = `org-lucky-pine-32944571`. |
| 2026-10-02 | Antigravity | Git & GitHub | `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com`) | dev | Configured local git user & author credentials; pushed `develop` and `main` branches to `sharonremotedeveloper/SharonOnline`. |
| 2026-10-02 | Claude | Cloudflare (dashboard via Chrome) | Account ID `c3f9198712a0df8a75049e7d5374b1dd`, titled "Sharonremotedeveloper@gmail.com's Account" | — | Verified. Anesu approved R2 activation and entered billing himself ($0/month, free tier). Created bucket `esl-platform-assets` (Standard, WEUR, public access disabled, no custom domain, public dev URL off). CORS: origin `http://localhost:3000`, methods GET/PUT/HEAD, header Content-Type. Still open: scoped R2 API token (Anesu), custom domain (D-10), prod CORS origin, private-vault separation. |
| 2026-10-02 | Claude | Cloudflare R2 (S3 API, local `.env`) | Bucket `esl-platform-assets`, account `c3f9198712a0df8a75049e7d5374b1dd` | — | Live presigned-upload test passed: wrong size 403, wrong content-type 403, correct PUT 200, read-back 200, test object deleted. Anesu created the scoped token and `.env` himself; values never read by Claude. `.env.apikeys` is 0 bytes (no tokens). |
| 2026-10-02 | Codex | Local Git configuration | `sharonremotedeveloper@gmail.com` | dev | Verified with repository-local `git config --show-origin --get-regexp ^user\.email$` before creating the isolated remediation worktree and branches. No remote Git or external provider action performed. |
| 2026-10-03 | Codex | Batch 2 local implementation | — | dev | Used only the local worktree, existing project virtual environment, and local test/build tools. No external provider, sandbox gateway, remote Git, or cloud database action performed. |
| 2026-10-03 | Codex | Batch 3 local implementation | — | dev | Provider reconciliation was tested only through injected local results. No PayFast, PayPal, cloud PostgreSQL, remote Git, or other external-provider action performed. |
| 2026-10-03 | Codex | Batch 4 local implementation | — | dev | Zoom attendance was verified using local signed webhook fixtures and injected client responses only. No Zoom account, API, sandbox, remote Git, or cloud action performed. |

---

## 5. Editing This File

- Only **Anesu** (or an agent acting on his explicit instruction in chat) may change an `Authorized Account` or set a row to `CONFIRMED`.
- Agents may add new tool rows as `UNCONFIRMED` and append to §4.
- Keep identifiers only — never secrets (§2).
