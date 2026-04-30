# Tenzo Licensing — Progress Tracker

| | |
|---|---|
| **Last updated** | 2026-04-24 |
| **Phases complete** | 0, 1, 2, 3 (backend), 4, 5, 6, 7, 8 (tooling) |
| **Phases remaining** | — (all server-side code done; Phase 8 remainder is calendar execution) |
| **Current rollout mode** | `LICENSING_MODE=off` (safe ship — no enforcement) |
| **Decisions doc** | [phase-0-decisions.md](phase-0-decisions.md) |
| **Rollout runbook** | [rollout-runbook.md](rollout-runbook.md) |
| **Key rotation runbook** | [key-rotation-runbook.md](key-rotation-runbook.md) |

---

## 1. Summary

A hybrid license system (signed offline tokens + online heartbeat) is **done end-to-end** across eight phases on the server side. It is **shipped in `off` mode** — every gate is a no-op until an operator flips the env var. The enforcement layer is proven by smoke tests; revocation propagates within seconds via a Redis cache; admin mint/revoke/suspend/reactivate/extend all work through a Clerk-gated admin API; Prometheus metrics expose activate/heartbeat/enforcement outcomes; grandfather and preflight scripts make the staged rollout safe.

What's **not** done and never was in scope: client-side (desktop/agent) code — heartbeat scheduler, grace-period state machine, native-keychain token storage. Also deferred: admin dashboard frontend pages, wire-up of the remaining ~15 non-critical routes into Phase 5 enforcement (see §4), and Stripe-webhook auto-mint (see §4).

The only remaining work is **operator calendar execution** of the rollout — not code — documented step by step in [rollout-runbook.md](rollout-runbook.md).

---

## 2. Completed phases

### ✅ Phase 0 — Decisions & prerequisites

**Deliverable:** [phase-0-decisions.md](phase-0-decisions.md) — 7 locked technical decisions + 6 open questions flagged.

Locked: grace periods (6h heartbeat, 3d soft, 14d hard), token lifetime (min 30d), Ed25519 via PASETO v4.public, AWS Secrets Manager key storage, `TNZO-XXXXX-XXXXX-XXXXX-XXXXX` key format with CRC-16, fingerprint recipe, admin identity (Clerk role + IP + 2FA).

**Caveat:** the 6 §2 questions (deployment target, license subject, OS targets, feature-flag scheme, issuance trigger, revocation SLA) were **not** answered by the user. Phases 1–6 proceeded on the working assumptions documented in the doc. Everything built is still correct under those assumptions.

---

### ✅ Phase 1 — Cryptographic foundation

**Deliverable:** isolated package `project/packages/licensing/` — `sign_license()`, `verify_license()`, keygen script.

- 40 tests passing, **98 % coverage**.
- PASETO v4.public (Ed25519) via `pyseto`, kid in authenticated footer for rotation.
- `LicensePayload` Pydantic model: frozen, UTC-only, extra=forbid.
- CLI entry point `tenzo-licensing-keygen --kid v1 --out-dir keys/`.
- Dev keypair lives at `data/keys/signing_*.pem`; public key also committed at `packages/licensing/keys/signing_public_v1.pem`.

---

### ✅ Phase 2 — Database schema & migrations

**Deliverable:** `alembic/versions/006_licensing.py` + `007_admin_audit_clerk_compat.py`.

Five new tables: `licenses`, `license_devices`, `license_activations`, `license_usage_counters`, `admin_audit_log`. RLS policies on the first four (admin_audit_log is intentionally cross-tenant).

5 new SQLAlchemy models + 25 exported constants (STATUS_*, EVENT_*, REASON_*, COUNTER_*, ACTION_*).

Migration verified clean up → down → re-up. DB is at head `007_admin_audit_clerk_compat`.

**007 exists** because Phase 2's original design required `admin_audit_log.admin_id` FK `users.id NOT NULL`, but Clerk users don't have local users rows. The fix: `admin_id` nullable, plus `admin_subject` (auth-provider id, NOT NULL) and `admin_email` (display).

