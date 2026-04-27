# Tenzo Licensing — Key Rotation Runbook

| | |
|---|---|
| **When to use** | Annually, or immediately if the active signing key is suspected compromised |
| **Estimated duration** | 30 min rollout + 48 h observation |
| **Blast radius** | Existing signed license tokens remain valid until their `exp` under the old `kid`. No reactivation required by customers. |
| **Reversibility** | Full — keep the old key's secret and PEM checked in until every outstanding token has expired |

---

## 1. Mental model

Every token carries a `kid` (key ID) in its PASETO footer. Verifiers pick the matching public key by `kid`. As long as:

1. The **new** private key is available to the signer (`license_signer.py`),
2. **Both** old and new public keys are present in the verifier's keyset (`license_enforcement.py::_get_public_keys`),

…rotation is seamless. Newly-minted tokens use the new `kid`; tokens signed under the old `kid` keep verifying until they naturally expire (up to 30 days).

The environment variable that controls which key the signer uses is `LICENSE_ACTIVE_KID`. Flipping this flag is the rotation trigger.

---

## 2. Before you start

- [ ] Confirm current active `kid` (check `LICENSE_ACTIVE_KID` in prod env or in [docker-compose.yml](../../docker-compose.yml))
- [ ] Confirm you have admin access to **AWS Secrets Manager** (`tenzo/licensing/signing_key_*`)
- [ ] Confirm the existing public key is in git at `packages/licensing/keys/signing_public_<kid>.pem`
- [ ] Confirm a staging environment exists and has an independent key
- [ ] Schedule a 2-day observation window afterwards — someone checks `license_activations_total{result="SIGNING_FAILED"}` daily

---

## 3. Generate the new keypair (staging first)

Run locally on the host that has `tenzo-licensing` installed:

```bash
python -m tenzo_licensing.scripts.generate_keypair --kid v2 --out-dir ./tmp-keys
```

This produces:

```
tmp-keys/signing_private_v2.pem   # mode 0600 — NEVER commit
tmp-keys/signing_public_v2.pem    # safe to commit
```

**Verify the pair is usable** before going further — Phase 1's round-trip test does this explicitly. From the repo root:

```bash
python -c "
from pathlib import Path
from tenzo_licensing import (
    load_private_key, load_public_key, sign_license, verify_license,
    LicensePayload, DeviceBindingMode,
)
import secrets
from datetime import datetime, timedelta, timezone

priv = load_private_key('v2', Path('tmp-keys/signing_private_v2.pem').read_bytes())
pub  = load_public_key('v2',  Path('tmp-keys/signing_public_v2.pem').read_bytes())
now = datetime.now(timezone.utc)
p = LicensePayload(
    lic_id='test', tenant_id='test', plan='pro',
    issued_at=now, not_before=now, expires_at=now+timedelta(days=30),
    device_binding_mode=DeviceBindingMode.HWID,
    fingerprint_salt=secrets.token_hex(16), nonce=secrets.token_hex(16),
)
tok = sign_license(p, priv)
restored = verify_license(tok, {'v2': pub})
assert restored == p
print('OK — v2 keypair round-trip verified')
"
```

If this fails, stop. Do not proceed.

---

## 4. Upload the new private key to Secrets Manager

```bash
aws secretsmanager create-secret \
  --region ap-south-1 \
  --name tenzo/licensing/signing_key_v2 \
  --secret-binary fileb://tmp-keys/signing_private_v2.pem
```

Verify access from a role the API service uses:

```bash
aws secretsmanager get-secret-value \
  --region ap-south-1 \
  --secret-id tenzo/licensing/signing_key_v2 \
  | jq -r '.SecretBinary' | base64 -d | head -c 30
```

Should print `-----BEGIN PRIVATE KEY-----`.

---

## 5. Commit the new public key

```bash
cp tmp-keys/signing_public_v2.pem project/packages/licensing/keys/
git add project/packages/licensing/keys/signing_public_v2.pem
git commit -m "licensing: add signing public key v2 (key rotation prep)"
```

**Do not delete `signing_public_v1.pem`.** It must remain until every token signed under v1 has expired (≤ 30 days after the flip).

---

## 6. Deploy: verifier first, signer second

This order is non-negotiable. If you flip the signer to v2 before verifiers know about v2, every newly-minted token will be rejected with `UnknownKeyIdError`.

### 6.1 Code change — teach verifiers about v2

Edit `apps/api/src/services/license_enforcement.py::_get_public_keys` to load **both** keys. The current implementation only loads the active kid; broaden it:

```python
def _get_public_keys() -> dict[str, PublicKey]:
    global _public_keys
    if not _public_keys:
        # Load every keys/signing_public_*.pem we find alongside the active one
        base = Path(settings.license_public_key_path).parent
        for p in sorted(base.glob("signing_public_*.pem")):
            kid = p.stem.replace("signing_public_", "")
            try:
                _public_keys[kid] = load_public_key_from_file(kid, p)
            except Exception as exc:
                logger.error(
                    "license_enforcement.public_key_load_failed",
                    path=str(p), error=str(exc),
                )
    return _public_keys
```

