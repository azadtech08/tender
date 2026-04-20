# GeM Tender Bot → SaaS Conversion Plan

## Context

**What exists today:** A single Windows desktop tool (`GeM_Tender_Bot.exe`, 67.5 MB, PyInstaller-packed Python) that scrapes India's Government e-Marketplace (https://gem.gov.in) for tender opportunities, downloads bid PDFs, extracts 23 structured fields per tender, and writes an Excel report. It runs locally, stateless, single-user, no auth, no config files. The only artifacts in the package are the `.exe`, a flat `run_history.json` audit log, a `/downloads/` folder of PDFs, and `/output/Tenders_YYYYMMDD_HHMM.xlsx`.

**Observed baseline throughput:** 12 keywords × 3 cards × ~8 minutes = 30 PDFs per run on a single browser session (~3.75 PDFs/min). Any SaaS worker must beat this.

**Why convert to SaaS:** the tool solves a real procurement-intelligence problem but is trapped on one Windows desktop. As a hosted multi-tenant product it can serve many vendors, support scheduled runs, alerting, AI-assisted eligibility scoring, team collaboration, and recurring revenue via subscriptions.

**Hard constraint:** No Python source code is shipped in the package — only the compiled `.exe`. Any plan must address source recovery OR clean-room rewrite.

**Intended outcome:** A production-ready multi-tenant SaaS hosted in AWS ap-south-1 (Mumbai) with subscription billing, scheduled scraping, AI-enhanced tender intelligence, and an API — all reproducing the existing 23-column XLSX contract byte-for-byte on day one so existing users can migrate cleanly.

---

## Critical Files (golden I/O contract — must be reproduced exactly)

- `F:\GeM_Tender_SaaS\project\run_history.json` — run lifecycle + input schema (`keywords[]`, `cards_per_kw`, `min_value`)
- `F:\GeM_Tender_SaaS\project\output\Tenders_20260410_1635.xlsx` — golden 23-column XLSX the new exporter must match
- `F:\GeM_Tender_SaaS\project\downloads\*.pdf` — 30 sample PDFs → regression corpus for the new PDF parser (largest: `GEM_2026_B_7424230.pdf`, 411 KB)
- `F:\GeM_Tender_SaaS\project\GeM_Tender_Bot.exe` — Phase-0 reverse-engineering target

**Known 23 Excel columns** (from the golden file):
S.No · Keyword · Tender Reference No · Tender Type · Published Date · Bid Submission End Date · Title · Description · Cleaned BOQ · Organisation · Ministry · Tender Value · EMD · State · Pincode · Delivery Period · Product Type · Exemption · Email · IT Relevant · Quantity · Link · Scraped Date

---

## 1. Source Recovery Strategy

**Recommendation:** Run two tracks in parallel, treat the rewrite as the real deliverable.

1. **Spec-mining from the binary** (1 day of effort, not blocking):
   - Extract PyInstaller archive with `pyinstxtractor-ng` → `PYZ-00.pyz` + `.pyc` files
   - Detect Python version from bundled `python3X.dll`
   - Decompile with `decompyle3` (Py 3.9–3.11) or `pycdc` (Py 3.12+)
   - Dump strings with `strings GeM_Tender_Bot.exe` — URLs, XPaths, regexes are goldmines
   - Save everything under `legacy/` as read-only reference, **not** as source to ship
2. **Email the original developer** (Option C) — zero-cost check, if source arrives, use it as the spec
3. **Clean-room rewrite with Playwright-Python** — the actual SaaS implementation

**Risk:** if binary is obfuscated (PyArmor/Nuitka) or built with Py 3.12+, decompilation yields garbage. Mitigation: rewrite does not depend on decompilation success.

---

## 2. Target SaaS Architecture

### Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 14 (App Router) + TS + Tailwind + shadcn/ui, deployed on Vercel |
| API | FastAPI (Py 3.12) + Pydantic v2, REST + OpenAPI |
| Scraper runtime | Playwright-Python (Chromium headless) in `mcr.microsoft.com/playwright/python` Docker image |
| Job queue | Celery 5 + Redis 7 (broker + result backend) |
| Scheduler | Celery Beat (cron schedules live in Postgres) |
| DB | Postgres 16 on RDS (JSONB for tender payloads, `tsvector` for FTS, `pgvector` for AI embeddings) |
| Object storage | Cloudflare R2 (zero egress) for PDFs + XLSX exports |
| Auth | Clerk (hosted signup, JWTs, teams) |
| Multi-tenancy | Row-level isolation — mandatory `tenant_id` on every table + Postgres RLS policies |
| Billing | Stripe Billing + Stripe Metered Usage |
| Email | Resend (dev) → SES (scale) |
| Webhooks | Svix (outbound), Stripe/Clerk inbound |
| Observability | Sentry (errors), Better Stack (logs/metrics), Playwright traces archived to R2 on failure |
| Secrets | AWS Secrets Manager |
| Proxies | Bright Data or Oxylabs residential India pool with failover |

