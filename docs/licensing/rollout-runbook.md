# Tenzo Licensing — Rollout Runbook

| | |
|---|---|
| **Purpose** | Day-by-day instructions for rolling out Phases 1-7 from shipped-but-inert (`off`) to fully enforced (`enforce` + hard-grace) |
| **Total duration** | ~3 weeks calendar time. Code changes: ~2 hours total across the three flips |
| **Rollback path** | At any point, set `LICENSING_MODE=off` in env + redeploy. Every route goes back to bypass. Takes ~1 minute. |
| **Owner** | Whoever is on-call for the rollout window |

---

## 0. Before you start

### Read once

- [phase-0-decisions.md](phase-0-decisions.md) — what's locked and why
- [STATUS.md](STATUS.md) — what's built; §4 cross-cutting deferred work
- [key-rotation-runbook.md](key-rotation-runbook.md) — not relevant to this rollout but you should know where it lives

### Confirm prerequisites

- [ ] Phases 1-7 deployed to production with `LICENSING_MODE=off`
- [ ] Alembic at `007_admin_audit_clerk_compat`
- [ ] Ed25519 production keypair generated and the private key uploaded to AWS Secrets Manager (`tenzo/licensing/signing_key_v1`)
- [ ] Production public key committed under `packages/licensing/keys/signing_public_v1.pem`
- [ ] Prometheus is scraping `/metrics` and dashboards are visible
- [ ] Someone can reach you if things go wrong (escalation path defined)

### Freeze window

- No unrelated releases during the rollout week.
- No Stripe plan changes (new plans added / pricing changes) during the rollout.
- No major customer-facing UI changes.

---

## Day 0 — Ship (already done)

Phases 1-7 are live in prod behind `LICENSING_MODE=off`.

**What to verify:**

```bash
# From a prod-shell with access to the cluster:
docker exec gem-tender-api python /app/scripts/preflight_licensing.py
```

Expected: `PASSED — licensing infrastructure is ready.` or with warnings only (no failures). If `FAILED`, fix before proceeding. See §8 for common issues.

**Watch for 24 h:** no new 5xx errors on existing routes, no drop in successful requests, `/metrics` scraping cleanly, no unexpected `tenzo_license_enforcement_checks_total{mode="off"}` traffic if anything is off.

---

## Day 1 — Grandfather existing tenants

Every tenant that exists today needs a license so they don't break on Day 2 (when `warn` starts logging) or Day 8 (when `enforce` starts denying).

### 1.1 Dry-run first

```bash
docker exec gem-tender-api python /app/scripts/grandfather_licenses.py --dry-run
```

Output: CSV header + one row per tenant that *would* be minted, plus a summary to stderr. **Sanity-check the tenant count** against your own tenant-count dashboard. If wildly off, stop — the script might be reading the wrong DB.

### 1.2 Run for real

```bash
docker exec gem-tender-api python /app/scripts/grandfather_licenses.py \
  --plan pro \
  --expires-days 365 \
  --max-devices 5 \
  --output /tmp/grandfather-$(date +%F).csv
docker cp gem-tender-api:/tmp/grandfather-$(date +%F).csv ./grandfather-$(date +%F).csv
```

The CSV has `tenant_id, plan, raw_key, expires_at, result`. **Treat it as a secret** — each `raw_key` is the plaintext license key and will never be retrievable again.

### 1.3 Verify

```bash
# Count tenants with active licenses — should equal total tenant count
docker exec gem-tender-db psql -U gem -d gem_tender -c \
  "SELECT count(distinct tenant_id) FROM licenses WHERE status='active';"

# Re-run preflight
docker exec gem-tender-api python /app/scripts/preflight_licensing.py
```

Expected: `uncovered tenants: 0`.

### 1.4 Distribute keys

Email each tenant's billing contact their `raw_key`. Template suggestion:

> *Subject: Tenzo — your license key*
>
> Hi — we're rolling out a license-key layer to Tenzo. You don't need to do anything today, but in a few days your workspace will start using this key. Please store it with your other secrets: `TNZO-XXXXX-XXXXX-XXXXX-XXXXX`. We'll never ask for it over email or phone.

### 1.5 Delete the CSV

After emailing:

```bash
# Overwrite with random bytes before deleting
shred --remove ./grandfather-$(date +%F).csv
docker exec gem-tender-api rm /tmp/grandfather-$(date +%F).csv
```

---

## Day 2 — Flip to `warn`

`warn` mode logs denials to structured logs and increments `tenzo_license_enforcement_checks_total{result="deny_*"}` but continues serving. This is your telemetry reveal — you find out what would have broken *without* breaking anything.