Deploy and restart the API. **Do not** change `LICENSE_ACTIVE_KID` yet — signer still uses v1.

Verify: hit `/openapi.json`, no regressions, a fresh activation still works (v1-signed tokens verify under v1).

### 6.2 Flip the signer to v2

Update env on all API instances:

```
LICENSE_ACTIVE_KID=v2
LICENSE_PRIVATE_KEY_PATH=  # blank in prod — forces Secrets Manager
LICENSE_SIGNING_KEY_SECRET_ID=tenzo/licensing/signing_key_v2
```

Restart the API. Check logs for one of:

```
license_signer.load_from_secrets_manager  secret_id=tenzo/licensing/signing_key_v2 kid=v2
license_signer.load_from_disk             kid=v2           # if using local path
```

### 6.3 Confirm live behaviour

Freshly-activated tokens should now decode by peeking at the footer:

```bash
TOKEN=$(curl -s -X POST https://api.yourdomain/api/license/activate \
  -H 'Content-Type: application/json' \
  -d '{"key":"TNZO-...","fingerprint":"..."}' | jq -r .token)

echo "$TOKEN" | awk -F. '{print $4}' | base64 -d 2>/dev/null
# expected: {"kid":"v2"}
```

Watch `tenzo_license_activations_total{result="success"}` — should continue climbing.

---

## 7. Grace period (≤ 30 days)

**Keep v1 running** for the full token lifetime (`LICENSE_TOKEN_TTL_SECONDS`, default 30 days). During this period:

- v1 tokens: verify fine (public key still loaded).
- v2 tokens: verify fine (both public keys loaded; signer produces v2).

Monitor:

- `tenzo_license_activations_total{result="TOKEN_INVALID"}` — should **not** spike. If it does, a verifier is missing v2 or v1 was prematurely removed.
- `tenzo_license_heartbeats_total` — clients should gradually upgrade to v2 tokens as they heartbeat.

After 30 days + 1 day safety buffer, every outstanding token will have naturally expired.

---

## 8. Retire the old key

Only after the full grace period:

### 8.1 Remove v1 public key from repo

```bash
git rm project/packages/licensing/keys/signing_public_v1.pem
git commit -m "licensing: remove retired signing public key v1"
```

Deploy the API. Verifiers now only know about v2.

### 8.2 Archive the v1 private key

Do **not** delete from Secrets Manager yet — move it to cold storage:

```bash
# Export, encrypt, store in a safe offline location (compliance needs)
aws secretsmanager get-secret-value \
  --region ap-south-1 \
  --secret-id tenzo/licensing/signing_key_v1 \
  | jq -r '.SecretBinary' | base64 -d \
  > archive/signing_key_v1-$(date +%F).pem
gpg --encrypt --recipient security@yourcompany archive/signing_key_v1-*.pem

# Then purge from Secrets Manager
aws secretsmanager delete-secret \
  --region ap-south-1 \
  --secret-id tenzo/licensing/signing_key_v1 \
  --recovery-window-in-days 30
```

### 8.3 Update documentation

- Bump `LICENSE_ACTIVE_KID=v2` in `.env.example` and `docker-compose.yml`
- Edit [phase-0-decisions.md §3.4](phase-0-decisions.md) — update active key references
- Edit [STATUS.md](STATUS.md) — note the rotation date under "Change log"

---

## 9. Emergency rotation (compromise suspected)

Same steps 3-6 but:

1. **Step 5 is replaced by an admin bulk-revoke**: mass-call `POST /api/admin/licenses/{id}/revoke` for every license issued under the old kid. The revocation cache will catch them instantly; next heartbeat rejects them; clients must re-activate to get a v2 token.

   Query to get the list:
   ```sql
   SELECT id FROM licenses WHERE signing_kid = 'v1' AND status = 'active';
   ```

2. **Do NOT wait 30 days for grace period.** After the bulk revoke + v2 flip, treat v1 as burned — immediately remove the v1 public key from the verifier (step 8.1) and rotate its secret in Secrets Manager.

3. **Communicate**: every tenant whose license was revoked needs to re-activate. Email them the same plaintext key — a re-activate from the new v2 signer path will just mint them a new token under the new kid.

---

## 10. Dry-run checklist (annual practice)

Once a year, even if you don't need to rotate in anger:

- [ ] Generate a `v-dryrun` keypair
- [ ] Upload to `tenzo/licensing/signing_key_v-dryrun`
- [ ] Commit the public key
- [ ] Deploy the verifier-broaden change (step 6.1)
- [ ] Do **not** flip `LICENSE_ACTIVE_KID` — just confirm the verifier loads both keys cleanly
- [ ] Let it run for 24 h, watch metrics
- [ ] Revert: `git revert` the public-key commit, delete the Secrets Manager entry
- [ ] Write a one-page "this went wrong" note if anything did, filed under `docs/licensing/retros/`