### Frontend pages
`/` marketing · `/dashboard` · `/jobs` · `/jobs/new` (form + schedule) · `/jobs/[id]` (live log via SSE, PDFs, extracted table) · `/tenders` (FTS grid) · `/tenders/[id]` (AI summary, eligibility score) · `/alerts` · `/workspace/members` · `/workspace/billing` · `/workspace/api-keys` · `/workspace/integrations`

### API endpoints (base `/api/v1`, JWT required, all scoped by `tenant_id`)
```
POST   /jobs            { keywords[], cards_per_kw, min_value, filters, schedule? }
GET    /jobs            ?status=&from=&to=&page=
GET    /jobs/{id}
GET    /jobs/{id}/events           SSE stream
POST   /jobs/{id}/cancel
POST   /jobs/{id}/retry
GET    /jobs/{id}/export.{xlsx,csv,json}
GET    /tenders         FTS + filters
GET    /tenders/{bid_id}
POST   /tenders/{bid_id}/summarize   (Claude API, cached)
POST   /tenders/{bid_id}/score       (eligibility, cached)
CRUD   /alerts
GET/PUT /profile/company
CRUD   /webhooks
GET    /usage
POST   /billing/portal
POST   /integrations/{stripe,clerk}/webhook   (unauth, signature-verified)
```

### Scraping worker DAG (Celery chord)
1. `search_keyword(job_id, keyword)` — parallel per keyword, returns bid cards
2. `download_bid(job_id, bid_id)` — fanned out, rate-limited, routes PDF to R2
3. `parse_pdf(job_id, bid_id)` — CPU queue on non-browser worker
4. `build_export(job_id)` — chord callback: XLSX/CSV/JSON to R2, update job, fire notifications

Per-tenant concurrency caps enforced at enqueue. Soft limit 30 min, hard 60 min per job.

### Postgres core schema
`tenants`, `workspaces`, `users`, `workspace_members` (role: owner/admin/analyst/viewer) · `plans`, `subscriptions`, `usage_events` · `jobs` (params jsonb, status, output_xlsx_key), `job_events` (SSE replay), `schedules` · `tenders` (unique `(workspace_id, bid_id)` for dedup, `search_vector tsvector`, `embedding vector(1536)`) · `alerts`, `alert_deliveries`, `webhooks`, `webhook_deliveries` · `api_keys`, `audit_log` · `company_profiles` (for AI eligibility matching)

All tables with `tenant_id` protected by Postgres RLS policies reading a session variable set by API middleware from the JWT.

---

## 3. Feature Enhancements Beyond Current Tool

**v1 (launch parity + SaaS essentials):**
- Scheduled recurring scrapes (daily/weekly/hourly cron)
- Incremental diff — only surface new `bid_id`s per workspace
- Deduplication via unique `(workspace_id, bid_id)` index, updates `last_seen_at`
- Postgres full-text search across title + description + cleaned BOQ + org
- Saved searches + alert rules with email digest
- Exports: XLSX (bit-identical to legacy), CSV, JSON, Google Sheets live sync
- REST API + API keys
- Outbound webhooks (`job.completed`, `tender.new`, `tender.matched`, `alert.triggered`)
- RBAC (owner/admin/analyst/viewer)
- Mobile-responsive dashboard

**v2 (high-value AI):**
- Claude summarization per PDF (Opus for long, Haiku for bulk), cached in `tenders.raw.ai_summary`
- Eligibility scoring: embed `company_profiles.capability_text` + tender BOQ via `voyage-3`, cosine ranking, hard-filter by state/value/MSME
- Natural-language search: "laptops above 10 lakh in Maharashtra this week" → structured filter via Claude
- Claude-drafted first-cut bid response
- Team comments, analyst assignment, Kanban pipeline (qualify → bid → won/lost)
- Slack/Teams notifications, Google Sheets sync
- Analytics: trends, top ministries, value distribution, win-rate

---

## 4. Deployment Topology

