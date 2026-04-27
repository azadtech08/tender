"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const API = "/api-backend";

type License = {
  id: number;
  tenant_id: string;
  key_prefix: string;
  plan: string;
  status: "active" | "suspended" | "revoked" | "expired";
  signing_kid: string;
  not_before: string;
  expires_at: string;
  max_devices: number;
  features: Record<string, unknown>;
  issued_by_admin_id: number | null;
  revoked_at: string | null;
  revoked_reason: string | null;
  created_at: string;
  updated_at: string;
};

type DetailResponse = {
  license: License;
  device_count: number;
  active_device_count: number;
  activations_24h: number;
};

type DeviceRow = {
  id: number;
  license_id: number;
  fingerprint: string;
  hostname: string | null;
  platform: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_ip: string | null;
  revoked_at: string | null;
};

type ActivationRow = {
  id: number;
  license_id: number;
  fingerprint: string | null;
  event: "activate" | "heartbeat" | "deactivate" | "denied" | "revoked";
  reason: string | null;
  ip: string | null;
  created_at: string;
};

const STATUS_COLORS: Record<License["status"], string> = {
  active:    "#34D399",
  suspended: "#FBBF24",
  revoked:   "#F87171",
  expired:   "#9CA3AF",
};

const EVENT_COLORS: Record<ActivationRow["event"], string> = {
  activate:   "#34D399",
  heartbeat:  "#60A5FA",
  deactivate: "#9CA3AF",
  denied:     "#F87171",
  revoked:    "#F87171",
};

function fmt(s: string | null | undefined) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString("en-IN"); } catch { return s; }
}

