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
| Cloudflare (R2 + DNS/CDN) | Asset storage `esl-platform-assets`, private vetting storage `esl-platform-private-vetting`, intended CDN `assets.sharonesl.com`; dashboard `https://dash.cloudflare.com/c3f9198712a0df8a75049e7d5374b1dd` | `sharonremotedeveloper@gmail.com` (+ account ID `c3f9198712a0df8a75049e7d5374b1dd`) | staging / prod | Dashboard URL account ID matches; `npx wrangler whoami` shows email + account ID | `.env` `CLOUDFLARE_R2_*` | `CONFIRMED` (R2 buckets and `topteacheracademy.com` zone observed 2026-10-12; Vercel apex CNAME saved DNS-only; no secrets recorded) |
| Vercel | Frontend hosting; team scope `sharon-team1` / project `sharon-online` | `sharonremotedeveloper@gmail.com` (+ username `sharonremotedeveloper`) | staging / prod | `vercel whoami` or account check | Vercel env | `CONFIRMED` (account identity 2026-10-14; project-scope API inspection returned 403, no settings or deployment change) |
| Railway | Backend API + Celery worker/beat hosting; canonical production project `sharon-online-prod` (`e2b11747-5519-4139-bd34-a658affea42a`); setup in [`RAILWAY_SETUP.md`](./RAILWAY_SETUP.md) | `sharonremotedeveloper@gmail.com` (+ production project `e2b11747-5519-4139-bd34-a658affea42a`) | staging / prod | `railway whoami` or Railway MCP identity check | Railway variables | `CONFIRMED` (2026-10-14 read-only identity/project/environment/service check; no variable values read) |
| Docker (local) | Local multi-container stack | local machine | dev | `docker info` | n/a | `N/A` |

### 3.4 Third-party APIs used by the product

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Zoom Server-to-Server OAuth app | Meeting provisioning + attendance webhooks | `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev / staging / prod | Zoom Marketplace app page | `.env` `ZOOM_*` | `SUPERSEDED` (by D-14 Daily.co) |
| Zoom Video SDK app (Platform Studio) | In-browser classroom: session JWTs (`ZOOM_VIDEO_SDK_*`) + attendance webhooks (V4) | `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev | Zoom Platform Studio app page | `.env` `ZOOM_VIDEO_SDK_*` | `SUPERSEDED` (by D-14 Daily.co) |
| Daily.co | In-browser 1-on-1 WebRTC classroom + attendance webhooks (Decision D-14) | `sharonremotedeveloper@gmail.com` | dev / staging / prod | Daily.co developer dashboard | `.env` `DAILY_*` | `AUTHORIZED` (Decision D-14; API key & domain pending live setup) |
| Google Cloud (Calendar API v3) | Teacher 2-way calendar sync | `sharonremotedeveloper@gmail.com` (+ project `Sharon Online Calendar`, ID `crafty-elf-510716-b6`) | dev / staging / prod | GCP console project; Calendar API enabled; Google Auth Platform client list | `.env` / OAuth client | `CONFIRMED` (2026-10-05; external test OAuth web client created with localhost callback; client secret not recorded here) |
| PayFast | ZAR payments | `sharonremotedeveloper@gmail.com` (+ id: TBD) — **sandbox only** | sandbox | PayFast sandbox dashboard | `.env` `PAYFAST_*` | `AUTHORIZED` |
| PayPal | USD/EUR/JPY payments | `sharonremotedeveloper@gmail.com` (+ id: TBD) — **sandbox only** | sandbox | PayPal developer dashboard | `.env` `PAYPAL_*` | `AUTHORIZED` |
| Resend | Transactional email (.ics) | `sharonremotedeveloper@gmail.com` (+ workspace `sharonremotedeveloper`) | dev / staging / prod | Resend dashboard | `.env` `RESEND_API_KEY` | `CONFIRMED` (2026-10-14; `topteacheracademy.com` sending domain verified; canonical production sender configured; owner-received student confirmation mail provider-reported Delivered; dashboard unverified banner disappeared after link use; recovery-mail UAT pending) |
| EskomSePush | Load-shedding schedules | `sharonremotedeveloper@gmail.com` (+ id: TBD) | prod | provider dashboard | `.env` | `AUTHORIZED` |
| Wise | Tutor payouts (future) | `sharonremotedeveloper@gmail.com` (+ id: TBD) | — | — | — | `N/A` |

### 3.5 Security, SAST & DAST tooling