- **Cloud + region:** AWS `ap-south-1` (Mumbai) — latency to GeM + DPDP data residency
- **Early-stage alt:** Render/Railway + Upstash Redis + R2 until first enterprise deal
- **Compute:** ECS Fargate (skip k8s until worker fleet > 30 tasks)
  - `gem-api` (Fargate, ALB, autoscale on CPU/req)
  - `gem-scraper-worker` (2 vCPU / 4 GB, autoscale on Celery queue depth)
  - `gem-parser-worker` (CPU-only, smaller tasks)
  - `gem-scheduler` (Celery Beat, `desired=1`)
  - `gem-web` on Vercel
- **Managed:** RDS Postgres, ElastiCache Redis, Secrets Manager, SES, R2 (cross-cloud)
- **CI/CD:** GitHub Actions → ECR → ECS update-service; Alembic migrations as one-shot ECS task before deploy; Vercel for frontend previews
- **Scaling:** autoscale workers on Celery queue depth (target 0–2 pending/worker); per-plan concurrency caps enforced at enqueue; Pro=1, Business=3, Enterprise=10 concurrent runs
- **Secrets:** AWS Secrets Manager, injected via ECS task-def `secrets`, never in env files or images

---

## 5. Legal, Compliance & Risk

- **BLOCKER before launch:** obtain Indian counsel written opinion on GeM ToS (`https://gem.gov.in/termsCondition`), IT Act 2000 §43, and public-data scraping precedent. Do not ship until in hand.
- **Prefer official GeM API** if it exists and is accessible — strictly safer than scraping. Architecture decouples `scraper` module so it's a drop-in swap.
- **Fallback posture if scraping is required:** polite crawling (≤1 req/sec/session), honor robots.txt, no auth bypass, no reselling raw PDFs — sell the intelligence/alerting/AI layer, not the data.
- **DPDP Act 2023:** register as Data Fiduciary, publish privacy notice, honor DSR endpoints (`DELETE /me`), India-only hosting, TLS 1.2+, RDS encryption at rest, quarterly review. Tender PDFs contain officials' contact emails — treat as sensitive.
- **Anti-bot:** residential India proxies with 3-provider failover; `playwright-stealth`; fingerprint randomization; exponential backoff on 429/403; ops alert (Better Stack/PagerDuty) if failure rate > 10% over 15 min; Playwright traces of failed runs retained 30 days in R2.
- **Marketing copy:** position as "tender intelligence platform," never "scraping bot."

---

## 6. Monetization & Pricing (INR per workspace per month)

| Tier | Price | Runs | Keywords/run | Schedules | Retention | Seats | API | AI summaries |
|---|---|---|---|---|---|---|---|---|
| Free | 0 | 5 | 3 | 0 | 30 d | 1 | — | 0 |
| Starter | 1,499 | 30 | 10 | 1 daily | 90 d | 2 | read | 50 |
| Pro | 4,999 | 150 | 25 | 5 daily / 1 hourly | 1 y | 5 | full | 500 |
| Business | 14,999 | 600 | 100 | unlimited | 3 y | 20 | full | 5,000 |
| Enterprise | Custom | Custom | Custom | Custom | Unlimited | Unlimited | SLA + SSO + VPC | Custom |

**Overage (Stripe Metered):** ₹15/extra run · ₹2/extra tender · ₹3/extra AI summary
**Annual discount:** 2 months free (~17%) · **Launch offer:** 3 months Starter free for first 100 workspaces

---

## 7. Phased Rollout (exit criteria only, no timelines)

### Phase 0 — Source recovery & spec freeze
- Extracted binary + decompiled fragments saved under `legacy/` (read-only reference)
- Written scraper spec: URLs, selectors, PDF regex catalog
- Legal opinion letter on GeM ToS + DPDP on file
- Playwright POC scraping 1 keyword end-to-end
- **Exit:** spec + legal opinion + working POC

### Phase 1 — Single-tenant MVP
- Monorepo (`apps/api`, `apps/web`, `apps/worker`, `packages/shared`)
- 5 API endpoints (jobs create/list/get/events/export)
- Single-tenant schema (no `tenant_id` yet), Celery + Playwright worker, bit-identical XLSX to golden file
- Next.js UI: `/jobs/new`, `/jobs`, `/jobs/[id]`
- Magic-link auth for one admin user, hosted on Render/Fly.io
- **Exit:** re-scrape the same 12 keywords from `run_history.json`, diff output XLSX against legacy, account for every column

### Phase 2 — Multi-tenant + auth + billing
- Add `tenant_id` + Postgres RLS everywhere
- Clerk signup, workspace creation, members + roles
- Stripe Free/Starter/Pro live, checkout, customer portal, metered usage
- Per-plan concurrency caps
- Migrate to AWS ap-south-1
- Sentry + Better Stack live
- **Exit:** 2 Starter + 1 Pro customer paying, invoices flowing

