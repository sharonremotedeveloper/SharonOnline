# Sharon's ESL Marketplace Platform

A high-reliability, mobile-first synchronous English tutoring marketplace platform connecting international students across East Asia (Japan, South Korea) and Europe with vetted native and South African tutors.

---

## 📚 Master Documentation Hub & AI Collaboration Suite

Comprehensive documentation for developers (**Anesu MUPESA**) and collaborating AI agents (**Antigravity**, **Claude**, **Codex**) is maintained in the [`docs/`](./docs/) directory:

- 📖 [**`docs/README.md`**](./docs/README.md) — Master Documentation Index & Sitemap
- 📖 [**`docs/PROJECT_CONTEXT.md`**](./docs/PROJECT_CONTEXT.md) — Business Model, Target Segments & Domain Specs
- 📐 [**`docs/ARCHITECTURE_AND_SCHEMA.md`**](./docs/ARCHITECTURE_AND_SCHEMA.md) — Database Models, Redis Lock & System Architecture
- 🚀 [**`docs/PROGRESS_AND_ROADMAP.md`**](./docs/PROGRESS_AND_ROADMAP.md) — 6-Phase Delivery Roadmap & Master 46-View Inventory
- ⚡ [**`docs/ERROR_LOGS_AND_RESOLUTIONS.md`**](./docs/ERROR_LOGS_AND_RESOLUTIONS.md) — Error Resolution Ledger (`ERR-xxx`)
- 🤖 [**`docs/AI_AGENT_COLLABORATION_RULES.md`**](./docs/AI_AGENT_COLLABORATION_RULES.md) — Rules of Engagement for AI Agents & Developers
- ⚙️ [**`docs/ENVIRONMENT_AND_TESTING.md`**](./docs/ENVIRONMENT_AND_TESTING.md) — Local Setup, Pytest & Build Verification

---

## 🛠️ Architecture Stack
* **Frontend:** Next.js 14+ (App Router, TypeScript, Tailwind CSS)
* **Backend:** Django 5.x / Django REST Framework (Python 3.12, Celery, Redis)
* **Database:** PostgreSQL 16 (Neon Serverless for Staging/Prod; Docker Postgres / SQLite for dev)
* **Cache & Distributed Locks:** Redis 7 (Upstash Serverless in Prod; LocMem / Docker Redis in Dev)
* **Video & Calendar:** Zoom Server-to-Server OAuth 2.0 & Google Calendar API (v3)
* **Payments:** PayFast (ZAR) & PayPal v2 Orders (USD/EUR/JPY)

---

## 🚀 Quickstart (Local Development)

### 1. Backend Verification & Tests:
```bash
cd backend
source venv/Scripts/activate
python manage.py check
pytest
```

### 2. Frontend Verification & Build:
```bash
cd frontend
npm run build
```

### 3. Docker Access Points:
* Frontend: [http://localhost:3000](http://localhost:3000)
* Backend REST API: [http://localhost:8000/api/v1](http://localhost:8000/api/v1)
* Django Admin Console: [http://localhost:8000/admin](http://localhost:8000/admin)
* Health Check: [http://localhost:8000/api/health/](http://localhost:8000/api/health/)