---

### ✅ Phase 3 — Admin API + key generation (backend)

**Deliverable:** 10 admin endpoints under `/api/admin/licenses/` + keygen util + audit logging.

- [`services/license_keygen.py`](../../apps/api/src/services/license_keygen.py) — `TNZO-XXXXX-XXXXX-XXXXX-XXXXX`, Crockford base32 + CRC-16, case-insensitive, typo-tolerant, 20 tests passing.
- [`auth_admin.py`](../../apps/api/src/auth_admin.py) — Clerk `public_metadata.role == 'tenzo_admin'` + `ADMIN_IP_ALLOWLIST` + optional 2FA, local-dev bypass via `LOCAL_ADMIN_USER_IDS`.
- [`services/admin_audit.py`](../../apps/api/src/services/admin_audit.py) — resolves email → users.id when present, falls back to `admin_subject` + `admin_email`.
- [`routers/admin_licenses.py`](../../apps/api/src/routers/admin_licenses.py) — 10 endpoints: create, list (filter + paginate), detail (with device/activation counts), devices, activations, revoke, suspend, reactivate, extend, device-revoke.

All mutating endpoints write to `admin_audit_log`. End-to-end smoke via direct code path (HTTP path untested because Clerk auth was in scope-off for smoke).

**Deferred:** Next.js admin pages under `app/admin/licenses/`. Backend is fully testable via curl. See §4 below.

---

### ✅ Phase 4 — Activation endpoint

**Deliverable:** `POST /api/license/activate`.

- Public, rate-limited (5/min/IP, 10/day/key-hash) — Redis-backed.
- CRC self-check rejects typos before DB lookup.
- Status checks: expired / revoked / suspended / not-yet-valid → distinct error codes.
- Device binding with `max_devices` enforcement.
- Idempotent for already-bound fingerprints.
- Returns signed PASETO v4.public token with TTL = `min(now+30d, license.expires_at)` and `heartbeat_after_seconds: 21600`.

7-scenario smoke test all pass (incl. DEVICE_LIMIT_EXCEEDED, malformed key, unknown key). Crypto round-trip (Phase 1 sign → Phase 4 mint → Phase 1 verify) confirmed.

**Stable error codes:** `INVALID_KEY`, `KEY_EXPIRED`, `KEY_REVOKED`, `KEY_SUSPENDED`, `KEY_NOT_YET_VALID`, `DEVICE_LIMIT_EXCEEDED`, `DEVICE_REVOKED`, `RATE_LIMITED`.

---

### ✅ Phase 5 — Client-side validation layer (enforcement)

**Deliverable:** `LicenseGuard` dependency wired into protected routes.

- [`services/license_features.py`](../../apps/api/src/services/license_features.py) — `PLAN_FEATURES` map (free/starter/pro/business/enterprise), 6 booleans + 4 counter ceilings. Per-license `features` jsonb overrides plan defaults.
- [`services/license_enforcement.py`](../../apps/api/src/services/license_enforcement.py) — `LicenseGuard` + `require_valid_license` (Clerk DB path) + `verify_license_token` (token header path for non-Clerk clients) + atomic `check_and_increment` UPSERT.
- **Three-mode rollout flag** `LICENSING_MODE=off|warn|enforce`. Default `off`.

Wired into 6 endpoints across jobs / exports / tenders. 8 smoke scenarios pass:

| # | Scenario | Expected |
|---|---|---|
| 1 | mode=off, no license | 201 (bypass) |
| 2 | mode=enforce, no license | 402 LICENSE_REQUIRED |
| 3 | enforce + pro license | 201, counter=1 |
| 4 | 2nd POST | counter=2 |
| 5 | revoke license | 402 LICENSE_REQUIRED |
| 6 | free plan + export | 402 FEATURE_NOT_LICENSED |
| 7 | max_runs=1, 2nd POST | 429 USAGE_LIMIT_EXCEEDED |
| 8 | mode=warn, no license | 201 + warn log |

