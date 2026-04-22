# Tenzo Licensing — Phase 0 Decisions

| | |
|---|---|
| **Status** | DRAFT — awaiting user confirmation on §2 open questions |
| **Scope** | Hybrid licensing model (signed offline license + online heartbeat) |
| **Prepared** | 2026-04-22 |
| **Next phase** | Phase 1 — cryptographic foundation (blocked on §2) |

---

## 1. Context

Tenzo currently allows any authenticated tenant to use all features. We are adding a license-key layer so that only explicitly authorized tenants can access paid functionality, with admin-controlled expiry, device/session limits, and usage caps.

This document locks the decisions that Phase 1 onward depend on. Decisions marked **LOCKED** are final; decisions in §2 need the user to resolve before Phase 1 begins.

Existing relevant infrastructure (pulled from `.claude/CLAUDE.md` and `packages/db-models/`):

- Tenancy is keyed by `tenant_id: String(36)` on every user-data table, enforced by Postgres RLS.
- Subscriptions already exist per tenant (`subscriptions` table) with plans `free / starter / pro / business / enterprise` and `PLAN_RUN_LIMITS`.
- Auth is Clerk (JWT, RS256 primary + HS256 fallback).
- Secrets live in **AWS Secrets Manager** (ap-south-1). No env-var secrets in prod.
- API keys already exist (`ApiKey` model) — licensing is a **separate** concern.

---

## 2. Open questions (BLOCKING Phase 1)

These cannot be resolved from code — user must decide.

### Q1. Deployment target — critical

CLAUDE.md describes Tenzo as hosted SaaS (Vercel + AWS). In that model, the server *is* the license validator, so offline-signed tokens and heartbeats are unnecessary — a simple `tenant.license_status` column gives the same guarantees, cheaper and simpler.

The hybrid model only justifies its complexity if **at least one** of the following is true:

- [ ] Tenzo will be distributed as a **desktop app / self-hosted container** to customers (code runs outside our trust boundary).
- [ ] A **worker/scraper agent** will run on customer premises (e.g. to keep scraping bandwidth on their side).
- [ ] We want to **pre-sell license keys** (e.g. via resellers) and have customers redeem them without our server being in the loop at sale time.
- [ ] We anticipate offline/air-gapped enterprise deals.

**Decision required:** confirm which of the above apply. If *none*, we should abandon the hybrid plan and build the simpler SaaS-entitlement variant instead.

Working assumption until answered: **hybrid is warranted** (the plan you approved).

### Q2. License subject

What does a license bind to?

- [ ] **Per-tenant** (recommended — matches existing `tenant_id` + `subscriptions` model, one key per workspace)
- [ ] Per-user
- [ ] Per-device / per-install (desktop-app scenario)

Working assumption: per-tenant.

### Q3. Client OS targets (only relevant if Q1 includes desktop/self-hosted)

- [ ] Windows (registry `MachineGuid`)
- [ ] Linux (`/etc/machine-id`)
- [ ] macOS (`IOPlatformUUID`)

Working assumption: all three, behind a `platform_fingerprint.py` abstraction.

### Q4. Feature-flag scheme — reuse or parallel?

Option A — **reuse plans**: license carries `plan: starter|pro|…` and all feature gates read from existing `PLAN_RUN_LIMITS` and a new `PLAN_FEATURES` map.

Option B — **parallel**: license carries a free-form `features: jsonb` and plans become irrelevant for gating.

Working assumption: **Option A**. Fewer sources of truth, reuses tested code. Billing stays on Stripe/subscriptions; licensing just asserts "this tenant is authorized to use plan X until Y".

### Q5. Issuance trigger

- [ ] **Automatic** on Stripe webhook (subscription activated → license minted)
- [ ] **Manual** by admin in an internal console
- [ ] **Both** (Stripe auto-mints, admin can override/extend/revoke)

Working assumption: **Both**. Stripe is the default path; admin console handles comp accounts, extensions, trials, and incident response.

### Q6. Revocation latency SLA

How fast must a revoked license stop working?

- [ ] **Instant** (< 60s) — requires online check on the hot path
- [ ] **Near-real-time** (< 5 min) — Redis revocation cache, current plan
- [ ] **Eventual** (< 6 h) — wait for next heartbeat