### 2.1 Update env

```bash
# In docker-compose.yml or your prod env config:
LICENSING_MODE: "warn"
```

### 2.2 Redeploy API + restart worker

```bash
cd project
docker compose up -d --force-recreate api worker celery-beat
```

### 2.3 Verify

```bash
# Metrics should show enforcement_checks_total{mode="warn"} climbing
curl -s http://localhost:8000/metrics | grep enforcement_checks_total

# No increase in 402s — warn should never deny
docker logs gem-tender-api --tail 100 | grep "402"  # expect empty or nothing new
```

### 2.4 Watch for 5 days

Daily during this window, check:

```bash
# How many denials would have happened today?
docker logs gem-tender-api --since 24h | grep -c "license.*_warn"

# Which kinds?
docker logs gem-tender-api --since 24h \
  | grep "license" | grep "warn" \
  | sed 's/.*"event": "\([^"]*\)".*/\1/' | sort | uniq -c
```

**What you expect:**

- `license.no_active_license_warn` → 0 (grandfathering should have covered everyone)
- `license.feature_not_licensed_warn` → tenants hitting features above their plan. Small numbers are normal; huge numbers mean your PLAN_FEATURES map is too tight.
- `license.usage_limit_exceeded_warn` → tenants hitting caps. If grandfathered everyone on pro, expect zero.
- `license.expired_warn` → 0 (grandfather gave 365-day expiry).

**If `no_active_license_warn` > 0:** some tenant sneaked in between the script and the flip. Run grandfather again, it's idempotent.

**If any denial kind is spiking unexpectedly:** do NOT proceed. Roll back to `off`, diagnose, fix, re-flip to `warn`.

---

## Day 8 — Flip to `enforce` for NEW tenants only

**We don't have a built-in "new tenants only" flag.** In practice you have three options, listed in order of safety:

### Option A (recommended) — just flip everything at Day 14

If `warn` has been clean for a week, you can skip straight to Day 14. "New tenants only" is a belt-and-suspenders risk-reduction that mostly matters when you weren't sure about the `warn` data. If Day 2-7 was silent, your confidence is high.

### Option B — manual new-tenant gating

Add a temporary env var allowlist:

```
LICENSING_ENFORCE_EXEMPT_TENANTS=tenant_uuid_1,tenant_uuid_2,...
```

Populate with the IDs of all tenants that existed at Day 0. Then flip `LICENSING_MODE=enforce`. The exempt list bypasses. New tenants (not in the list) get enforced.

This isn't built — if you need it, add a check at the top of `require_valid_license`:

```python
if user.tenant_id in settings.licensing_enforce_exempt_tenants:
    return LicenseGuard.unrestricted(user.tenant_id)
```

Quick (~30 min) code change plus a deploy. Remove the list on Day 14.

### Option C — rollout cohorts via tenant-ID hashing

Deterministic cohort selection: `hash(tenant_id) % 10 < N`. Bump `N` from 1→10 over days. Requires code — skip unless you have a 1000+ tenant population.

**Recommendation:** Option A. Most teams of Tenzo's size don't need the complexity of B or C.

---

## Day 14 — Flip to `enforce` for all tenants

### 14.1 Final preflight

```bash
docker exec gem-tender-api python /app/scripts/preflight_licensing.py
```

Must report `PASSED` with zero failures and zero critical warnings.

### 14.2 Flip env

```yaml
LICENSING_MODE: "enforce"
```

### 14.3 Redeploy

```bash
docker compose up -d --force-recreate api worker celery-beat
```

### 14.4 Watch closely for 30 minutes

- `tenzo_license_enforcement_checks_total{mode="enforce",result="deny_no_license"}` — if non-zero, someone fell through the crack. Emergency-mint a license via the admin endpoint or the grandfather script.
- 402 responses on `/api/jobs`, `/api/tenders`, `/api/exports` — should be either zero or expected (tenant's plan really doesn't include the feature).
- 429 responses — tenants hitting usage caps. If a paying customer is getting 429'd, raise their license's `features.max_runs_per_month` via the admin API.

### 14.5 Rollback if needed

One-liner:

```bash
# In prod env: set LICENSING_MODE=off, redeploy.
# Everything goes back to Phase 0 bypass mode within ~1 minute.
docker compose up -d --force-recreate api
```

Nothing is lost. License rows stay. Audit rows stay. Metrics keep flowing. Next `warn`/`enforce` flip picks up where this one left off.

---

## Day 21 — Enable hard-grace denial

