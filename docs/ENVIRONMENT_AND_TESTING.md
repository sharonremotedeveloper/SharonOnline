# Environment Setup, Testing & Deployment Specification

## 1. Local Development Prerequisites

- **Python**: `3.12.x` (Virtual Environment located at `Project-files/backend/venv`)
- **Node.js**: `v22.x` (npm package manager)
- **Database**: PostgreSQL 16 (Local Docker Postgres or SQLite fallback for lightweight testing)
- **Cache & Broker**: Redis 7 (Local Docker Redis or Upstash Serverless)

---

## 2. Environment Variables Configuration

Copy `.env.example` to `.env` in `Project-files/`:

```bash
# Core Environment
DEBUG=True
DJANGO_SECRET_KEY=django-insecure-prod-key-change-in-production   # the code reads DJANGO_SECRET_KEY (config/settings/base.py), not SECRET_KEY
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database Configuration (Neon Serverless in Staging/Prod)
DATABASE_URL=postgresql://esl_user:password@localhost:5432/esl_db

# Cache & Distributed Locks (Upstash Serverless in Staging/Prod)
REDIS_URL=redis://localhost:6379/0

# Zoom Server-to-Server OAuth API
ZOOM_ACCOUNT_ID=your_zoom_account_id
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_WEBHOOK_SECRET_TOKEN=your_zoom_webhook_secret

# Payments API Credentials
PAYFAST_MERCHANT_ID=10000100
PAYFAST_MERCHANT_KEY=46f0cd694581a
PAYFAST_PASSPHRASE=your_payfast_passphrase
PAYFAST_SANDBOX=True

PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_MODE=sandbox

# Cloudflare R2 Media Bucket
CLOUDFLARE_R2_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_R2_ACCESS_KEY_ID=your_r2_access_key
CLOUDFLARE_R2_SECRET_ACCESS_KEY=your_r2_secret_key
CLOUDFLARE_R2_BUCKET_NAME=esl-platform-assets

# Transactional Email (Resend API)
RESEND_API_KEY=re_123456789
DEFAULT_FROM_EMAIL=Sharon's ESL Platform <noreply@sharon-esl.com>
```

---

## 3. Automated Verification & Testing Commands

### 3.1 Backend Django Verification
Run inside `Project-files/backend/`:
```bash
# Activate virtual environment
source venv/Scripts/activate

# Check Django health and settings configuration
python manage.py check

# Run database migrations check
python manage.py makemigrations --check

# Execute Pytest test suite
pytest
```

### 3.2 Frontend Next.js Verification
Run inside `Project-files/frontend/`:
```bash
# Run ESLint linter
npm run lint

# Execute production build compilation test (12/12 static & dynamic routes)
npm run build
```

---

## 4. Production Deployment Topology Specs

- **Frontend Hosting**: Vercel Pro (Next.js 14 App Router, Edge Caching in Tokyo & Johannesburg).
- **Backend API Container**: Railway / Render (`Dockerfile` execution for Django API + Gunicorn).
- **Celery Async Worker**: Railway Background Worker service (`celery -A config worker -l info -c 2`).
- **Database**: Neon PostgreSQL 16 (`eu-central-1` Frankfurt).
- **Cache**: Upstash Serverless Redis (`eu-central-1` Frankfurt).
- **Storage**: Cloudflare R2 (PDFs & Curriculum worksheets - \$0 egress fees).