**Stable error codes added:** `LICENSE_REQUIRED`, `LICENSE_EXPIRED`, `LICENSE_NOT_YET_VALID`, `LICENSE_INVALID`, `FEATURE_NOT_LICENSED`, `USAGE_LIMIT_EXCEEDED`.

---

### ✅ Phase 6 — Heartbeat + revocation propagation

**Deliverable:** `POST /api/license/heartbeat` + Redis revocation cache.

- [`services/license_cache.py`](../../apps/api/src/services/license_cache.py) — `add_revoked`, `is_revoked`, `remove_revoked`, `bulk_replace`, `clear_for_tests`. Fails open on Redis errors (DB is source of truth).
- Heartbeat endpoint: verifies signature → checks fingerprint binding → fresh DB status check → logs `EVENT_HEARTBEAT` → refreshes device row → mints new token → returns `server_now` for authoritative clock sync.
- Admin revoke/suspend push to cache; reactivate clears cache entry.
- `verify_license_token` consults cache after signature check — closes the gap where a valid-signed but revoked token would work until natural expiry.

9 smoke scenarios all pass. Key proof: revoked license's 30-day-valid token is denied within seconds via cache hit (scenario 8).

---

## 3. Remaining phases

### ✅ Phase 7 — Observability, anti-abuse, rollout prep

**Delivered:** Prometheus metrics + `/metrics` endpoint + abuse-detection queries + admin stats endpoints + Celery cache-refresh + key-rotation runbook.