### Phase 3 — Schedules, alerts, notifications, dedup
- `schedules` table + Celery Beat
- Incremental diff + dedupe via `tenders` unique index
- Saved alerts → daily email digest (Resend/SES)
- Slack webhooks, Google Sheets sync
- Postgres full-text search in `/tenders`
- REST API + API keys, outbound webhooks (Svix)
- **Exit:** a real customer receives the 08:00 IST daily digest with ≥1-click export

### Phase 4 — AI features
- Claude per-tender summarization (cached)
- `company_profiles` + pgvector embeddings + cosine eligibility score shown on every tender
- Natural-language search, Claude-drafted responses
- AI cost tracking in `usage_events`
- **Exit:** customer reports >30% triage time saved vs manual

### Phase 5 — Enterprise
- SSO (SAML/OIDC via Clerk or WorkOS), SCIM provisioning, audit log export, SLA monitoring
- Dedicated worker pool per enterprise tenant
- VPC/on-prem Terraform module
- SOC 2 Type I readiness
- **Exit:** first enterprise contract signed

---

## 8. Key Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| GeM portal DOM/flow changes | High | Breaks all runs | Canary job every 30 min; archived Playwright traces; selectors centralized in one module; ops on-call |
| Anti-bot escalation (CAPTCHA, IP ban) | High | Manual review queue, proxy cost spike | 3-provider residential pool; stealth + fingerprinting; circuit breaker |
| Source recovery fails (obfuscated binary) | Medium | Slower Phase 0 only | Clean rewrite already baked in; does not block SaaS build |
| Legal takedown / ToS violation | Medium | Existential | Legal opinion before launch; prefer official API; fallback "bring your own GeM login" model |
| Proxy cost blowout | Medium | Margin erosion | Per-plan run caps; cache PDFs 30 d in R2 (re-runs never re-download); metered overage |
| PDF parser drift across ministries | High | Bad data quality | Golden-file regression tests using the 30 sample PDFs; per-field error logging surfaced in `/jobs/[id]` |
| Postgres hot `tenders` table | Low now, Medium at scale | Slow writes | Partition by `workspace_id` hash at 10M rows; move FTS to OpenSearch if needed |
| Clerk/Stripe vendor lock-in | Low | Switching cost | Auth abstraction in `packages/shared/auth`; billing handlers isolated |
| DPDP non-compliance | Medium | Fine + reputation | Day-1 DPO, privacy notice, DSR endpoints, India-only hosting, encryption at rest, quarterly review |
| GeM ships an official API | Low | Good problem | `scraper` module decoupled — swap with API client, rest unchanged |

---

## Verification Plan

End-to-end acceptance once Phase 1 is built:

1. **Golden-file diff test**
   - Re-run the exact 12 keywords from `run_history.json` (`Server`, `Laptop`, `AMC`, `CAMC`, `FMS`, `Networking`, `Firewall`, `HPC`, `Workstation`, `Software Development`, `IT Support`, `Data Center`) with `cards_per_kw=3`, `min_value=50000`
   - Compare new XLSX against `output/Tenders_20260410_1635.xlsx` cell-by-cell using `openpyxl`
   - Assert: same 23 column headers, same column order, same data types, same formulas for computed columns
   - Allow data-drift (new live tenders) but assert schema identity

2. **PDF parser regression corpus**
   - Pytest fixture loads all 30 PDFs from `downloads/`
   - For each PDF assert all 23 fields populate (non-null OR expected-null per ministry type)
   - Track per-field success rate; fail build if < 95%

3. **Scraper canary**
   - Playwright headed-mode smoke test hitting GeM's public search for 1 keyword
   - Runs in CI nightly + in prod every 30 min → Better Stack alert on failure

4. **Multi-tenant isolation**
   - Create 2 tenants, run jobs in each, assert tenant A cannot read tenant B's jobs/tenders/PDFs via API, DB query, or signed-URL guess
   - Integration test asserts RLS blocks cross-tenant SELECTs even with raw psql

5. **Billing flow**
   - Stripe test-mode: signup → Starter checkout → trigger 31st run → assert overage event recorded in `usage_events` and billed

6. **Load / throughput**
   - k6 script: 10 concurrent tenants × 1 job each × 5 keywords; assert p95 job duration < 2× single-worker baseline (16 min) and no task failures

7. **Legal sign-off gate**
   - Manual: counsel opinion letter filed in `/legal/` before prod DNS cutover
