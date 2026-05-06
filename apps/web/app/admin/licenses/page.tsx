"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
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

type ListResponse = {
  items: License[];
  total: number;
  limit: number;
  offset: number;
};

const STATUS_COLORS: Record<License["status"], string> = {
  active:    "#34D399",
  suspended: "#FBBF24",
  revoked:   "#F87171",
  expired:   "#9CA3AF",
};

function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("en-IN"); } catch { return s; }
}

export default function LicensesListPage() {
  const { getToken } = useAuth();
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | License["status"]>("");
  const [planFilter, setPlanFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");

  async function fetchLicenses() {
    setLoading(true);
    setError(null);
    const token = await getToken();
    const params = new URLSearchParams({ limit: "100" });
    if (statusFilter) params.set("status", statusFilter);
    if (planFilter) params.set("plan", planFilter);
    if (tenantFilter.trim()) params.set("tenant_id", tenantFilter.trim());
    try {
      const res = await fetch(`${API}/api/admin/licenses?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 403) {
        setError(
          "Backend returned 403. Your Clerk user isn't configured as admin — " +
          "set public_metadata.role='tenzo_admin' in Clerk dashboard, " +
          "or add your Clerk user_id to LOCAL_ADMIN_USER_IDS in docker-compose.yml."
        );
        return;
      }
      if (!res.ok) {
        setError(`Failed to load licenses (HTTP ${res.status}).`);
        return;
      }
      setData(await res.json());
    } catch (e) {
      setError(`Network error: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchLicenses(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, []);

  function applyFilters() {
    fetchLicenses();
  }

  const activeCount    = data?.items.filter((l) => l.status === "active").length    ?? 0;
  const revokedCount   = data?.items.filter((l) => l.status === "revoked").length   ?? 0;
  const suspendedCount = data?.items.filter((l) => l.status === "suspended").length ?? 0;

  return (
    <div className="max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
            Licenses
          </h1>
          <p className="text-xs font-mono mt-1" style={{ color: "var(--text-muted)" }}>
            {data?.total ?? 0} licenses · {activeCount} active · {suspendedCount} suspended · {revokedCount} revoked
          </p>
        </div>
        <Link
          href="/admin/licenses/new"
          className="text-sm px-5 py-2.5 rounded-lg font-semibold transition-opacity glow-amber"
          style={{ background: "#F59E0B", color: "#0F1117" }}
        >
          ＋ Mint new license
        </Link>
      </div>

      {/* Filters */}
      <div className="card-surface p-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs font-mono block mb-1" style={{ color: "var(--text-muted)" }}>
            Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
            className="text-sm px-3 py-2 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          >
            <option value="">all</option>
            <option value="active">active</option>
            <option value="suspended">suspended</option>
            <option value="revoked">revoked</option>
            <option value="expired">expired</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-mono block mb-1" style={{ color: "var(--text-muted)" }}>
            Plan
          </label>
          <select
            value={planFilter}
            onChange={(e) => setPlanFilter(e.target.value)}
            className="text-sm px-3 py-2 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          >
            <option value="">all</option>
            <option value="free">free</option>
            <option value="starter">starter</option>
            <option value="pro">pro</option>
            <option value="business">business</option>
            <option value="enterprise">enterprise</option>
          </select>
        </div>
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs font-mono block mb-1" style={{ color: "var(--text-muted)" }}>
            Tenant ID
          </label>
          <input
            type="text"
            placeholder="exact tenant_id (uuid)"
            value={tenantFilter}
            onChange={(e) => setTenantFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyFilters()}
            className="w-full text-sm px-3 py-2 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
        </div>
        <button
          onClick={applyFilters}
          className="text-sm px-4 py-2 rounded-lg font-mono transition-opacity"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-bright)",
            color: "var(--text-primary)",
          }}
        >
          Apply
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="card-surface p-4"
          style={{ borderColor: "rgba(248, 113, 113, 0.4)" }}
        >
          <p className="text-sm" style={{ color: "#F87171" }}>⚠ {error}</p>
        </div>
      )}

      {/* Table */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}
      >
        <div className="overflow-x-auto">
          <table className="text-xs w-full" style={{ minWidth: "900px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["ID", "Tenant", "Plan", "Status", "Key prefix", "Expires", "Max devices", "Actions"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-mono font-medium whitespace-nowrap"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center font-mono" style={{ color: "var(--text-muted)" }}>
                    Loading…
                  </td>
                </tr>
              ) : !data?.items.length ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center font-mono" style={{ color: "var(--text-muted)" }}>
                    No licenses yet. Click <span style={{ color: "var(--accent)" }}>＋ Mint new license</span>.
                  </td>
                </tr>
              ) : (
                data.items.map((lic) => (
                  <tr
                    key={lic.id}
                    className="transition-colors hover:bg-white/[0.02]"
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--accent)" }}>
                      #{lic.id}
                    </td>
                    <td
                      className="px-4 py-2.5 font-mono truncate"
                      style={{ color: "var(--text-primary)", maxWidth: "200px" }}
                      title={lic.tenant_id}
                    >
                      {lic.tenant_id}
                    </td>
                    <td className="px-4 py-2.5 font-mono uppercase" style={{ color: "var(--text-secondary)" }}>
                      {lic.plan}
                    </td>
                    <td className="px-4 py-2.5">
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
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-muted)" }}>
                      {lic.key_prefix}…
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-secondary)" }}>
                      {fmtDate(lic.expires_at)}
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: "var(--text-secondary)" }}>
                      {lic.max_devices}
                    </td>
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/admin/licenses/${lic.id}`}
                        className="text-xs px-2.5 py-1 rounded font-mono transition-colors"
                        style={{
                          border: "1px solid var(--border-bright)",
                          color: "var(--accent)",
                          background: "transparent",
                        }}
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
        Tip: the plaintext license key is only shown once at mint time. After that only the SHA-256 hash is kept in the DB.
      </p>
    </div>
  );
}