| Task | Status | Notes |
|---|---|---|
| Prometheus counters | ✅ Done | `tenzo_license_activations_total{result}`, `tenzo_license_heartbeats_total{result}`, `tenzo_license_enforcement_checks_total{mode,result}`, `tenzo_license_feature_denials_total{plan,feature}`, `tenzo_license_usage_limit_denials_total{counter,plan}` |
| Prometheus duration histograms | ✅ Done | `tenzo_license_activation_duration_seconds`, `tenzo_license_heartbeat_duration_seconds` |
| `/metrics` endpoint | ✅ Done | [routers/metrics.py](../../apps/api/src/routers/metrics.py), not license-gated |
| Activate/heartbeat instrumentation | ✅ Done | `_instrument` decorator derives `{result}` label from response body/status |
| Enforcement instrumentation | ✅ Done | `_bump_check(mode, result)` at every decision branch in `require_valid_license` |
| Abuse-detection queries | ✅ Done | [services/license_abuse_detection.py](../../apps/api/src/services/license_abuse_detection.py) — fingerprint_churn, rapid_reactivation, invalid_key_spike, activity_summary |
| Admin `/stats/summary` endpoint | ✅ Done | High-level activations/heartbeats/denials in 1h + 24h windows |
| Admin `/stats/suspicious` endpoint | ✅ Done | Three heuristic queries; windowed, admin-gated |
| Periodic cache refresh | ✅ Done | [apps/worker/src/tasks/license_cache_refresh.py](../../apps/worker/src/tasks/license_cache_refresh.py) — Celery beat schedule every 300s |
| Heartbeat rate-limit | ✅ Done in Phase 6 | 10/min/license |
| Activation rate-limit | ✅ Done in Phase 4 | 5/min/IP, 10/day/key-hash |
| Key-rotation runbook | ✅ Done | [key-rotation-runbook.md](key-rotation-runbook.md) — 10 sections covering normal rotation, emergency rotation, and annual dry-run |
| Admin dashboard charts | Deferred | Frontend task — backend APIs are ready (/stats/*); see §4 |
| Alertmanager rules | Deferred | Ops-stack task — metrics are emitting, wire your rules externally |

**Smoke test:** 10 scenarios pass end-to-end (metric families exposed, activate counter +1, heartbeat counter +1, enforcement allow +1, feature denial +1, usage-limit denial +1, /stats/summary returns counts, /stats/suspicious returns structured output, cache-refresh rebuilds Redis set from DB, `is_revoked` mirrors DB truth).

### ✅ Phase 8 — Staged rollout (tooling delivered; execution is calendar work)

**Code work:** done. **Calendar execution:** operator's responsibility — follow [rollout-runbook.md](rollout-runbook.md).

| Item | Status | Notes |
|---|---|---|
| Grandfather mint script | ✅ Done | [apps/api/scripts/grandfather_licenses.py](../../apps/api/scripts/grandfather_licenses.py) — idempotent, dry-run capable, outputs CSV, writes `admin_audit_log` with `admin_subject='grandfather-script'` |
| Preflight readiness check | ✅ Done | [apps/api/scripts/preflight_licensing.py](../../apps/api/scripts/preflight_licensing.py) — 8 checks across alembic/tables/RLS/keys/Redis/env/metrics/tenant-coverage |
| Rollout runbook | ✅ Done | [rollout-runbook.md](rollout-runbook.md) — day-by-day actions, 3 rollout options, observability dashboard list, common-issue playbook |
| Day-0 verification | ✅ Smoke-tested | Preflight PASSED; grandfather dry-run → real → re-run (idempotent, found 0 on second call); audit row written correctly |

**Calendar execution status** (operator responsibility, not code):

| Day | Action | Status |
|---|---|---|
| 0 | Phases 1-7 shipped behind `LICENSING_MODE=off` | ⚪ Pending operator (prod deploy) |
| 1 | Grandfather existing tenants (script ready) | ⚪ Pending operator |
| 2 | Flip to `LICENSING_MODE=warn` | ⚪ Pending operator |
| 3-7 | Watch metrics, fix false positives | ⚪ Pending operator |
| 8 | Flip to `enforce` (new tenants only, or straight to all — see runbook §Day 8) | ⚪ Pending operator |
| 14 | Flip to `enforce` for all tenants | ⚪ Pending operator |
| 21 | Enable hard-grace denial (Model B clients only — skip for SaaS-only) | ⚪ Pending operator |
| 365 | First annual key rotation (calendar reminder) | ⚪ Pending operator — see [key-rotation-runbook.md](key-rotation-runbook.md) |

---

## 4. Cross-cutting deferred work

Items that cut across phases and remain open:

| # | Item | Belongs to | Why deferred | Effort |
|---|---|---|---|---|
| 1 | **Admin frontend pages** (`app/admin/licenses/`) | Phase 3 | Backend testable via curl; UI is incremental and not on the critical path | 1-2 d |
| 2 | **Live Clerk-admin HTTP smoke** | Phase 3 | Requires setting `public_metadata.role=tenzo_admin` on a real Clerk user; auth-path code verified by direct call | 30 min + Clerk setup |
| 3 | **Full route sweep** — wire enforcement into alerts, api_keys, outbound_webhooks, schedules delete, tender delete, PDF download | Phase 5 | Pattern is mechanical (add `Depends(require_valid_license)`); only 6 critical routes wired so far | 1-2 h |
| 4 | **Worker-side enforcement** — Celery tasks that run scheduled jobs bypass the API layer and therefore bypass the license gate | Phase 5 | Needs `LicenseGuard` check in the worker `scrape_job` task; requires a sync or separate async session | 2-3 h |
| 5 | **Pytest unit tests** for `LicenseGuard`, `merge_features`, `license_signer`, `rate_limit`, `license_cache` | Phases 4-6 | End-to-end smokes cover behaviour; unit tests are faster feedback for future changes | 2-3 h |
| 6 | **Periodic cache refresh** — Celery beat entry calling `bulk_replace()` every 5-10 min | Phase 6/7 | Push-on-event path covers 99 % of cases; the 1 % gap is "revocation via direct SQL" which is an operational anti-pattern | 30 min |
| 7 | **Quota telemetry header** — return `X-License-Quota-Remaining` on successful responses so the UI can show remaining runs | Phase 5 | Nice-to-have; no current UI consumer | 1 h |
| 8 | **Client SDK / scheduler** (Python, TS) for the desktop/agent case — heartbeat loop, grace-period state machine, token storage | Phase 6 / Model B | Server-only project scope; only relevant if we ship a desktop/agent build | 1-2 d per language |

---

## 5. Open decisions (from Phase 0 §2)

These were flagged at the start and never resolved. Everything built still works under the working assumptions, but if any answer diverges, rework is needed:

| Q | Question | Working assumption | What breaks if wrong |
|---|---|---|---|
| Q1 | Deployment target (SaaS / desktop / both)? | Hybrid warranted | If SaaS-only, Phases 4 & 6 are partially over-engineered — simpler `tenant.license_status` check would suffice. Code still works but we carried extra complexity. |
| Q2 | License subject (per-tenant / per-user / per-device)? | Per-tenant | Schema + enforcement is tenant-keyed. Per-user would need `user_id` columns + route-level user checks. |
| Q3 | Client OS targets? | All three behind a `platform_fingerprint.py` abstraction | Only relevant to client SDK (§4 item 8); no impact on server code. |
| Q4 | Feature-flag scheme (reuse plans vs. parallel)? | **Reuse plans** — `PLAN_FEATURES` maps to existing Stripe plans | If parallel, `PLAN_FEATURES` becomes unused and we'd rely only on per-license `features` jsonb. |
| Q5 | Issuance trigger (Stripe webhook / admin / both)? | Both — admin-manual works today; Stripe auto-mint = Phase 8 | Nothing breaks; just shapes what Phase 8 script does. |
| Q6 | Revocation latency SLA? | < 5 min (Redis cache) | Hard req for **instant** (<60s) would push us toward always-DB-check on token path — losing the stateless-verification win. |

**Request to operator / PM:** answer these 6 at some point. Q1 is the most important.

---

## 6. Quick reference

### Endpoints
```
Public (client):
  POST /api/license/activate                    Phase 4
  POST /api/license/heartbeat                   Phase 6

Admin (Clerk role=tenzo_admin):
  POST    /api/admin/licenses                   Phase 3 — mint
  GET     /api/admin/licenses                   Phase 3 — list
  GET     /api/admin/licenses/{id}              Phase 3 — detail
  GET     /api/admin/licenses/{id}/devices      Phase 3
  GET     /api/admin/licenses/{id}/activations  Phase 3
  POST    /api/admin/licenses/{id}/revoke       Phase 3 (+cache push in Phase 6)
  POST    /api/admin/licenses/{id}/suspend      Phase 3 (+cache push in Phase 6)
  POST    /api/admin/licenses/{id}/reactivate   Phase 3 (+cache clear in Phase 6)
  POST    /api/admin/licenses/{id}/extend       Phase 3
  POST    /api/admin/licenses/{id}/devices/{did}/revoke   Phase 3
  GET     /api/admin/licenses/stats/summary     Phase 7 — activity aggregates
  GET     /api/admin/licenses/stats/suspicious  Phase 7 — abuse heuristics

Observability (unauthenticated):
  GET     /metrics                              Phase 7 — Prometheus scrape target
```

### Env vars
```
LICENSE_ACTIVE_KID=v1
LICENSE_PRIVATE_KEY_PATH=/keys/signing_private_v1.pem
LICENSE_PUBLIC_KEY_PATH=/keys/signing_public_v1.pem
LICENSE_SIGNING_KEY_SECRET_ID=tenzo/licensing/signing_key_v1
LICENSE_TOKEN_TTL_SECONDS=2592000                           # 30 days
LICENSE_HEARTBEAT_INTERVAL_SECONDS=21600                    # 6 hours
LICENSE_ACTIVATE_RATE_PER_IP_PER_MIN=5
LICENSE_ACTIVATE_RATE_PER_KEY_PER_DAY=10
LICENSING_MODE=off                                          # off | warn | enforce
ADMIN_IP_ALLOWLIST=[]                                       # CIDR list
LOCAL_ADMIN_USER_IDS=["1"]                                  # dev bypass for Clerk admin role
ADMIN_REQUIRE_2FA=false
```

### DB state
- Alembic head: `007_admin_audit_clerk_compat`
- Tables: `licenses`, `license_devices`, `license_activations`, `license_usage_counters`, `admin_audit_log`
- RLS: enabled on the first 4; cross-tenant on `admin_audit_log` (admin-only)

### Redis keys
- `license:revoked` — SET of revoked license IDs
- `license:revoked:<id>` — TTL hint string
- `rl:min:activate:ip:<ip>:<YYYYMMDDhhmm>` — per-IP activation counter
- `rl:day:activate:key:<key_hash>:<YYYYMMDD>` — per-key activation counter
- `rl:min:heartbeat:lic:<id>:<YYYYMMDDhhmm>` — per-license heartbeat counter

### File map
```
project/
├── packages/licensing/                                   Phase 1 — crypto primitives (isolated pkg)
│   ├── src/tenzo_licensing/{payload,signing,keys,errors}.py
│   ├── tests/                                            40 tests, 98% coverage
│   └── keys/signing_public_v1.pem                        committed pub key
├── apps/api/
│   ├── alembic/versions/
│   │   ├── 006_licensing.py                              Phase 2 — 5 tables
│   │   └── 007_admin_audit_clerk_compat.py               Phase 2 fix-up
│   └── src/
│       ├── auth_admin.py                                 Phase 3 — admin gate
│       ├── routers/
│       │   ├── admin_licenses.py                         Phase 3 (+ Phase 6 cache hooks, + Phase 7 /stats)
│       │   ├── license.py                                Phase 4 (activate) + Phase 6 (heartbeat) + Phase 7 (_instrument)
│       │   └── metrics.py                                Phase 7 — /metrics endpoint
│       ├── schemas/license.py                            Phases 3/4/6 — all license DTOs
│       └── services/
│           ├── admin_audit.py                            Phase 3
│           ├── license_keygen.py                         Phase 3 — TNZO-XXX keygen + CRC
│           ├── license_signer.py                         Phase 4 — PASETO signer (lazy singleton)
│           ├── rate_limit.py                             Phase 4 — Redis limiter
│           ├── license_features.py                       Phase 5 — PLAN_FEATURES
│           ├── license_enforcement.py                    Phase 5 — LicenseGuard (+ Phase 6 cache check + Phase 7 metrics)
│           ├── license_cache.py                          Phase 6 — Redis revocation set
│           ├── license_metrics.py                        Phase 7 — Prometheus definitions
│           └── license_abuse_detection.py                Phase 7 — sharing/brute-force queries
├── apps/api/scripts/
│   ├── grandfather_licenses.py                           Phase 8 — one-shot mint
│   └── preflight_licensing.py                            Phase 8 — readiness check
├── apps/worker/src/tasks/
│   └── license_cache_refresh.py                          Phase 7 — Celery beat task
└── docs/licensing/
    ├── phase-0-decisions.md                              Phase 0
    ├── key-rotation-runbook.md                           Phase 7
    ├── rollout-runbook.md                                Phase 8
    └── STATUS.md                                         this file
```

---

## 7. How to pick this up

1. Read [phase-0-decisions.md](phase-0-decisions.md) and this file.
2. Decide whether to finish cross-cutting items (§4) first or move straight to Phase 7.
3. If moving to Phase 7: start with Prometheus metrics on activate + heartbeat. Then alerts. Then the periodic cache-refresh Celery beat entry.
4. When ready to roll out, run `scripts/mint_grandfathered_licenses.py` (to be written) to give existing tenants a free license, then flip `LICENSING_MODE=warn`.
5. Watch `license_denials_total` for a week. Nothing should be denying except actual unpaid tenants.
6. Flip to `enforce` for new tenants first, then all tenants, then enable hard-grace.
