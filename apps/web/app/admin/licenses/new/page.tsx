"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const API = "/api-backend";

type MintResponse = {
  license: {
    id: number;
    tenant_id: string;
    plan: string;
    status: string;
    key_prefix: string;
    expires_at: string;
    max_devices: number;
  };
  raw_key: string;
};

function isoAtStartOfDay(dateStr: string): string {
  // dateStr is YYYY-MM-DD — convert to UTC ISO
  return new Date(dateStr + "T00:00:00.000Z").toISOString();
}

const DEFAULT_FEATURES: Record<string, Record<string, unknown>> = {
  free: { max_runs_per_month: 3 },
  starter: { max_runs_per_month: 30, export_xlsx: true },
  pro: { max_runs_per_month: 150, export_xlsx: true, ai_summaries: true },
  business: { max_runs_per_month: 600, export_xlsx: true, ai_summaries: true, webhooks: true },
  enterprise: { max_runs_per_month: null, export_xlsx: true, ai_summaries: true, webhooks: true },
};

export default function NewLicensePage() {
  const { getToken } = useAuth();
  const router = useRouter();

  const defaultExpires = (() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() + 1);
    return d.toISOString().slice(0, 10);
  })();

  const [tenantId, setTenantId] = useState("");
  const [plan, setPlan] = useState("pro");
  const [expiresAt, setExpiresAt] = useState(defaultExpires);
  const [maxDevices, setMaxDevices] = useState(3);
  const [notes, setNotes] = useState("");
  const [featuresJson, setFeaturesJson] = useState(
    JSON.stringify(DEFAULT_FEATURES.pro, null, 2)
  );

  const [minting, setMinting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MintResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Sync features JSON when plan changes
  function onPlanChange(p: string) {
    setPlan(p);
    setFeaturesJson(JSON.stringify(DEFAULT_FEATURES[p] ?? {}, null, 2));
  }

  async function mint() {
    setError(null);
    if (!tenantId.trim()) { setError("Tenant ID is required."); return; }
    if (maxDevices < 1 || maxDevices > 1000) { setError("Max devices must be 1–1000."); return; }

    let features: Record<string, unknown> = {};
    if (featuresJson.trim()) {
      try { features = JSON.parse(featuresJson); }
      catch { setError("Features JSON is not valid."); return; }
    }

    setMinting(true);
    try {
      const token = await getToken();
      const res = await fetch(`${API}/api/admin/licenses`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tenant_id: tenantId.trim(),
          plan,
          expires_at: isoAtStartOfDay(expiresAt),
          max_devices: maxDevices,
          features,
          notes: notes.trim() || null,
        }),
      });
      if (res.status === 403) {
        setError(
          "403 — your user isn't admin on the backend. Set public_metadata.role='tenzo_admin' in Clerk, " +
          "or add your Clerk user_id to LOCAL_ADMIN_USER_IDS in docker-compose.yml."
        );
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(`Mint failed (HTTP ${res.status}): ${JSON.stringify(body)}`);
        return;
      }
      setResult(await res.json());
    } catch (e) {
      setError(`Network error: ${e}`);
    } finally {
      setMinting(false);
    }
  }

  async function copyKey() {
    if (!result?.raw_key) return;
    try {
      await navigator.clipboard.writeText(result.raw_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback — select the input
    }
  }

  // ── Success modal ─────────────────────────────────────────────────────
  if (result) {
    return (
      <div className="max-w-2xl space-y-6">
        <div
          className="card-surface p-6 space-y-5"
          style={{ borderColor: "rgba(52, 211, 153, 0.4)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center"
              style={{ background: "rgba(52, 211, 153, 0.16)", color: "#34D399" }}
            >
              ✓
            </div>
            <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              License minted
            </h1>
          </div>

          <div
            className="p-4 rounded-lg"
            style={{
              background: "rgba(251, 191, 36, 0.08)",
              border: "1px solid rgba(251, 191, 36, 0.4)",
            }}
          >
            <p className="text-xs font-mono font-semibold uppercase tracking-wider mb-2" style={{ color: "#FBBF24" }}>
              ⚠ Copy this key now. It will NEVER be shown again.
            </p>
            <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
              The database stores only the SHA-256 hash. If you lose this key, you must revoke the license and mint a new one.
            </p>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              Plaintext license key
            </label>
            <div className="flex gap-2">
              <input
                readOnly
                value={result.raw_key}
                onClick={(e) => (e.target as HTMLInputElement).select()}
                className="flex-1 text-sm px-4 py-3 rounded-lg font-mono outline-none tracking-wider"
                style={{
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border-bright)",
                  color: "var(--accent)",
                  letterSpacing: "0.08em",
                }}
              />
              <button
                onClick={copyKey}
                className="text-sm px-4 py-3 rounded-lg font-mono font-semibold transition-opacity"
                style={{
                  background: copied ? "#34D399" : "#F59E0B",
                  color: "#0F1117",
                  minWidth: "120px",
                }}
              >
                {copied ? "✓ Copied" : "Copy"}
              </button>
            </div>
          </div>

          <div
            className="text-xs space-y-2 p-4 rounded-lg"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
            }}
          >
            <div className="grid grid-cols-2 gap-2 font-mono" style={{ color: "var(--text-secondary)" }}>
              <div><span style={{ color: "var(--text-muted)" }}>License ID:</span> #{result.license.id}</div>
              <div><span style={{ color: "var(--text-muted)" }}>Plan:</span> {result.license.plan}</div>
              <div><span style={{ color: "var(--text-muted)" }}>Key prefix:</span> {result.license.key_prefix}</div>
              <div><span style={{ color: "var(--text-muted)" }}>Max devices:</span> {result.license.max_devices}</div>
              <div className="col-span-2"><span style={{ color: "var(--text-muted)" }}>Tenant:</span> {result.license.tenant_id}</div>
              <div className="col-span-2"><span style={{ color: "var(--text-muted)" }}>Expires:</span> {new Date(result.license.expires_at).toLocaleString("en-IN")}</div>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => router.push(`/admin/licenses/${result.license.id}`)}
              className="flex-1 text-sm px-4 py-2.5 rounded-lg font-mono transition-opacity"
              style={{
                background: "#F59E0B",
                color: "#0F1117",
                fontWeight: "600",
              }}
            >
              Open license detail
            </button>
            <Link
              href="/admin/licenses"
              className="flex-1 text-sm px-4 py-2.5 rounded-lg font-mono text-center transition-opacity"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-bright)",
                color: "var(--text-secondary)",
              }}
            >
              Back to list
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Form ─────────────────────────────────────────────────────────────
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <Link
          href="/admin/licenses"
          className="text-xs font-mono"
          style={{ color: "var(--text-muted)" }}
        >
          ← Licenses
        </Link>
        <h1 className="text-2xl font-bold tracking-tight mt-2" style={{ color: "var(--text-primary)" }}>
          Mint new license
        </h1>
        <p className="text-xs font-mono mt-1" style={{ color: "var(--text-muted)" }}>
          The plaintext key will be shown once after minting. The DB stores only its SHA-256 hash.
        </p>
      </div>

      {error && (
        <div
          className="card-surface p-4"
          style={{ borderColor: "rgba(248, 113, 113, 0.4)" }}
        >
          <p className="text-sm" style={{ color: "#F87171" }}>⚠ {error}</p>
        </div>
      )}

      <div className="card-surface p-6 space-y-5">
        <div>
          <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
            Tenant ID <span style={{ color: "#F87171" }}>*</span>
          </label>
          <input
            type="text"
            placeholder="e.g. 58850c01-67a5-4fad-bb63-ff2b03aa9694 or acme-corp"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="w-full text-sm px-4 py-2.5 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
          <p className="text-[10px] font-mono mt-1" style={{ color: "var(--text-muted)" }}>
            Must match the tenant_id the customer uses to sign in (Clerk org_id or local registration UUID).
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Plan
            </label>
            <select
              value={plan}
              onChange={(e) => onPlanChange(e.target.value)}
              className="w-full text-sm px-4 py-2.5 rounded-lg font-mono outline-none"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-bright)",
                color: "var(--text-primary)",
              }}
            >
              <option value="free">free</option>
              <option value="starter">starter</option>
              <option value="pro">pro</option>
              <option value="business">business</option>
              <option value="enterprise">enterprise</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
              Max devices
            </label>
            <input
              type="number"
              min={1}
              max={1000}
              value={maxDevices}
              onChange={(e) => setMaxDevices(parseInt(e.target.value, 10) || 1)}
              className="w-full text-sm px-4 py-2.5 rounded-lg font-mono outline-none"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-bright)",
                color: "var(--text-primary)",
              }}
            />
          </div>
        </div>

        <div>
          <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
            Expires at
          </label>
          <input
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            className="w-full text-sm px-4 py-2.5 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
        </div>

        <div>
          <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
            Features override (JSON)
          </label>
          <textarea
            value={featuresJson}
            onChange={(e) => setFeaturesJson(e.target.value)}
            rows={5}
            className="w-full text-xs px-3 py-2 rounded-lg font-mono outline-none resize-y"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
          <p className="text-[10px] font-mono mt-1" style={{ color: "var(--text-muted)" }}>
            Overrides the plan defaults. Leave as-is to use {plan}&apos;s defaults.
          </p>
        </div>

        <div>
          <label className="text-xs font-mono block mb-1.5" style={{ color: "var(--text-muted)" }}>
            Notes (optional, stored in audit log)
          </label>
          <input
            type="text"
            placeholder="e.g. Manual mint for customer X (contract #42)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={500}
            className="w-full text-sm px-4 py-2.5 rounded-lg outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={mint}
            disabled={minting}
            className="flex-1 text-sm px-5 py-3 rounded-lg font-semibold transition-opacity disabled:opacity-50 glow-amber"
            style={{ background: "#F59E0B", color: "#0F1117" }}
          >
            {minting ? "Minting…" : "▶ Mint license"}
          </button>
          <Link
            href="/admin/licenses"
            className="text-sm px-5 py-3 rounded-lg font-mono text-center transition-opacity"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-secondary)",
            }}
          >
            Cancel
          </Link>
        </div>
      </div>
    </div>
  );
}