| Tool | Purpose | Authorized Account | Env | How to verify (read-only) | Secrets live in | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| OWASP ZAP (Zed Attack Proxy) | Dynamic Application Security Testing (DAST) vulnerability scan against running web application (OWASP Top 10, headers, injection, auth) | `sharonremotedeveloper@gmail.com` | staging / dev | `zap.sh -version` / ZAP desktop/CLI banner / container log | n/a | `AUTHORIZED` |
| GitHub CodeQL | Static Application Security Testing (SAST) semantic code analysis for Python and JavaScript/TypeScript vulnerabilities in CI & local analysis | `sharonremotedeveloper@gmail.com` (GitHub repository `sharonremotedeveloper/SharonOnline`) | CI / dev | `codeql version` / GitHub Actions CodeQL workflow status / `gh api repos/sharonremotedeveloper/SharonOnline/code-scanning/alerts` | n/a (GitHub native) | `AUTHORIZED` |

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
| 2026-10-03 | Codex | Batch 5 local implementation | — | dev | Profile, support-notification, OpenAPI, and timezone behavior was verified locally; Resend was injected in tests. No email provider, remote Git, or cloud action performed. |
| 2026-10-03 | Codex | Batch 6 local implementation | — | dev | Tutor wallet, encrypted payout settings, key rotation, masking, and reauthentication were verified locally. No banking rail, provider API, remote Git, cloud database, or payout action performed. Payout execution remains disabled. |
| 2026-10-03 | Codex | Batch 7 local implementation | — | dev | EskomSePush behavior, cached/stale status, notification delivery, backup flags, and outage corroboration were verified only with injected local clients. No EskomSePush or Resend API, remote Git, cloud database, or other external action performed. |
| 2026-10-03 | Codex | Batch 8 local stabilization | — | dev | Added and locally validated CI/lint configuration; all available local gates passed. No remote Git/CI run, provider sandbox, deploy, cloud database, or infrastructure action performed. PostgreSQL/Redis service evidence awaits the first authorized remote CI run. |
| 2026-10-03 | Claude | GitHub CLI (push of Task 10.1 to `develop`) | `sharonremotedeveloper` (`gh auth status` active; `gh api user/emails` primary `sharonremotedeveloper@gmail.com`) | - | Matches registry; remote `sharonremotedeveloper/SharonOnline`. No account switch. |
| 2026-10-04 | Claude | GitHub CLI (push of Task 10.2 to `develop`) | `sharonremotedeveloper` (`gh auth status` active; `gh api user/emails` primary `sharonremotedeveloper@gmail.com`) | - | Matches registry; remote `sharonremotedeveloper/SharonOnline`. No account switch. PayPal sandbox NOT used (no credentials yet; all PayPal code verified against mocked HTTP only). |
| 2026-10-04 | Claude | GitHub CLI (push of Task 10.7 to `develop`) | `sharonremotedeveloper` (`gh auth status` active; `gh api user/emails` primary `sharonremotedeveloper@gmail.com`) | - | Matches registry; remote `sharonremotedeveloper/SharonOnline`. No account switch. PayPal/PayFast sandboxes NOT used (no credentials yet; refund code verified against mocked HTTP only). |
| 2026-10-04 | Claude | Slice N1c (unified `send_email`) local implementation | - | dev | Resend NOT called: every test replaces `requests.post` in `apps/integrations/services/email.py`, the test fixture pins `EMAIL_BACKEND_MODE=console`. No account used, no key read or written, no push. 409 / 24 h idempotency semantics taken from Resend docs, unverified live. |
| 2026-10-05 | Claude | GitHub CLI (push of Phase 11/12 layer 0 to `develop`) | `sharonremotedeveloper` (`gh auth status` active account) | - | Matches registry; remote `sharonremotedeveloper/SharonOnline`. No account switch. Zoom, Resend, Google not called (all mocked in tests). |
| 2026-10-05 | Claude | GitHub CLI (planned push of Phase 11/12 layer 1 to `develop`) | **MISMATCH**: `gh auth status` active account = `anesu-metabox` (expected `sharonremotedeveloper`; the layer-0 push this morning used `sharonremotedeveloper`) | - | Stopped before any push. No `gh auth switch`, no login, no credential change by Claude. Anesu must make `sharonremotedeveloper` the active `gh` account (or explicitly authorise a different one) before layer 1 is pushed. |
| 2026-10-05 | Claude | GitHub CLI (push of Phase 11/12 layer 1 to `develop`, CI run) | `sharonremotedeveloper` (`gh auth status` active; `gh api user` login `sharonremotedeveloper`) | - | Matches registry after Anesu re-activated the account; remote `sharonremotedeveloper/SharonOnline`. Anesu instructed (2026-10-05) to commit all files incl. the Zoom Video SDK docs, push to `develop`, clean branches and run CI. No account switch by Claude. |
| 2026-10-05 | Claude | Zoom S2S OAuth app (slice Z1, client hardening) | registry row `sharonremotedeveloper@gmail.com` (+ id: TBD) | dev | **No real Zoom call made**: the client was exercised only against `tests/fakes.py::FakeZoom` (no network, no credentials used). Real-account verification (C2/C4 sandbox checks, host-link ZAK lifetime) is still to do by Anesu's go. |
| 2026-10-05 | Codex | Cloudflare R2 (dashboard via Chrome) | `sharonremotedeveloper@gmail.com`, account `c3f9198712a0df8a75049e7d5374b1dd` | staging / prod | Created private bucket `esl-platform-private-vetting` with default private access; existing assets bucket remains `esl-platform-assets`. No domain or public access was added. |
| 2026-10-05 | Codex | Google Cloud / Calendar API (dashboard via Chrome) | `sharonremotedeveloper@gmail.com`, project `Sharon Online Calendar` (`crafty-elf-510716-b6`) | dev / staging | Enabled Calendar API, configured external OAuth branding, and created the web OAuth client with redirect `http://localhost:8000/api/v1/integrations/google-calendar/callback/`. Client secret intentionally not recorded in this file. |
| 2026-10-05 | Codex | Resend (dashboard via Chrome) | `sharonremotedeveloper@gmail.com`, workspace `sharonremotedeveloper` | dev / staging / prod | Dashboard identity verified. No domain is configured; SPF/DKIM cannot be generated or applied until a domain is chosen and its DNS provider is available. |
| 2026-10-05 | Claude | GitHub (`gh auth status`, read-only) | `sharonremotedeveloper` active | develop | Active account matches the registry before pushing the layer-1b integration to `origin/develop`. |
| 2026-10-08 | Claude | Vercel (read-only dashboard check in Anesu's logged-in Chrome, project `sharon-team1/sharon-online`) | Dashboard user shown as `sharonremotedeveloper` (team SharonTeam, Hobby) | prod/preview | Matches registry. Git repo `sharonremotedeveloper/SharonOnline` connected, Root Directory `frontend`, Production branch `main`, Preview = all other branches. No settings changed by Claude; no login, no deploy, Railway untouched. |
| 2026-10-08 | Claude | GitHub CLI (account switch + push of docs to `develop`) | `gh auth status` was `anesu-metabox` (mismatch); on Anesu's explicit chat instruction ("change to sharonremotedeveloper@gmail.com") Claude ran `gh auth switch -u sharonremotedeveloper`; `gh api user` login = `sharonremotedeveloper` | develop | Matches registry after the switch. Switch only between already-logged-in accounts; no login or credential change. |
| 2026-10-09 | Antigravity | GitHub / Daily.co Migration (Decision D-14) | `sharonremotedeveloper` active | develop | Migrated video conferencing to Daily.co embedded WebRTC, added DailyClient, webhook receiver, attendance auditor, frontend DailyClassroom component, unit & E2E tests, updated docs. |
| 2026-10-07 | Antigravity | OWASP ZAP | `sharonremotedeveloper@gmail.com` | staging / dev | Registered in §3.5 per Anesu instruction. Scheduled as pre-production DAST security assessment tool against staging endpoints prior to production launch. |
| 2026-10-07 | Antigravity | GitHub CodeQL | `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com`) | CI / dev | Registered in §3.5 per Anesu instruction. Scheduled as automated SAST code scanner for Python and JavaScript/TypeScript in CI and pre-production security review. |
| 2026-10-14 | Codex | Railway MCP (read-only identity/capacity preflight) | `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com`), user ID `40c37413-444b-4e1b-82f7-435b9e68c3e4` | prod | Active identity matches the master account; workspace `sharonremotedeveloper's Projects` (`df8b4d19-e16a-436e-a2f1-cba37f993291`) verified before production inspection. No secrets read or recorded. |
| 2026-10-14 | Codex | Vercel account check (read-only) | `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com`), user ID `zjiab99hznsgaikcN2Y8mfP2` | staging / prod | Active identity matches the master account. Project enumeration for `sharon-team1` / `sharon-online` returned 403, so no project settings, deployment, or environment values were inspected or changed. |
| 2026-10-14 | Codex | Railway MCP (read-only project/environment/service/deployment check) | `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com`), user ID `40c37413-444b-4e1b-82f7-435b9e68c3e4` | staging / prod | SharonRailway development services `backend-api-development`, `celery-worker-development`, and `celery-beat-development` were SUCCESS on `dcaa9c7`; production `backend-api-production` was FAILED at `/api/health/` on `dcaa9c7`; staged patches were observed but not applied. No variable values, secrets, or infrastructure settings were read or changed. |
| 2026-10-14 | Codex | Vercel / Neon / Cloudflare / Upstash provider recheck | Vercel matched `sharonremotedeveloper@gmail.com`; Neon MCP returned `MetaBox` / `org-ancient-dew-43434004` instead of the registered Sharon organization; Cloudflare browser tab showed `Teachersharone Gmail's Account` / `30971c1f8b0cb0fae652fed13a4288c9`; Upstash identity was not verifiable through the available browser binding | staging / prod | Vercel project reads for `sharon-team1/sharon-online` returned 403 and no settings were changed. Neon work stopped at the account gate. Cloudflare DNS and Upstash billing/database actions were not attempted. |
| 2026-10-14 | Codex | Authorized hosted execution update | Railway `sharonremotedeveloper@gmail.com`; Vercel and Cloudflare browser sessions active; Upstash production billing session active | prod | Canonical Railway project `sharon-online-prod` created with API/worker/one Beat on `develop`; production Upstash Redis created separately and wired through encrypted Railway variables; Vercel Production `INTERNAL_API_URL` and Cloudflare `www`/`api` records configured. Neon provider credentials and remaining guarded secrets are still pending; no secret values recorded. |
| 2026-10-15 | Codex | GitHub CLI | Active `sharonremotedeveloper` (`sharonremotedeveloper@gmail.com` is the registered account) | dev / prod monitoring design | `gh auth status` and `gh api user` matched registry; repository `sharonremotedeveloper/SharonOnline` is public with default branch `develop`. Other stored GitHub accounts were inactive. No token values were read. |
| 2026-10-15 | Codex | GitHub CLI, Railway MCP, Vercel connector | `sharonremotedeveloper@gmail.com` / GitHub `sharonremotedeveloper` | dev / approved production release | Read-only GitHub active-account, Railway `whoami`, and Vercel authenticated-user checks matched the master account before the approved tutor-directory promotion. Canonical Railway production project and Vercel project were identified separately; no credential values were recorded. |
| 2026-10-19 | Claude | Railway API | `sharonremotedeveloper@gmail.com` | prod | On Anesu's go-ahead (Wave 2 step 4) deployed API, worker and Beat at `59e3e52` (deployments `6bbbc371-...`, `82f5b044-...`, `ca8cc6f4-...`), all SUCCESS; public health, ready and scheduler-ready 200. No variable changed. |
| 2026-10-19 | Claude | Railway API | `sharonremotedeveloper@gmail.com` | prod | On Anesu's go-ahead (Wave 2 step 3) applied materials.0003 + teachers.0015 through the one-shot migration service at `59e3e52` (deployments `8a7074a5-...` apply, `a2c2152e-...` "No migrations to apply"), then reset it to `--plan` and cleared `PRODUCTION_MIGRATION_APPROVED`. API/worker/Beat not deployed. |
| 2026-10-19 | Claude | Railway API | `sharonremotedeveloper@gmail.com` | prod | On Anesu's go-ahead copied `CLOUDFLARE_R2_ACCOUNT_ID` and `CLOUDFLARE_R2_PUBLIC_DOMAIN` from `backend-api-production` to `production-migrations-b33743a` (values held in memory only, equality re-checked, `skipDeploys: true`), then re-ran the plan-only job at `59e3e52` (deployment `4ba359ac-...`): plan = materials.0003 + teachers.0015. Nothing applied; approval flag empty. |
| 2026-10-19 | Claude | Neon CLI, Railway API | `neon me` = `sharonremotedeveloper` / `sharonremotedeveloper@gmail.com`, project `sweet-bonus-69458238`; `railway whoami` = `sharonremotedeveloper@gmail.com` | prod | On Anesu's go-ahead (Wave 2 release steps 1-2): created Neon branch `pre-wave2-migrations-59e3e52` (`br-noisy-fog-b47ocuxw`, parent `production`, no compute, expires 2026-10-26); deployed the plan-only migration service `cdc25acb-...` at `59e3e52` (deployment `e5d812f9-...`), which stopped at settings load (ERR-555). No migration applied, no variable changed. |
| 2026-10-19 | Claude | Cloudflare R2 (local backend `.env`), Railway CLI | R2 account ID from settings equals `c3f9198712a0df8a75049e7d5374b1dd`, bucket `esl-platform-assets`; `railway whoami` = `sharonremotedeveloper@gmail.com` | prod bucket / prod Railway read-only | On Anesu's go-ahead deleted the one 13-byte test PDF `materials/9e941091-a3c0-4110-8144-f66c4c1ccdc5/pdf-cc91e85be57d4d91ac3cfecec5b1b5e0.pdf` (head before: 13 bytes application/pdf; after: 404; quarantine prefix empty). Railway: read-only GraphQL queries of project `e2b11747-...` services, deployments and two non-secret flags (`PRODUCTION_MIGRATION_APPROVED` empty, `TUTOR_TRAINING_GATE_ENABLED=1`); a variables query returned values in memory, only names and those two flags were printed. Local CLI stays linked to `SharonRailway` (not relinked). No deploy, variable change or migration. |
| 2026-10-19 | Claude | Cloudflare R2 via the local backend's `.env` (Wave 2 upload check) | bucket `esl-platform-assets` (registry row: account `c3f9198712a0df8a75049e7d5374b1dd`) | dev against the shared staging/prod bucket | Not a planned tool use: verifying the new `/admin/materials` upload on localhost went through the local backend, whose `.env` holds the R2 keys, so one 13-byte test PDF was committed to `materials/9e941091-a3c0-4110-8144-f66c4c1ccdc5/pdf-cc91e85be57d4d91ac3cfecec5b1b5e0.pdf` (quarantine copy removed by the commit). Detached from the local test material; object left in place pending Anesu's OK to delete it. No keys read; no further uploads. |
| 2026-10-19 | Claude | GitHub (git push) | `gh api user` = `sharonremotedeveloper` (token passed for this one command; the active `gh` account stayed `Mupesa`, not switched) | develop | Anesu asked to push as sharonremotedeveloper after two 403s as Mupesa. Pushed develop `73a2e6c..241a377` (tutor speed-test minimum upload 2 Mbps). Not promoted to main; no Railway change. |
| 2026-10-19 | Claude | GitHub (git push), Railway API | `gh api user` = `sharonremotedeveloper` (per-command token); `railway whoami` = `sharonremotedeveloper@gmail.com` | prod | On Anesu's go-ahead after green CI on develop `f4c9719`: cherry-picked the 2 Mbps change to main as `a4523f0` (Vercel success) and deployed only `backend-api-production` at `a4523f0` (deployment `5cb7fde4-...`, SUCCESS; health/ready 200) instead of develop `241a377`, which carries unreleased backend work. Read-only check: API variables have no `APPLICATION_MIN_UPLOAD_MBPS` override. Worker/Beat unchanged on `59e3e52`. `railway ssh` refused (no SSH key; none created). |
| 2026-10-19 | Claude | Neon CLI + psycopg2 (read-only session), public API | `neon me` = `sharonremotedeveloper` / `sharonremotedeveloper@gmail.com`, project `sweet-bonus-69458238`, branch `production` | prod (read-only) | Why tutor Sharon (`dceb645a-...`) shows no slots: she is approved and listed, but has 0 weekly availability, 0 date overrides, 0 time-off rows (Anesu has 17 weekly rows). Connection string piped in memory, never printed. Nothing written. |
| 2026-10-20 | Claude | Neon CLI + psycopg2 (read-only), Railway API | `neon me` = `sharonremotedeveloper`; `railway whoami` = `sharonremotedeveloper@gmail.com` | prod | ERR-557. Read-only: Sharon's holds `0d676912-...`, `6436cad7-...` stuck `pending_payment`; allowlist compared in memory (Sharon not listed). On Anesu's go-ahead appended Sharon's tutor e-mail to `TEST_BOOKING_ALLOWED_EMAILS` on `backend-api-production` (2 -> 3 entries, existing kept, no address printed), redeploy `372658f4-...` at `a4523f0` SUCCESS, health/ready 200, re-check: Sharon listed. |
| 2026-10-18 | Claude | GitHub CLI (push of chat design docs to `develop`) | `sharonremotedeveloper` (`gh auth status` active; `gh api user` login `sharonremotedeveloper`) | develop | Matches registry; remote `sharonremotedeveloper/SharonOnline`. Docs-only commit on Anesu's chat instruction. No account switch. Chat research used public web pages only; no vendor (Ably, Stream, TalkJS, etc.) account or API used. |

---

## 5. Editing This File

- Only **Anesu** (or an agent acting on his explicit instruction in chat) may change an `Authorized Account` or set a row to `CONFIRMED`.
- Agents may add new tool rows as `UNCONFIRMED` and append to §4.
- Keep identifiers only — never secrets (§2).
