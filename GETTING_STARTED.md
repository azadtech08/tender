# Getting Started — GeM Tender SaaS

This guide walks you from a fresh clone to a fully running local development environment, then explains how to deploy to production.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone & Folder Structure](#2-clone--folder-structure)
3. [Environment Variables](#3-environment-variables)
4. [Option A — Docker (Recommended)](#4-option-a--docker-recommended)
5. [Option B — Manual (Without Docker)](#5-option-b--manual-without-docker)
6. [Database Migrations](#6-database-migrations)
7. [Run the Frontend (Next.js)](#7-run-the-frontend-nextjs)
8. [Verify Everything Works](#8-verify-everything-works)
9. [External Services Setup](#9-external-services-setup)
10. [Running Tests](#10-running-tests)
11. [Production Deployment](#11-production-deployment)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

Install the following tools before you begin.

| Tool | Minimum Version | Notes |
|---|---|---|
| **Docker Desktop** | 24+ | Includes Docker Compose v2 |
| **Python** | 3.12+ | Only needed for Option B (manual) |
| **Node.js** | 20 LTS | Only needed for Option B (manual) |
| **Git** | Any | For cloning the repo |

> **Windows users:** Use Git Bash or WSL2 for all shell commands below. PowerShell will not work with some commands.

---

## 2. Clone & Folder Structure

```bash
git clone <your-repo-url> gem-tender-saas
cd gem-tender-saas
```

```
gem-tender-saas/
├── apps/
│   ├── api/          ← FastAPI backend (Python 3.12)
│   ├── web/          ← Next.js 14 frontend (TypeScript)
│   └── worker/       ← Celery scraper worker (Playwright)
├── packages/
│   └── db-models/    ← Shared SQLAlchemy models
├── docker-compose.yml
└── .env.example      ← Copy this to .env
```

---

## 3. Environment Variables

Copy the template and fill in the required values:

```bash
cp .env.example .env
```

Then open `.env` and set the following:

### Required for local dev (must change)

```env
# Postgres — keep defaults for Docker, change for cloud DB
POSTGRES_PASSWORD=devpass

# Redis
REDIS_URL=redis://localhost:6379

# JWT secret — generate a strong random string for anything non-throwaway
JWT_SECRET=your-secret-key-here
```

### Optional (leave blank to disable features in dev)

```env
# Clerk — leave blank to use local JWT auth (no sign-in page, use POST /auth/login)
CLERK_JWKS_URL=
CLERK_ISSUER=

# Stripe — leave blank to disable billing
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Cloudflare R2 / S3 — leave blank; PDFs saved locally to /tmp/gem_pdfs
S3_ENDPOINT=
S3_BUCKET=gem-tender-dev
S3_ACCESS_KEY=
S3_SECRET_KEY=

# Email (Resend) — leave blank to skip sending alert digest emails
RESEND_API_KEY=
EMAIL_FROM=GeM Tender <noreply@gemtender.com>

# App base URL used in email digest links
APP_BASE_URL=http://localhost:3000

# Scraper proxies — leave blank for direct connections in dev
PROXY_URLS=
```

### Frontend env file

Create a separate env file for Next.js:

```bash
cp apps/web/.env.local.example apps/web/.env.local   # if file exists
# OR create manually:
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > apps/web/.env.local
```

If you are using Clerk for auth, also add:

```env
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
```

---

## 4. Option A — Docker (Recommended)

This starts Postgres, Redis, the API, the Celery worker, Celery Beat, and the Next.js frontend — all in one command.

### Step 1 — Build and start all services

```bash
docker compose up --build
```

First run takes 3–5 minutes to build images. Subsequent starts are instant.

### Step 2 — Run database migrations (first time only)

Open a second terminal and run:

```bash
docker compose exec api alembic -c alembic.ini upgrade head
```

This applies all 5 migrations (schema, tenant IDs, RLS, billing tables, FTS + alerts/api-keys/webhooks).

### Step 3 — Access the services

| Service | URL |
|---|---|
| **Frontend (Next.js)** | http://localhost:3000 |
| **API (FastAPI)** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API Health** | http://localhost:8000/health |

### Stopping everything

```bash
docker compose down          # stop containers, keep DB data
docker compose down -v       # stop containers AND delete DB data (fresh start)
```

---

## 5. Option B — Manual (Without Docker)

Use this if you prefer to run services directly on your machine.

### Step 1 — Start Postgres and Redis

Install and start them locally, then verify:

```bash
# Postgres must have a database named gem_tender
psql -U postgres -c "CREATE USER gem WITH PASSWORD 'devpass';"
psql -U postgres -c "CREATE DATABASE gem_tender OWNER gem;"

# Redis
redis-cli ping   # should return PONG
```

### Step 2 — Install Python dependencies (API)

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ../../packages/db-models
pip install -e .
```

### Step 3 — Run database migrations

```bash
# Still inside apps/api with .venv active
PYTHONPATH=src alembic upgrade head
```

### Step 4 — Start the API server

```bash
# Still inside apps/api
PYTHONPATH=src uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir src
```

### Step 5 — Install Python dependencies (Worker)

Open a new terminal:

```bash
cd apps/worker
python3.12 -m venv .venv
source .venv/bin/activate

pip install -e ../../packages/db-models
pip install -e .
playwright install chromium   # downloads Chromium for scraping
```

### Step 6 — Start the Celery worker

```bash
# Inside apps/worker with .venv active
PYTHONPATH=src celery -A celery_app worker --loglevel=info
```

### Step 7 — Start Celery Beat (scheduler)

Open a new terminal:

```bash
cd apps/worker
source .venv/bin/activate
PYTHONPATH=src celery -A celery_app beat --loglevel=info
```

### Step 8 — Start the frontend

Open a new terminal:

```bash
cd apps/web
npm install
npm run dev
```

---

## 6. Database Migrations

Migrations live in `apps/api/alembic/versions/`. They are cumulative and must be run in order.

| Migration | What it creates |
|---|---|
| `001_initial_schema` | Core tables: users, jobs, job_events, tenders, schedules |
| `002_add_tenant_id` | Adds `tenant_id` column to jobs and tenders |
| `003_enable_rls` | Postgres Row-Level Security policies per tenant |
| `004_billing_tables` | Stripe subscriptions, usage events, api_keys |
| `005_phase3_fts_alerts_apikeys_webhooks` | `search_vector` tsvector + GIN index, alerts, alert_deliveries, api_keys, outbound_webhooks, webhook_deliveries |

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# Roll back one step
alembic downgrade -1

# Roll back everything
alembic downgrade base
```

---

## 7. Run the Frontend (Next.js)

```bash
cd apps/web
npm install
npm run dev        # starts on http://localhost:3000
```

**Dashboard pages:**

| Page | URL |
|---|---|
| Jobs (create + monitor) | http://localhost:3000/dashboard |
| Tenders grid (23-col, FTS search) | http://localhost:3000/dashboard/tenders |
| Alerts (email/Slack digests) | http://localhost:3000/dashboard/alerts |
| Billing | http://localhost:3000/dashboard/billing |
| Job detail (live SSE log + progress ring) | http://localhost:3000/dashboard/jobs/\<id\> |

---

## 8. Verify Everything Works

### API health

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

### Register a test user (local auth, no Clerk)

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!"}'
```

### Log in and get a token

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!"}'
# Returns: {"access_token":"eyJ...","token_type":"bearer"}
```

### Create a scrape job

```bash
TOKEN="eyJ..."   # paste token from above

curl -X POST http://localhost:8000/api/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"keywords":["laptop","server"],"cards_per_kw":3}'
```

### Open Swagger UI

Visit http://localhost:8000/docs to explore all 35+ endpoints interactively.

---

## 9. External Services Setup

### Clerk (Authentication)

1. Create a free account at https://clerk.com
2. Create an application → copy keys to `apps/web/.env.local`
3. In Clerk dashboard → API Keys → copy **JWKS URL** and **Issuer**
4. Add to `.env`:
   ```env
   CLERK_JWKS_URL=https://<your-clerk-frontend-api>/.well-known/jwks.json
   CLERK_ISSUER=https://clerk.<your-domain>.com
   ```

### Stripe (Billing)

1. Create an account at https://stripe.com
2. Go to Developers → API Keys → copy Secret Key
3. Create products for Starter / Pro / Business plans → copy Price IDs
4. Set up a webhook endpoint pointing to `https://your-api.com/webhooks/stripe`
5. Add to `.env`:
   ```env
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_STARTER=price_...
   STRIPE_PRICE_PRO=price_...
   STRIPE_PRICE_BUSINESS=price_...
   ```

### Cloudflare R2 (Object Storage for PDFs/exports)

1. Log in to Cloudflare → R2 → Create bucket named `gem-tender-dev`
2. Create API token with R2 read/write permissions
3. Add to `.env`:
   ```env
   S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
   S3_BUCKET=gem-tender-dev
   S3_ACCESS_KEY=<access-key-id>
   S3_SECRET_KEY=<secret-access-key>
   ```

### Resend (Email for alert digests)

1. Create a free account at https://resend.com
2. Verify your sending domain
3. Create an API key
4. Add to `.env`:
   ```env
   RESEND_API_KEY=re_...
   EMAIL_FROM=GeM Tender <noreply@yourdomain.com>
   ```

---

## 10. Running Tests

### API tests

```bash
cd apps/api
source .venv/bin/activate
pytest tests/ -v
```

Key test files:

| File | What it tests |
|---|---|
| `tests/test_auth.py` | Register, login, JWT verification |
| `tests/test_jobs.py` | Job CRUD, scheduling, cross-tenant isolation |
| `tests/test_tenders.py` | Tender list, search, pagination |
| `tests/test_exports.py` | 23-column XLSX contract |

### Worker / PDF regression tests

```bash
cd apps/worker
source .venv/bin/activate
pytest tests/ -v
# Requires 30 PDFs in downloads/ directory
```

---

## 11. Production Deployment

### Infrastructure overview

```
Vercel (Next.js frontend)
    ↕  HTTPS
AWS ECS ap-south-1 (FastAPI API container)
    ↕
AWS ECS ap-south-1 (Celery worker + beat containers)
    ↕
AWS RDS Postgres 16 (ap-south-1)
AWS ElastiCache Redis 7 (ap-south-1)
Cloudflare R2 (PDF + XLSX storage)
```

### Step 1 — Deploy the API

```bash
# Build and push Docker image
docker build -f apps/api/Dockerfile -t gem-api:latest .
docker tag gem-api:latest <ecr-url>/gem-api:latest
docker push <ecr-url>/gem-api:latest
```

Set these environment variables in ECS task definition (use AWS Secrets Manager):

```
DATABASE_URL          → postgresql+asyncpg://...
REDIS_URL             → redis://...
JWT_SECRET_KEY        → <strong random 64-char string>
CLERK_JWKS_URL        → https://...
STRIPE_SECRET_KEY     → sk_live_...
S3_ENDPOINT           → https://<account>.r2.cloudflarestorage.com
S3_ACCESS_KEY / S3_SECRET_KEY
RESEND_API_KEY
ENVIRONMENT           → production
```

### Step 2 — Run migrations in prod

```bash
docker run --rm \
  -e DATABASE_URL=postgresql+asyncpg://... \
  gem-api:latest \
  alembic -c alembic.ini upgrade head
```

### Step 3 — Deploy the worker

```bash
docker build -f apps/worker/Dockerfile -t gem-worker:latest .
docker push <ecr-url>/gem-worker:latest
```

Run two ECS tasks from this image with different commands:
- **Worker:** `celery -A celery_app worker --loglevel=info --concurrency=4`
- **Beat:** `celery -A celery_app beat --loglevel=info`

### Step 4 — Deploy the frontend

```bash
cd apps/web
npx vercel --prod
```

Set in Vercel project settings → Environment Variables:
```
NEXT_PUBLIC_API_URL              → https://api.yourdomain.com
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
CLERK_SECRET_KEY
```

### Legal gate

**Do NOT point production DNS to the API until** an Indian counsel written opinion on GeM ToS + DPDP Act 2023 is placed in `/legal/`. This is a hard requirement before Phase 2 launch.

---

## 12. Troubleshooting

### "Connection refused" on API startup

Postgres or Redis is not running. Check:
```bash
docker compose ps        # Are postgres and redis healthy?
```

### Migration fails with "relation already exists"

The database has a partial migration. Roll back and try again:
```bash
alembic downgrade base
alembic upgrade head
```

### Playwright download fails / browser not found

Install browser binaries:
```bash
playwright install chromium
# Inside Docker, this is done automatically by the Dockerfile
```

### Clerk 401 on API calls

- Check that `CLERK_JWKS_URL` in the API matches your Clerk app's JWKS URL exactly
- For local dev without Clerk, leave `CLERK_JWKS_URL=` blank — the API falls back to local HS256 JWT

### X-API-Key not working

API keys must be sent as:
```
X-API-Key: gem_live_<64-hex-chars>
```
Generate one at `POST /api/api-keys` via the dashboard or Swagger UI.

### Alert digest emails not sending

- Verify `RESEND_API_KEY` is set and the sending domain is verified in Resend
- Check the worker logs: `docker compose logs worker`
- The digest task runs once daily at 08:00 IST — trigger it manually for testing:
  ```bash
  docker compose exec worker \
    python -c "from tasks.digest import send_daily_digests; send_daily_digests()"
  ```

### Port conflicts

Default ports used: `5432` (Postgres), `6379` (Redis), `8000` (API), `3000` (Frontend).
Change the left side of port mappings in `docker-compose.yml` if any are taken.