Working assumption: **< 5 min**. Matches the hybrid plan's Redis `revoked_license_ids` cache.

---

## 3. Locked decisions

### 3.1 Grace period and heartbeat cadence — **LOCKED**

| Parameter | Value |
|---|---|
| `heartbeat_interval` | **6 hours** |
| `soft_grace` | **3 days** — warning banner in UI; full functionality |
| `hard_grace` | **14 days** — access denied, read-only state |
| Clock skew allowance | **5 minutes** on `exp` / `nbf` |

**Rationale:** 6h keeps load on the license server trivial (4 calls/tenant/day). 3d soft grace handles weekend outages without bothering users. 14d hard grace survives a long outage but defeats "firewall the license server forever" piracy. Configurable via env vars so we can tighten later.

### 3.2 Token lifetime — **LOCKED**

Signed license token (PASETO) validity: `min(30 days, license.expires_at - now)`.

Refreshed on every successful heartbeat, so under normal operation the token is always ≤ 24h old. This limits the damage window if a token is exfiltrated.

### 3.3 Signing algorithm — **LOCKED**

**Ed25519** via **PASETO v4.public** (library: `pyseto>=1.7`).

Rejected alternatives:
- **JWT/JOSE** — too many footguns (`alg=none`, algorithm confusion). `python-jose` already in the project but we will not use it for license tokens.
- **RSA** — larger signatures, slower, no benefit here.
- **HMAC (symmetric)** — client binary would leak the signing key; anyone could forge licenses.

### 3.4 Key storage and rotation — **LOCKED**

| Item | Location | Notes |
|---|---|---|
| Private signing key | AWS Secrets Manager (ap-south-1), secret name `tenzo/licensing/signing_key_v1` | Accessed only by admin API service role via IAM |
| Public verifying key | Checked into repo at `packages/licensing/keys/signing_public_v1.pem` | Safe to distribute; embedded in any future desktop client |
| Key ID (`kid`) | `v1` → `v2` on rotation | Token header carries `kid`; verifier selects the right public key |
| Rotation policy | **Annual, or on compromise** | Runbook required before Phase 7 ships |
| Backup | Sealed envelope in a physical safe + second Secrets Manager entry in a different account | Losing the private key = catastrophic; cannot sign new tokens or re-verify existing ones without rollover |

Env var names (added to `.env.example` in Phase 2):
- `LICENSE_SIGNING_KEY_SECRET_ID=tenzo/licensing/signing_key_v1`
- `LICENSE_PUBLIC_KEY_PATH=/app/keys/signing_public_v1.pem`
- `LICENSE_ACTIVE_KID=v1`

### 3.5 Human-facing key format — **LOCKED**

```
TNZO-XXXXX-XXXXX-XXXXX-XXXXX
```