export default function LicenseDetailPage() {
  const { getToken } = useAuth();
  const router = useRouter();
  const params = useParams();
  const id = Number(params?.id);

  const [detail, setDetail] = useState<DetailResponse | null>(null);
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [activations, setActivations] = useState<ActivationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function authHeaders() {
    const token = await getToken();
    return {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
  }

  async function fetchAll() {
    setLoading(true);
    setError(null);
    try {
      const headers = await authHeaders();
      const [d, dv, ac] = await Promise.all([
        fetch(`${API}/api/admin/licenses/${id}`, { headers }),
        fetch(`${API}/api/admin/licenses/${id}/devices`, { headers }),
        fetch(`${API}/api/admin/licenses/${id}/activations?limit=50`, { headers }),
      ]);
      if (!d.ok) {
        setError(`Failed to load license (HTTP ${d.status}).`);
        return;
      }
      setDetail(await d.json());
      if (dv.ok) setDevices(await dv.json());
      if (ac.ok) setActivations(await ac.json());
    } catch (e) {
      setError(`Network error: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchAll(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [id]);

  async function callAction(
    path: string,
    body: Record<string, unknown> = {},
    confirmMsg?: string,
  ) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API}/api/admin/licenses/${id}/${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        alert(`Action failed (HTTP ${res.status}): ${JSON.stringify(b)}`);
        return;
      }
      await fetchAll();
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    const reason = window.prompt("Reason for revoke (shown in audit log):", "");
    if (reason === null) return;
    await callAction("revoke", { reason: reason || null },
      "Revoke this license? This cannot be reversed — the customer must be re-issued a new key.");
  }

  async function suspend() {
    const reason = window.prompt("Reason for suspend:", "");
    if (reason === null) return;
    await callAction("suspend", { reason: reason || null });
  }

  async function reactivate() {
    await callAction("reactivate", {});
  }

  async function extend() {
    const currentISO = detail?.license.expires_at ?? new Date().toISOString();
    const defaultDate = new Date(currentISO);
    defaultDate.setFullYear(defaultDate.getFullYear() + 1);
    const input = window.prompt(
      "New expires_at (YYYY-MM-DD):",
      defaultDate.toISOString().slice(0, 10),
    );
    if (!input) return;
    const newIso = new Date(input + "T00:00:00.000Z").toISOString();
    const reason = window.prompt("Reason (optional):", "") ?? "";
    await callAction("extend", { new_expires_at: newIso, reason: reason || null });
  }

  async function revokeDevice(deviceId: number, fp: string) {
    if (!window.confirm(
      `Revoke device binding ${fp.slice(0, 16)}…?\n\nThe slot will be freed. The device's current token keeps working until it expires or the cache catches up.`,
    )) return;
    setBusy(true);
    try {
      const headers = await authHeaders();
      const res = await fetch(
        `${API}/api/admin/licenses/${id}/devices/${deviceId}/revoke`,
        { method: "POST", headers },
      );
      if (!res.ok) {
        alert(`Failed (HTTP ${res.status})`);
      } else {
        await fetchAll();
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-5xl">
        <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Loading…</p>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="max-w-5xl space-y-4">
        <Link href="/admin/licenses" className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          ← Licenses
        </Link>
        <div className="card-surface p-4" style={{ borderColor: "rgba(248, 113, 113, 0.4)" }}>
          <p className="text-sm" style={{ color: "#F87171" }}>⚠ {error ?? "License not found."}</p>
        </div>
      </div>
    );
  }

  const lic = detail.license;

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link href="/admin/licenses" className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          ← Licenses
        </Link>
        <div className="flex items-end justify-between mt-2">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-3" style={{ color: "var(--text-primary)" }}>
              License #{lic.id}
              <span
                className="text-[10px] px-2 py-0.5 rounded-full font-mono uppercase"
                style={{
                  color: STATUS_COLORS[lic.status],
                  background: `${STATUS_COLORS[lic.status]}22`,
                  border: `1px solid ${STATUS_COLORS[lic.status]}55`,
                }}
              >
                {lic.status}
              </span>
            </h1>
            <p className="text-xs font-mono mt-1" style={{ color: "var(--text-muted)" }}>
              {lic.key_prefix}… · {lic.plan} · {lic.tenant_id}
            </p>
          </div>
        </div>
      </div>

      {/* ── Actions row ── */}
      <div className="card-surface p-4 flex flex-wrap gap-2">
        {lic.status === "active" && (
          <>
            <button
              onClick={extend}
              disabled={busy}
              className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity disabled:opacity-50"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-bright)",
                color: "var(--text-primary)",
              }}
            >
              📅 Extend expiry
            </button>
            <button
              onClick={suspend}
              disabled={busy}
              className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity disabled:opacity-50"
              style={{
                background: "rgba(251, 191, 36, 0.12)",
                border: "1px solid rgba(251, 191, 36, 0.4)",
                color: "#FBBF24",
              }}
            >
              ⏸ Suspend
            </button>
            <button
              onClick={revoke}
              disabled={busy}
              className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity disabled:opacity-50 ml-auto"
              style={{
                background: "rgba(248, 113, 113, 0.12)",
                border: "1px solid rgba(248, 113, 113, 0.4)",
                color: "#F87171",
              }}
            >
              ⊘ Revoke
            </button>
          </>
        )}
        {lic.status === "suspended" && (
          <>
            <button
              onClick={reactivate}
              disabled={busy}
              className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity disabled:opacity-50"
              style={{
                background: "rgba(52, 211, 153, 0.12)",
                border: "1px solid rgba(52, 211, 153, 0.4)",
                color: "#34D399",
              }}
            >
              ▶ Reactivate
            </button>
            <button
              onClick={revoke}
              disabled={busy}
              className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity disabled:opacity-50 ml-auto"
              style={{
                background: "rgba(248, 113, 113, 0.12)",
                border: "1px solid rgba(248, 113, 113, 0.4)",
                color: "#F87171",
              }}
            >
              ⊘ Revoke (permanent)
            </button>
          </>
        )}
        {(lic.status === "revoked" || lic.status === "expired") && (
          <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
            This license is {lic.status}. Mint a new one to replace it.
          </p>
        )}
      </div>

      {/* ── Counts ── */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card-surface px-5 py-4">
          <div className="text-2xl font-bold font-mono" style={{ color: "var(--accent)" }}>
            {detail.active_device_count}<span style={{ color: "var(--text-muted)", fontSize: "16px" }}>/{lic.max_devices}</span>
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Active devices</div>
        </div>
        <div className="card-surface px-5 py-4">
          <div className="text-2xl font-bold font-mono" style={{ color: "var(--accent)" }}>
            {detail.device_count}
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Total devices (incl. revoked)</div>
        </div>
        <div className="card-surface px-5 py-4">
          <div className="text-2xl font-bold font-mono" style={{ color: "var(--accent)" }}>
            {detail.activations_24h}
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Events in last 24h</div>
        </div>
      </div>

      {/* ── Metadata ── */}
      <div className="card-surface p-5">
        <p className="text-xs font-mono mb-3" style={{ color: "var(--text-muted)" }}>
          Metadata
        </p>
        <div className="grid grid-cols-2 gap-y-2 gap-x-6 text-xs font-mono">
          <Row label="Not before"  value={fmt(lic.not_before)} />
          <Row label="Expires at"  value={fmt(lic.expires_at)} />
          <Row label="Signing kid" value={lic.signing_kid} />
          <Row label="Created at"  value={fmt(lic.created_at)} />
          <Row label="Revoked at"  value={fmt(lic.revoked_at)} />
          <Row label="Revoke reason" value={lic.revoked_reason ?? "—"} />
        </div>
        <div className="mt-4">
          <p className="text-xs font-mono mb-1" style={{ color: "var(--text-muted)" }}>Features</p>
          <pre
            className="text-[11px] font-mono p-3 rounded-lg overflow-x-auto"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
          >
            {JSON.stringify(lic.features, null, 2)}
          </pre>
        </div>
      </div>

      {/* ── Devices ── */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Bound devices ({devices.length})
        </h2>
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}
        >
          <table className="text-xs w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["ID", "Fingerprint", "Hostname", "Platform", "Last IP", "Last seen", "Status", "Action"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-mono font-medium" style={{ color: "var(--text-muted)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!devices.length ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center font-mono" style={{ color: "var(--text-muted)" }}>
                    No devices have activated yet.
                  </td>
                </tr>
              ) : (
                devices.map((d) => (
                  <tr key={d.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--accent)" }}>#{d.id}</td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-primary)" }}>
                      {d.fingerprint.slice(0, 16)}…
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-secondary)" }}>{d.hostname ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-secondary)" }}>{d.platform ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-secondary)" }}>{d.last_ip ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-muted)" }}>{fmt(d.last_seen_at)}</td>
                    <td className="px-4 py-2.5">
                      {d.revoked_at ? (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono" style={{ color: "#F87171", background: "rgba(248,113,113,0.16)" }}>
                          revoked
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-mono" style={{ color: "#34D399", background: "rgba(52,211,153,0.16)" }}>
                          active
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {!d.revoked_at && (
                        <button
                          onClick={() => revokeDevice(d.id, d.fingerprint)}
                          disabled={busy}
                          className="text-[11px] px-2 py-1 rounded font-mono"
                          style={{
                            border: "1px solid var(--border-bright)",
                            color: "#F87171",
                            background: "transparent",
                          }}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Activations ── */}
      <div className="space-y-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          Recent activations (last 50)
        </h2>
        <div
          className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}
        >
          <table className="text-xs w-full">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["#", "Event", "Reason", "Fingerprint", "IP", "When"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-mono font-medium" style={{ color: "var(--text-muted)" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!activations.length ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center font-mono" style={{ color: "var(--text-muted)" }}>
                    No events yet.
                  </td>
                </tr>
              ) : (
                activations.map((a) => (
                  <tr key={a.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="px-4 py-2 font-mono" style={{ color: "var(--text-muted)" }}>{a.id}</td>
                    <td className="px-4 py-2 font-mono uppercase" style={{ color: EVENT_COLORS[a.event] }}>
                      {a.event}
                    </td>
                    <td className="px-4 py-2 font-mono" style={{ color: "var(--text-secondary)" }}>{a.reason ?? "—"}</td>
                    <td className="px-4 py-2 font-mono" style={{ color: "var(--text-muted)" }}>
                      {a.fingerprint ? a.fingerprint.slice(0, 14) + "…" : "—"}
                    </td>
                    <td className="px-4 py-2 font-mono" style={{ color: "var(--text-muted)" }}>{a.ip ?? "—"}</td>
                    <td className="px-4 py-2 font-mono" style={{ color: "var(--text-muted)" }}>{fmt(a.created_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline gap-4">
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ color: "var(--text-primary)" }} className="truncate">{value}</span>
    </div>
  );
}
