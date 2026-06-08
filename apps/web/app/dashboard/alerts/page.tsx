"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";

const API = "/api-backend";

interface Alert {
  id: number;
  name: string;
  keywords: string | null;
  min_value: number | null;
  state_filter: string | null;
  email_to: string | null;
  slack_webhook_url: string | null;
  is_active: boolean;
  last_triggered_at: string | null;
  created_at: string;
}

function useApiHeaders() {
  const { getToken } = useAuth();
  return async () => {
    const token = await getToken();
    return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  };
}

const CELL = "px-4 py-3 text-sm";
const LABEL = "block text-xs mb-1 font-medium";
const INPUT =
  "w-full px-3 py-2 rounded text-sm outline-none focus:ring-1 focus:ring-amber-500/70";

// ── Alert row ─────────────────────────────────────────────────────────────────

function AlertRow({
  alert,
  onToggle,
  onDelete,
}: {
  alert: Alert;
  onToggle: (id: number, active: boolean) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td className={CELL} style={{ color: "var(--accent)", fontFamily: "monospace" }}>
        {alert.name}
      </td>
      <td className={CELL} style={{ color: "var(--text-secondary)" }}>
        {alert.keywords ?? <span style={{ color: "var(--text-muted)" }}>any</span>}
      </td>
      <td className={CELL} style={{ color: "var(--text-secondary)" }}>
        {alert.min_value != null ? `₹${alert.min_value.toLocaleString()}` : "—"}
      </td>
      <td className={CELL} style={{ color: "var(--text-secondary)" }}>
        {alert.state_filter ?? "—"}
      </td>
      <td className={CELL} style={{ color: "var(--text-secondary)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {alert.email_to ?? "—"}
      </td>
      <td className={`${CELL} text-center`}>
        <button
          onClick={() => onToggle(alert.id, !alert.is_active)}
          className="px-2 py-0.5 rounded text-xs font-medium transition-colors"
          style={
            alert.is_active
              ? { background: "rgba(34,197,94,0.15)", color: "#4ade80" }
              : { background: "rgba(148,163,184,0.1)", color: "var(--text-muted)" }
          }
        >
          {alert.is_active ? "Active" : "Paused"}
        </button>
      </td>
      <td className={CELL} style={{ color: "var(--text-muted)" }}>
        {alert.last_triggered_at
          ? new Date(alert.last_triggered_at).toLocaleDateString("en-IN")
          : "Never"}
      </td>
      <td className={`${CELL} text-right`}>
        <button
          onClick={() => onDelete(alert.id)}
          className="text-xs px-2 py-0.5 rounded transition-colors"
          style={{ color: "#f87171", background: "rgba(248,113,113,0.1)" }}
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

// ── Create form ───────────────────────────────────────────────────────────────

function CreateAlertForm({ onCreated }: { onCreated: () => void }) {
  const getHeaders = useApiHeaders();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const form = useRef<HTMLFormElement>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setError("");

    const fd = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {
      name: fd.get("name"),
      keywords: fd.get("keywords") || null,
      min_value: fd.get("min_value") ? Number(fd.get("min_value")) : null,
      state_filter: fd.get("state_filter") || null,
      email_to: fd.get("email_to") || null,
      slack_webhook_url: fd.get("slack_webhook_url") || null,
      is_active: true,
    };

    try {
      const resp = await fetch(`${API}/api/alerts`, {
        method: "POST",
        headers: await getHeaders(),
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail ?? "Failed to create alert");
      } else {
        form.current?.reset();
        setOpen(false);
        onCreated();
      }
    } catch {
      setError("Network error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="px-4 py-2 rounded text-sm font-semibold transition-colors"
        style={{  color: "#dadee9" }}
      >
        {open ? "Cancel" : "+ New Alert"}
      </button>

      {open && (
        <form
          ref={form}
          onSubmit={handleSubmit}
          className="mt-4 p-5 rounded-xl space-y-4"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          <h3 className="font-semibold text-white" >
            Create Alert
          </h3>     

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                Alert Name *
              </label>
              <input
                name="name"
                required
                placeholder="e.g. High-value IT tenders"
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>

            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                Keywords (comma-separated)
              </label>
              <input
                name="keywords"
                placeholder="laptop, server, cloud"
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>

            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                Minimum Value (₹)
              </label>
              <input
                name="min_value"
                type="number"
                min={0}
                placeholder="e.g. 500000"
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>

            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                State Filter
              </label>
              <input
                name="state_filter"
                placeholder="e.g. Maharashtra"
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>

            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                Email Recipients (comma-separated)
              </label>
              <input
                name="email_to"
                type="text"
                placeholder="you@example.com, team@example.com"
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>

            <div>
              <label className={LABEL} style={{ color: "var(--text-secondary)" }}>
                Slack Webhook URL
              </label>
              <input
                name="slack_webhook_url"
                type="url"
                placeholder="https://hooks.slack.com/services/..."
                className={INPUT}
                style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
              />
            </div>
          </div>

          {error && (
            <p className="text-sm" style={{ color: "#f87171" }}>
              {error}
            </p>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded text-sm font-semibold disabled:opacity-50"
              style={{ background: "var(--accent)", color: "#0f46ec" }}
            >
              {saving ? "Saving…" : "Create Alert"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-4 py-2 rounded text-sm"
              style={{ color: "var(--text-secondary)", background: "var(--bg-elevated)" }}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const getHeaders = useApiHeaders();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const resp = await fetch(`${API}/api/alerts`, { headers: await getHeaders() });
      if (resp.ok) setAlerts(await resp.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggleAlert(id: number, is_active: boolean) {
    await fetch(`${API}/api/alerts/${id}`, {
      method: "PATCH",
      headers: await getHeaders(),
      body: JSON.stringify({ is_active }),
    });
    await load();
  }

  async function deleteAlert(id: number) {
    if (!confirm("Delete this alert?")) return;
    await fetch(`${API}/api/alerts/${id}`, { method: "DELETE", headers: await getHeaders() });
    await load();
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
            Alerts
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
            Daily email &amp; Slack digest when new tenders match your criteria
          </p>
        </div>
        <CreateAlertForm onCreated={load} />
      </div>

      {/* Table */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ border: "1px solid var(--border)", background: "var(--bg-surface)" }}
      >
        {loading ? (
          <div className="p-8 text-center" style={{ color: "var(--text-muted)" }}>
            Loading…
          </div>
        ) : alerts.length === 0 ? (
          <div className="p-12 text-center space-y-2">
            <p className="text-2xl">🔔</p>
            <p style={{ color: "var(--text-secondary)" }}>No alerts yet</p>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Create an alert to receive daily digests when matching tenders are found.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-elevated)" }}>
                  {["Name", "Keywords", "Min Value", "State", "Email To", "Status", "Last Fired", ""].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-semibold tracking-wider uppercase"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <AlertRow key={a.id} alert={a} onToggle={toggleAlert} onDelete={deleteAlert} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Info card */}
      <div
        className="rounded-xl p-5 text-sm space-y-1"
        style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
      >
        <p className="font-semibold" style={{ color: "var(--text-primary)" }}>
          How alerts work
        </p>
        <p>Digests are sent daily at <strong>08:00 IST</strong> for tenders scraped since the last trigger.</p>
        <p>At least one of <em>email</em> or <em>Slack webhook</em> must be provided per alert.</p>
        <p>Leave <em>keywords</em>, <em>min value</em>, and <em>state</em> blank to receive all new tenders.</p>
      </div>
    </div>
  );
}