This step **only matters if you distribute a client app** that holds a signed token (Model B — desktop/agent). For hosted SaaS (Clerk-authenticated web users), there is nothing to enable — `require_valid_license` already does a fresh DB check on every request.

Skipping if hosted SaaS only.

For Model B: the heartbeat response includes `server_now` so the client can reset its grace clock to authoritative time. Client code enforces:

- `last_successful_heartbeat > 14 days ago` → refuse to operate.

This is enforced in the **client app's code**, not the server. Coordinate with whoever owns the client binary / desktop app.

---

## Day 365 — First annual key rotation

See [key-rotation-runbook.md](key-rotation-runbook.md).

Set a calendar reminder now — rotation is painless if planned, painful if done in emergency mode.

---

## Observability during the rollout

### Dashboards to watch

| Panel | Alert if… |
|---|---|
| `tenzo_license_activations_total{result="success"}` | stops climbing during business hours |
| `tenzo_license_activations_total{result!="success"}` | sum over 5 min > normal baseline × 3 |
| `tenzo_license_heartbeats_total{result!="success"}` | > 5% of total heartbeats over 15 min |
| `tenzo_license_enforcement_checks_total{result="deny_no_license"}` | > 0 in enforce mode (grandfathering gap) |
| `tenzo_license_enforcement_checks_total{result="deny_expired"}` | > 0 on Day 14 (grandfather expiry too short) |
| `rate(tenzo_license_activation_duration_seconds_sum[5m]) / rate(..._count[5m])` | > 1 second avg |
| `tenzo_license_feature_denials_total` | spike after a deploy → someone shipped a route gated on a feature wrong plans don't have |

### Structured logs to grep

```bash
# Find every denied request with its tenant and reason
docker logs gem-tender-api --since 1h \
  | grep "license" | grep -E "warn|deny" \
  | jq -c '{event, tenant_id, license_id, reason, plan}'
```

---

## Common issues & fixes

### "preflight says public key missing"

The public key needs to be at `settings.license_public_key_path` inside the container. In dev that's `/keys/signing_public_v1.pem` from the `data/keys` bind mount. In prod, make sure the Dockerfile copies the committed public key into the image:

```dockerfile
COPY packages/licensing/keys /keys
```

### "grandfather script says 0 tenants"

Some deployments key `tenant_id` off of Clerk `org_id`, which may be empty for single-user workspaces. The script filters `WHERE tenant_id IS NOT NULL` — if nobody has a tenant_id, there's nothing to grandfather. Confirm your auth flow populates `User.tenant_id` on signup.

### "enforce flip caused a surge of 402s"

Roll back to `off` immediately, then:

1. Re-run preflight → look at the **tenant coverage** section. If `uncovered > 0`, the grandfather run missed somebody.
2. Re-run grandfather_licenses.py. It's idempotent.
3. Check if LICENSE_ACTIVE_KID was changed during the rollout — if yes, existing tokens under the old kid don't verify. Keep the old kid active during rotation (see key-rotation-runbook).
4. Flip back to `enforce`.

### "usage-cap denials are spiking"

Either your plan ceilings are too tight (adjust `PLAN_FEATURES` in `license_features.py`) or a specific tenant's usage exploded. For the latter, raise that tenant's ceiling via the admin API:

```bash
# Bump max_runs_per_month for one license:
# (requires an admin endpoint that mutates features.jsonb — deferred, see §4 of STATUS.md)

# Workaround: direct SQL
docker exec gem-tender-db psql -U gem -d gem_tender -c "
  UPDATE licenses
  SET features = features || '{\"max_runs_per_month\": 5000}'::jsonb
  WHERE tenant_id = 'tenant_xyz';
"
```

Then clear the revocation cache (not strictly necessary, but keeps the cache tidy):

```bash
docker exec gem-tender-redis redis-cli DEL license:revoked
# The next cache-refresh beat tick rebuilds it from DB truth.
```

### "heartbeat endpoint returning 500"

Check `tenzo_license_activations_total{result="SIGNING_FAILED"}` (it also covers heartbeats in the shared signer). If climbing, the signer's private key is unreachable. Check Secrets Manager permissions and the IAM role attached to the API.

---

## Closeout

After Day 21 (or Day 14 for SaaS-only):

- [ ] Remove any `LICENSING_ENFORCE_EXEMPT_TENANTS` allowlist added as part of Option B
- [ ] Update [STATUS.md](STATUS.md) §6 "current rollout mode" from `off` to `enforce`
- [ ] File a retro: how long it actually took, what surprised you, what to change for the next rollout
- [ ] Set the Day-365 calendar reminder for key rotation