- Prefix `TNZO-` (static, identifies product — useful for support triage)
- 4 groups × 5 chars = 20 significant characters
- **Crockford base32** alphabet (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`) — excludes `I L O U` to prevent OCR / typo ambiguity
- **Last group is a CRC-16** of the first three, base32-encoded — client-side validation catches typos before any server round-trip
- Total entropy: 15 chars × 5 bits = **75 bits** (plenty for a non-secret identifier; real security is the Ed25519 signature, not this string)
- **Case-insensitive** on input; stored uppercase

Example (illustrative only): `TNZO-K3H8P-QR7MW-2N9XT-BC4FZ`

### 3.6 Fingerprint recipe — **LOCKED (pending Q1, Q3)**

**For hosted SaaS (default if Q1 = SaaS-only):**
```
fingerprint = sha256(tenant_id || clerk_org_id || installation_salt)
```
There is no "device" in this model; the fingerprint is a constant per tenant and only exists to keep the same token schema as the desktop case.

**For desktop / self-hosted (if Q1 includes it):**
```
fingerprint = sha256(
    machine_id            # OS-specific: MachineGuid / /etc/machine-id / IOPlatformUUID
    || primary_mac        # First non-virtual NIC, lowercased, no separators
    || cpu_vendor_id      # CPUID leaf 0 (stable across reboots)
    || license_salt       # From license payload — prevents cross-license fingerprint reuse
)
```
Stability handling: weighted match — if 2 of 3 hardware components still match on reactivation, treat as the same device (NIC swaps happen). Implemented in Phase 4.

### 3.7 Admin identity and access — **LOCKED**

Admin endpoints (`/admin/licenses/*`) require **all** of:
1. Valid Clerk JWT
2. Custom Clerk claim `role=tenzo_admin` (configured in Clerk dashboard per user)
3. Source IP in `ADMIN_IP_ALLOWLIST` (CIDR list env var)
4. 2FA enforced on the admin's Clerk account (checked via Clerk claim `two_factor_enabled=true`)

Every mutation writes to `admin_audit_log` (admin_id, action, target, payload, created_at, ip).

No separate admin user store. No service accounts with admin rights.

---

## 4. Library and code-layout decisions — **LOCKED**

| Concern | Choice | Rationale |
|---|---|---|
| PASETO | `pyseto>=1.7` | Actively maintained, pure-python fallback + cryptography-backed fast path |
| Ed25519 primitives | `cryptography>=42` (already in `python-jose[cryptography]` tree) | No new system deps |
| Package location | `project/packages/licensing/` (new) | Peer to `db-models`, importable by `api` and `worker` |
| Public-key artifact | `project/packages/licensing/keys/signing_public_v1.pem` | Checked in; sibling-file lookup by `kid` |
| Admin router | `project/apps/api/src/routers/admin_licenses.py` | Follows existing router pattern |
| Activation / heartbeat router | `project/apps/api/src/routers/license.py` | Public (activate) + authenticated (heartbeat) endpoints |
| Migration | `project/apps/api/alembic/versions/NNNN_licensing.py` | Standard Alembic, single migration for all licensing tables |
| Admin UI | `project/apps/web/app/admin/licenses/` | Mirrors existing `/app` structure; role-gated |

---

## 5. Deferred / explicitly out of scope for launch

These are *intentionally* not in scope for Phases 1–8. Revisit when real signal demands it.

- **Hardware HSM** for the signing key — Secrets Manager + KMS envelope is sufficient until we clear ₹50L/yr revenue or take an enterprise deal that mandates it.
- **Multi-region signing key replication** — single-region (ap-south-1) acceptable given the SLA; DR is backup-restore, not active-active.
- **Scheduled key rotation automation** — manual runbook is fine for v1; automate after we've rotated once in anger.
- **Usage-based dynamic pricing** — out of scope; licensing caps are hard limits only.
- **License transfer between tenants** — no UX, no API. Admin manually revokes and reissues.
- **SSO-coupled license provisioning** — Phase 5 item in CLAUDE.md; revisit then.

---

## 6. Risks acknowledged

| Risk | Likelihood | Mitigation | Owner |
|---|---|---|---|
| Private key loss | Low | Sealed-envelope backup + dual-account Secrets Manager copy | Admin |
| Mass clock skew on clients | Medium (desktop only) | 5-min leeway + server-returned `now` in heartbeat response | Phase 5 |
| False-positive fingerprint churn | Medium (desktop only) | 2-of-3 weighted match + admin "release slot" button before GA | Phase 3, 4 |
| License server outage denies all customers | Low | 3d soft grace = warning only; engineering SLA must keep outage < 3d | Ops |
| Legitimate users brute-forced by stolen keys | Low | Rate limit activation (5/min/IP, 10/day/key-hash) + alert on unusual churn | Phase 4, 7 |
| Stripe → license sync drift | Medium | Reconciliation job (nightly) compares `subscriptions.status` to `licenses.status` and alerts on mismatch | Phase 8 |

---

## 7. Acceptance criteria for Phase 0

Phase 0 is **done** when:

- [ ] User confirms or overrides each §2 open question (Q1–Q6).
- [ ] This document is committed with §2 answers filled in (checkboxes ticked, working assumptions promoted or replaced).
- [ ] A single-line summary is added to `.claude/CLAUDE.md` under a new "Licensing" heading, pointing here.
- [ ] A calendar reminder is set for the first annual key rotation (1 year after Phase 1 ships).

---

## 8. Change log

| Date | Change | Author |
|---|---|---|
| 2026-04-22 | Initial draft — Phase 0 locked decisions + open questions | claude-opus-4-7 |
