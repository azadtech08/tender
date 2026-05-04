"use client";

import { useAuth } from "@clerk/nextjs";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "/api-backend";

// ── Types ──────────────────────────────────────────────────────────────────────

type Job = {
  id: number;
  keywords: string[];
  status: string;
  total_keywords: number | null;
  done_keywords: number | null;
  total_tenders: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
};

type Tender = {
  id: number;
  keyword: string;
  tender_ref_no: string | null;
  tender_type: string | null;
  published_date: string | null;
  bid_end_date: string | null;
  title: string | null;
  description: string | null;
  cleaned_boq: string | null;
  organisation: string | null;
  ministry: string | null;
  tender_value: number | null;
  emd: number | null;
  state: string | null;
  pincode: string | null;
  delivery_period: string | null;
  product_type: string | null;
  exemption: string | null;
  email: string | null;
  it_relevant: string | null;
  quantity: string | null;
  link: string | null;
};

type TenderList = { items: Tender[]; total: number };

type LogLine = {
  event: string;
  payload: Record<string, unknown>;
  time: string;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

const SORT_OPTIONS = [
  { value: "published_latest", label: "Bid Start Date: Latest First" },
  { value: "published_oldest", label: "Bid Start Date: Oldest First" },
  { value: "bid_end_latest",   label: "Bid End Date: Latest First" },
  { value: "bid_end_oldest",   label: "Bid End Date: Oldest First" },
];

const LOG_COLORS: Record<string, string> = {
  status_change: "#60A5FA",   // blue
  keyword_start: "#A78BFA",   // purple
  cards_found:   "#F59E0B",   // amber
  card_scraped:  "#F59E0B",
  pdf_parsed:    "#34D399",   // green
  keyword_done:  "#34D399",
  complete:      "#10B981",   // emerald
  error:         "#F87171",   // red
  search_retry:  "#FBBF24",   // yellow
  search_failed: "#F87171",   // red
};

function logColor(event: string): string {
  return LOG_COLORS[event] ?? "#8B8D97";
}

function formatPayload(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  if (payload.keyword) parts.push(`kw="${payload.keyword}"`);
  if (payload.bid_no) parts.push(`bid=${payload.bid_no}`);
  if (payload.count != null) parts.push(`count=${payload.count}`);
  if (payload.tenders_found != null) parts.push(`found=${payload.tenders_found}`);
  if (payload.total_tenders != null) parts.push(`total=${payload.total_tenders}`);
  if (payload.status) parts.push(`→ ${payload.status}`);
  if (payload.message) parts.push(`err="${payload.message}"`);
  if (payload.error) parts.push(`error="${payload.error}"`);
  if (payload.attempt != null) parts.push(`attempt=${payload.attempt}`);
  return parts.join(" ") || JSON.stringify(payload);
}

// ── SVG Progress Ring ──────────────────────────────────────────────────────────

function ProgressRing({ pct, status }: { pct: number; status: string }) {
  const r = 36;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  const colour =
    status === "completed" ? "#10B981"
    : status === "failed"  ? "#EF4444"
    : status === "running" ? "#3B82F6"
    : "#6B7280";

  return (
    <svg width="96" height="96" viewBox="0 0 96 96" className="shrink-0">
      {/* Track */}
      <circle cx="48" cy="48" r={r} fill="none" stroke="#2C3040" strokeWidth="6" />
      {/* Progress */}
      <circle
        cx="48" cy="48" r={r}
        fill="none"
        stroke={colour}
        strokeWidth="6"
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ / 4}
        style={{ transition: "stroke-dasharray 0.5s ease" }}
      />
      {/* Centre text */}
      <text
        x="48" y="52"
        textAnchor="middle"
        fontSize="14"
        fontWeight="600"
        fontFamily="'JetBrains Mono', monospace"
        fill={colour}
      >
        {pct}%
      </text>
    </svg>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function JobDetailPage() {
  const { id: jobId } = useParams<{ id: string }>();
  const { getToken } = useAuth();
  const searchParams = useSearchParams();

  const [job, setJob]       = useState<Job | null>(null);
  const [tenders, setTenders] = useState<TenderList | null>(null);
  const [log, setLog]       = useState<LogLine[]>([]);
  const [pinned, setPinned] = useState(true);
  const [loading, setLoading] = useState(true);
  const [stateFilter, setStateFilter] = useState<string>("");
  const [selectedMinistries, setSelectedMinistries] = useState<string[]>([]);
  const [ministryOpen, setMinistryOpen] = useState(false);
  const [sortOrder, setSortOrder] = useState<string>(
    searchParams.get("sort") ?? "published_latest"
  );
  const [ministries, setMinistries] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const pollRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // ── Data fetching ────────────────────────────────────────────────────────────

  async function fetchJob(): Promise<Job | null> {
    const token = await getToken();
    const res = await fetch(`${API}/api/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data: Job = await res.json();
    setJob(data);
    return data;
  }

  async function fetchTenders(s = sortOrder, m = selectedMinistries) {
    const token = await getToken();
    const params = new URLSearchParams({ job_id: jobId!, per_page: "200" });
    if (s) params.set("sort", s);
    if (m.length) params.set("ministry", m.join(","));
    const res = await fetch(`${API}/api/tenders?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setTenders(await res.json());
  }

  async function fetchMinistries() {
    const token = await getToken();
    const res = await fetch(`${API}/api/tenders/ministries`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setMinistries(await res.json());
  }

  // ── Polling (replaces SSE — Next.js dev proxy buffers SSE chunks) ─────────────

  function pushLog(event: string, payload: Record<string, unknown>) {
    setLog((prev) => [
      ...prev,
      { event, payload, time: new Date().toLocaleTimeString("en-IN", { hour12: false }) },
    ]);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(initialStatus: string, initialDone: number) {
    if (pollRef.current) return;
    let lastStatus = initialStatus;
    let lastDone   = initialDone;

    pollRef.current = setInterval(async () => {
      const j = await fetchJob();
      if (!j) return;

      // Emit a log line when keywords progress
      if ((j.done_keywords ?? 0) > lastDone) {
        lastDone = j.done_keywords ?? 0;
        pushLog("keyword_done", {
          count: lastDone,
          total: j.total_keywords,
          total_tenders: j.total_tenders,
        });
      }

      // Emit a log line on status change
      if (j.status !== lastStatus) {
        lastStatus = j.status;
        pushLog("status_change", { status: j.status });
      }

      // Stop and load results when terminal
      if (j.status === "completed" || j.status === "failed" || j.status === "cancelled") {
        stopPolling();
        await fetchTenders();
        await fetchMinistries();
        pushLog(j.status === "completed" ? "complete" : "error", {
          total_tenders: j.total_tenders,
          message: j.error_message ?? undefined,
        });
      }
    }, 2000);
  }

  // ── Init ─────────────────────────────────────────────────────────────────────

  useEffect(() => {
    async function init() {
      const j = await fetchJob();
      await Promise.all([fetchTenders(), fetchMinistries()]);
      setLoading(false);
      if (j && (j.status === "running" || j.status === "queued")) {
        startPolling(j.status, j.done_keywords ?? 0);
      }
    }
    init();
    return () => { stopPolling(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // Close ministry dropdown on outside click
  const ministryRef = useRef<HTMLDivElement>(null);
  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (ministryRef.current && !ministryRef.current.contains(e.target as Node)) {
      setMinistryOpen(false);
    }
  }, []);
  useEffect(() => {
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [handleClickOutside]);

  // Auto-scroll
  useEffect(() => {
    if (pinned) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, pinned]);

  // ── Actions ──────────────────────────────────────────────────────────────────

  async function handleRun() {
    const token = await getToken();
    await fetch(`${API}/api/jobs/${jobId}/run`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    setLog([]);
    const j = await fetchJob();
    if (j && (j.status === "running" || j.status === "queued")) {
      startPolling(j.status, j.done_keywords ?? 0);
    }
  }

  async function handleDownload(url: string, filename: string) {
    const token = await getToken();
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      alert(`Download failed (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="font-mono text-sm" style={{ color: "var(--text-muted)" }}>
        Loading…
      </div>
    );
  }
  if (!job) {
    return <div className="text-red-400 text-sm">Job not found.</div>;
  }

  const isActive = job.status === "running" || job.status === "queued";
  const isDone   = job.status === "completed" || job.status === "failed";
  const done     = job.done_keywords ?? 0;
  const total    = job.total_keywords ?? 1;
  const pct      = total > 0 ? Math.round((done / total) * 100) : (isDone ? 100 : 0);

  const allItems = tenders?.items ?? [];
  const availableStates = Array.from(
    new Set(allItems.map((t) => t.state).filter((s): s is string => !!s))
  ).sort();
  const filteredTenders = stateFilter
    ? allItems.filter((t) => t.state === stateFilter)
    : allItems;

  return (
    <div className="space-y-6 max-w-5xl">
      {/* ── Breadcrumb ── */}
      <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
        <Link href="/dashboard" style={{ color: "var(--text-secondary)" }} className="hover:text-white transition-colors">
          Jobs
        </Link>
        <span>/</span>
        <span>#{job.id}</span>
      </div>

      {/* ── Header card ── */}
      <div className="card-surface p-5 flex gap-6 items-start">
        <ProgressRing pct={pct} status={job.status} />

        <div className="flex-1 min-w-0 space-y-3">
          {/* Status row */}
          <div className="flex items-center gap-3">
            {isActive && <span className="pulse-dot" />}
            <span className={`status-${job.status} text-xs px-2.5 py-1 rounded-full font-mono font-medium capitalize`}>
              {job.status}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: "12px" }}>
              #{job.id} · {new Date(job.created_at).toLocaleString("en-IN")}
            </span>
          </div>

          {/* Keywords */}
          <div className="flex flex-wrap gap-2">
            {job.keywords.map((kw) => (
              <span
                key={kw}
                className="text-xs px-2.5 py-1 rounded-md font-mono"
                style={{ background: "var(--bg-elevated)", color: "var(--accent)", border: "1px solid var(--border-bright)" }}
              >
                {kw}
              </span>
            ))}
          </div>

          {/* Progress label */}
          {total > 0 && (
            <p className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
              {done}/{total} keywords · {job.total_tenders ?? 0} tenders
            </p>
          )}

          {/* Error */}
          {job.error_message && (
            <p className="text-xs font-mono px-3 py-2 rounded" style={{ background: "#1F0D0D", color: "#F87171", border: "1px solid #5B1A1A" }}>
              {job.error_message}
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            {(job.status === "pending" || isDone) && (
              <button
                onClick={handleRun}
                className="text-xs px-4 py-2 rounded-lg font-medium transition-colors glow-amber"
                style={{ background: "var(--accent)", color: "#0F1117" }}
              >
                {job.status === "pending" ? "▶ Run" : "↺ Re-run"}
              </button>
            )}
            {(job.total_tenders ?? 0) > 0 && (
              <button
                onClick={() => handleDownload(`${API}/api/exports/${job.id}.xlsx`, `Tenders_${job.id}.xlsx`)}
                className="text-xs px-4 py-2 rounded-lg font-medium transition-colors"
                style={{ border: "1px solid var(--border-bright)", color: "var(--text-secondary)" }}
              >
                ↓ Export XLSX
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Terminal log ── */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
            EVENT LOG
          </span>
          <button
            onClick={() => setPinned((p) => !p)}
            className="text-xs font-mono transition-colors"
            style={{ color: pinned ? "var(--accent)" : "var(--text-muted)" }}
          >
            {pinned ? "● PINNED" : "○ UNPINNED"}
          </button>
        </div>
        <div
          className="terminal p-4 h-52 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget;
            const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 4;
            if (!atBottom && pinned) setPinned(false);
          }}
        >
          {log.length === 0 ? (
            <span style={{ color: "var(--text-muted)" }}>
              {isActive ? "Waiting for events…" : "No events. Press Run to start."}
            </span>
          ) : (
            log.map((line, i) => (
              <div key={i} className="leading-6 whitespace-nowrap overflow-x-hidden">
                <span style={{ color: "var(--text-muted)" }}>{line.time}</span>
                {" "}
                <span style={{ color: logColor(line.event) }}>{line.event}</span>
                {" "}
                <span style={{ color: "#C8C9D0" }}>{formatPayload(line.payload)}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* ── Tenders table ── */}
      <div className="card-surface overflow-hidden">
        <div
          className="px-5 py-4 flex items-center justify-between gap-3 flex-wrap"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            Tenders{" "}
            {tenders && (
              <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                ({filteredTenders.length}/{tenders.total})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3 flex-wrap">
            {/* Multi-select Ministry dropdown */}
            <div ref={ministryRef} className="relative flex items-center gap-1.5">
              <span className="text-xs font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>Ministry:</span>
              <button
                onClick={() => setMinistryOpen((o) => !o)}
                className="text-xs font-mono px-3 py-1.5 rounded-md text-left flex items-center gap-2"
                style={{
                  background: "var(--bg-elevated)",
                  color: "var(--text-primary)",
                  border: `1px solid ${selectedMinistries.length ? "var(--accent)" : "var(--border-bright)"}`,
                  minWidth: "160px",
                  maxWidth: "220px",
                }}
              >
                <span className="truncate">
                  {selectedMinistries.length === 0
                    ? "All Ministries"
                    : selectedMinistries.length === 1
                    ? selectedMinistries[0]
                    : `${selectedMinistries.length} selected`}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: "10px", marginLeft: "auto" }}>
                  {ministryOpen ? "▲" : "▼"}
                </span>
              </button>
              {selectedMinistries.length > 0 && (
                <button
                  onClick={() => { setSelectedMinistries([]); fetchTenders(sortOrder, []); }}
                  className="text-xs font-mono px-1 py-0.5 rounded transition-colors"
                  style={{ color: "var(--accent)", background: "var(--bg-elevated)", border: "1px solid var(--border-bright)" }}
                  title="Clear ministry filter"
                >
                  ✕
                </button>
              )}
              {ministryOpen && (
                <div
                  className="absolute top-full left-0 mt-1 z-50 rounded-lg overflow-hidden"
                  style={{
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-bright)",
                    maxHeight: "240px",
                    overflowY: "auto",
                    minWidth: "240px",
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  }}
                >
                  {ministries.length === 0 ? (
                    <div className="px-3 py-2 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                      No ministries found
                    </div>
                  ) : (
                    ministries.map((m) => (
                      <label
                        key={m}
                        className="flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors hover:bg-white/[0.04]"
                        style={{ borderBottom: "1px solid var(--border)" }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedMinistries.includes(m)}
                          onChange={() => {
                            const next = selectedMinistries.includes(m)
                              ? selectedMinistries.filter((x) => x !== m)
                              : [...selectedMinistries, m];
                            setSelectedMinistries(next);
                            fetchTenders(sortOrder, next);
                          }}
                          className="accent-amber-500"
                        />
                        <span className="text-xs font-mono truncate" style={{ color: "var(--text-primary)" }}>
                          {m}
                        </span>
                      </label>
                    ))
                  )}
                </div>
              )}
            </div>
            {/* State filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>State:</span>
              <select
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
                className="text-xs font-mono px-3 py-1.5 rounded-md"
                style={{
                  background: "var(--bg-elevated)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-bright)",
                }}
              >
                <option value="">All States</option>
                {availableStates.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            {/* Sort dropdown */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>Sort by:</span>
              <select
                value={sortOrder}
                onChange={(e) => {
                  setSortOrder(e.target.value);
                  fetchTenders(e.target.value, selectedMinistries);
                }}
                className="text-xs font-mono px-3 py-1.5 rounded-md"
                style={{
                  background: "var(--bg-elevated)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-bright)",
                }}
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            {isActive && (
              <button
                onClick={() => fetchTenders()}
                className="text-xs font-mono transition-colors px-3 py-1.5"
                style={{ color: "var(--text-muted)" }}
              >
                ↻ Refresh
              </button>
            )}
          </div>
        </div>

        {!filteredTenders.length ? (
          <div className="px-5 py-10 text-center text-xs font-mono" style={{ color: "var(--text-muted)" }}>
            {job.status === "completed" ? "No tenders found." : "Tenders will appear here as the job runs."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={{ minWidth: "1400px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                  {[
                    "", "Reference", "Title", "Organisation", "Ministry",
                    "Value (₹)", "EMD (₹)", "Published", "Bid End",
                    "Delivery", "State", "Pincode", "IT", "Files",
                  ].map((h) => (
                    <th key={h} className="px-3 py-3 text-left font-medium font-mono whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredTenders.map((t) => {
                  const isOpen = !!expanded[t.id];
                  return (
                    <Fragment key={t.id}>
                      <tr
                        style={{ borderBottom: "1px solid var(--border)" }}
                        className="transition-colors hover:bg-white/[0.02] cursor-pointer"
                        onClick={() => setExpanded((p) => ({ ...p, [t.id]: !p[t.id] }))}
                      >
                        <td className="px-3 py-2.5 font-mono" style={{ color: "var(--text-muted)" }}>
                          {isOpen ? "▾" : "▸"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>
                          {t.tender_ref_no ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 max-w-[260px] truncate" style={{ color: "var(--text-primary)" }}>
                          {t.title ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 max-w-[200px] truncate" style={{ color: "var(--text-secondary)" }}>
                          {t.organisation ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 max-w-[160px] truncate" style={{ color: "var(--text-secondary)" }}>
                          {t.ministry ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--text-primary)" }}>
                          {t.tender_value ? `₹${t.tender_value.toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.emd ? `₹${t.emd.toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.published_date ? new Date(t.published_date).toLocaleDateString("en-IN") : "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.bid_end_date ? new Date(t.bid_end_date).toLocaleDateString("en-IN") : "—"}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.delivery_period ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.state ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono whitespace-nowrap" style={{ color: "var(--text-secondary)" }}>
                          {t.pincode ?? "—"}
                        </td>
                        <td className="px-3 py-2.5 font-mono">
                          <span style={{ color: t.it_relevant === "YES" ? "#34D399" : "var(--text-muted)" }}>
                            {t.it_relevant ?? "—"}
                          </span>
                        </td>
                        <td
                          className="px-3 py-2.5 font-mono whitespace-nowrap"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() =>
                                handleDownload(
                                  `${API}/api/tenders/${t.id}/pdf`,
                                  `${t.tender_ref_no ?? `tender-${t.id}`}.pdf`,
                                )
                              }
                              title="Download PDF"
                              className="transition-colors"
                              style={{ color: "var(--accent)" }}
                            >
                              ↓ PDF
                            </button>
                            {t.link && (
                              <a
                                href={t.link}
                                target="_blank"
                                rel="noopener noreferrer"
                                title="Open on GeM"
                                style={{ color: "var(--text-secondary)" }}
                              >
                                ↗ GeM
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr style={{ borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.015)" }}>
                          <td></td>
                          <td colSpan={13} className="px-3 py-4">
                            <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-xs">
                              {t.description && (
                                <div className="col-span-2">
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>DESCRIPTION</div>
                                  <div style={{ color: "var(--text-primary)" }}>{t.description}</div>
                                </div>
                              )}
                              {t.cleaned_boq && (
                                <div className="col-span-2">
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>BOQ</div>
                                  <pre className="whitespace-pre-wrap font-mono" style={{ color: "var(--text-primary)" }}>{t.cleaned_boq}</pre>
                                </div>
                              )}
                              {t.quantity && (
                                <div>
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>QUANTITY</div>
                                  <div style={{ color: "var(--text-primary)" }}>{t.quantity}</div>
                                </div>
                              )}
                              {t.product_type && (
                                <div>
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>PRODUCT TYPE</div>
                                  <div style={{ color: "var(--text-primary)" }}>{t.product_type}</div>
                                </div>
                              )}
                              {t.exemption && (
                                <div>
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>EXEMPTION</div>
                                  <div style={{ color: "var(--text-primary)" }}>{t.exemption}</div>
                                </div>
                              )}
                              {t.email && (
                                <div>
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>EMAIL</div>
                                  <div className="font-mono" style={{ color: "var(--accent)" }}>{t.email}</div>
                                </div>
                              )}
                              {t.tender_type && (
                                <div>
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>TENDER TYPE</div>
                                  <div style={{ color: "var(--text-primary)" }}>{t.tender_type}</div>
                                </div>
                              )}
                              {t.link && (
                                <div className="col-span-2">
                                  <div className="font-mono mb-1" style={{ color: "var(--text-muted)" }}>LINK</div>
                                  <a href={t.link} target="_blank" rel="noopener noreferrer" className="font-mono break-all" style={{ color: "var(--accent)" }}>
                                    {t.link}
                                  </a>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
