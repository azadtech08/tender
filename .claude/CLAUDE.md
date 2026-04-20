# GeM Tender Bot → SaaS Conversion

## Project Purpose
Converting a single-user Windows desktop scraper (`GeM_Tender_Bot.exe`) into a **multi-tenant SaaS** that scrapes India's Government e-Marketplace (gem.gov.in) for tender opportunities, extracts structured intelligence, and delivers AI-enhanced insights.

## Critical Constraint
**No Python source code exists** — only a compiled PyInstaller `.exe`. Phase 0 must either decompile it or perform a clean-room rewrite. Do NOT ship decompiled code — use it as spec only.

## Golden I/O Contract (must never break)
- **Input schema:** `run_history.json` — `{ keywords[], cards_per_kw, min_value }`
- **Output:** 23-column XLSX matching `output/Tenders_20260410_1635.xlsx` exactly
- **23 columns (in order):** S.No · Keyword · Tender Reference No · Tender Type · Published Date · Bid Submission End Date · Title · Description · Cleaned BOQ · Organisation · Ministry · Tender Value · EMD · State · Pincode · Delivery Period · Product Type · Exemption · Email · IT Relevant · Quantity · Link · Scraped Date
- **PDF regression corpus:** 30 PDFs in `downloads/` — all 23 fields must be ≥95% populated
- **Baseline throughput:** ~3.75 PDFs/min — new workers must beat this

## Monorepo Structure (target)
```
apps/api          FastAPI (Py 3.12) + Pydantic v2
apps/web          Next.js 14 (App Router) + TS + Tailwind + shadcn/ui
apps/worker       Playwright-Python + Celery 5
packages/shared   Auth abstraction, types, utilities
legacy/           Decompiled fragments (read-only reference, DO NOT SHIP)
legal/            Counsel opinion letter (required before prod DNS cutover)
```

## Key Stack Decisions (already decided — do not re-litigate)
| Layer | Choice |
|---|---|
| Frontend | Next.js 14 + shadcn/ui → Vercel |
| API | FastAPI + Pydantic v2 |
| Scraper | Playwright-Python in `mcr.microsoft.com/playwright/python` |
| Queue | Celery 5 + Redis 7 |
| DB | Postgres 16 (RDS) — JSONB + tsvector + pgvector |
| Object Storage | Cloudflare R2 (zero egress fees) |
| Auth | Clerk (JWT, teams) |
| Billing | Stripe Billing + Metered Usage |
| Proxies | Bright Data / Oxylabs residential India pool |
| AI | Claude API — Opus for long PDFs, Haiku for bulk |
| Embeddings | voyage-3 via Claude API |
| Region | AWS ap-south-1 (Mumbai) |

## Multi-tenancy Rules
- Every table with user data MUST have `tenant_id` (mandatory, enforced by Postgres RLS)
- API middleware reads JWT → sets `app.tenant_id` session variable → RLS does the rest
- Never return cross-tenant data — integration test asserts this

## Scraper Worker DAG
1. `search_keyword(job_id, keyword)` — parallel per keyword → returns bid cards
2. `download_bid(job_id, bid_id)` — fanned out, rate-limited → PDF to R2
3. `parse_pdf(job_id, bid_id)` — CPU queue, non-browser worker
4. `build_export(job_id)` — chord callback: XLSX/CSV/JSON to R2, fire notifications

## Phased Delivery (current: Phase 2 → Phase 3 next)
- **Phase 0:** ✓ Source recovery + scraper spec + Playwright POC (legal opinion pending external counsel)
- **Phase 1:** ✓ Single-tenant MVP
  - ✓ Infrastructure: FastAPI (7 routers), DB migrations 1–4, XLSX export, Next.js app, Celery skeleton, RLS
  - ✓ Real Playwright scraper (gem_scraper.py with stealth, PDF extraction, S3 upload)
  - ✓ 23-column XLSX export contract implemented and tested
- **Phase 2:** ✓ Multi-tenant + Clerk + Stripe + scheduling
  - ✓ Clerk JWT dual-mode (RS256 + HS256 fallback), Clerk middleware in web
  - ✓ Stripe billing (checkout, portal, webhooks, metered usage)
  - ✓ S3/R2 PDF + XLSX upload (utils/s3.py in worker and API)
  - ✓ Dark industrial UI (globals.css, JetBrains Mono, terminal log, progress ring)
  - ✓ jobs/[id] page: SSE live log, SVG progress ring, tenders table
  - ✓ Tenders grid: sticky columns, full 23-col view, debounced search, pagination
  - ✓ Scheduling: PATCH /jobs/{id}/schedule + Celery Beat tick every 60s
  - ✓ Tests: auth, jobs (CRUD + schedule), tenders, exports (23-col contract), PDF regression (30 PDFs)
- **Phase 3:** Schedules alerts, FTS, dedup, webhooks, API keys
- **Phase 4:** Claude summarization, pgvector eligibility scoring, NL search
- **Phase 5:** SSO, SOC 2, enterprise contracts

## Legal Blocker
**DO NOT push to prod DNS** until Indian counsel written opinion on GeM ToS + DPDP Act 2023 is filed in `/legal/`. This is a hard gate before Phase 2 launch.

## Anti-Bot Requirements
- Residential India proxies (3-provider failover)
- `playwright-stealth` + fingerprint randomization
- ≤1 req/sec/session, honor robots.txt
- Exponential backoff on 429/403
- Ops alert if failure rate >10% over 15 min
- Playwright traces of failed runs → R2, retained 30 days

## Pricing (INR/workspace/month)
Free: ₹0 · Starter: ₹1,499 · Pro: ₹4,999 · Business: ₹14,999 · Enterprise: Custom
Overage: ₹15/run · ₹2/tender · ₹3/AI summary

## Commands to Know
```bash
# Verify openpyxl can read the golden file
python3 -c "import openpyxl; wb = openpyxl.load_workbook('output/Tenders_20260410_1635.xlsx'); print([c.value for c in wb.active[1]])"

# Count PDFs in regression corpus
ls downloads/*.pdf | wc -l   # should be 30

# Run keywords from history
cat run_history.json | python3 -c "import json,sys; r=json.load(sys.stdin)[0]; print(r['keywords'])"
```

## Do NOT
- Re-discuss stack choices already decided
- Ship decompiled code from `legacy/`
- Hardcode secrets anywhere — use AWS Secrets Manager
- Use `tenant_id` bypass even in tests — test with RLS active
- Launch without legal opinion on file
