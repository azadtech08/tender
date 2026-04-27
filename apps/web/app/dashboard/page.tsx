"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

const API = "/api-backend";

type Job = {
  id: number;
  keywords: string[];
  status: string;
  total_keywords: number | null;
  done_keywords: number | null;
  total_tenders: number | null;
  created_at: string;
};

type JobList = { items: Job[]; total: number; page: number; per_page: number };

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [jobs, setJobs]         = useState<JobList | null>(null);
  const [loading, setLoading]   = useState(true);
  const [keywords, setKeywords] = useState("");
  const [perKeyword, setPerKeyword] = useState(10);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function fetchJobs() {
    const token = await getToken();
    console.log("[DEBUG] Clerk token:", token ? token.substring(0, 40) + "..." : "NULL");
    if (!token) { setLoading(false); return; }
    const res = await fetch(`${API}/api/jobs?per_page=30`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    console.log("[DEBUG] /api/jobs status:", res.status);
    if (res.ok) setJobs(await res.json());
    setLoading(false);
  }

  useEffect(() => { fetchJobs(); }, []);

  async function createAndRun() {
    const kws = keywords.split(",").map((k) => k.trim()).filter(Boolean);
    if (!kws.length) return;
    setCreating(true);
    const token = await getToken();
    const res = await fetch(`${API}/api/jobs`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ keywords: kws, cards_per_kw: perKeyword }),
    });
    if (res.ok) {
      const job = await res.json();
      await fetch(`${API}/api/jobs/${job.id}/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setKeywords("");
      await fetchJobs();
    }
    setCreating(false);
  }

  async function deleteJob(id: number, keywordLabel: string) {
    const ok = window.confirm(
      `Delete job "${keywordLabel}"?\n\nThis will remove the job and all tenders, events, and schedules associated with it. This cannot be undone.`
    );
    if (!ok) return;
    setDeletingId(id);
    try {
      const token = await getToken();
      const res = await fetch(`${API}/api/jobs/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) {
        alert(`Failed to delete job (${res.status})`);
        return;
      }
      setJobs((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.filter((j) => j.id !== id),
              total: Math.max(0, prev.total - 1),
            }
          : prev
      );
    } finally {
      setDeletingId(null);
    }
  }

  // Stats
  const totalJobs    = jobs?.total ?? 0;
  const totalTenders = jobs?.items.reduce((s, j) => s + (j.total_tenders ?? 0), 0) ?? 0;
  const running      = jobs?.items.filter((j) => j.status === "running").length ?? 0;

  return (
    <div className="max-w-4xl space-y-8">
      {/* ── Header ── */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
          Scrape Jobs
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Dispatch keyword searches against GeM portal and collect tender intelligence.
        </p>
      </div>

      {/* ── Stats row ── */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total jobs",    value: totalJobs },
          { label: "Total tenders", value: totalTenders },
          { label: "Running now",   value: running },
        ].map((s) => (
          <div key={s.label} className="card-surface px-5 py-4">
            <div
              className="text-3xl font-bold font-mono"
              style={{ color: "var(--accent)" }}
            >
              {s.value}
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* ── New job ── */}
      <div className="card-surface p-5">
        <p className="text-xs font-mono mb-3" style={{ color: "var(--text-muted)" }}>
          NEW JOB — keywords (comma-separated) · tenders per keyword
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Laptop, Server, AMC, Networking…"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createAndRun()}
            className="flex-1 text-sm px-4 py-2.5 rounded-lg font-mono outline-none transition-all"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
          <input
            type="number"
            min={1}
            max={100}
            step={1}
            value={perKeyword}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (Number.isFinite(n)) setPerKeyword(Math.max(1, Math.min(100, n)));
            }}
            onKeyDown={(e) => e.key === "Enter" && createAndRun()}
            aria-label="Tenders per keyword"
            title="How many tenders to fetch per keyword (1–100)"
            className="w-24 text-sm px-3 py-2.5 rounded-lg font-mono outline-none transition-all text-center"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          />
          <button
            onClick={createAndRun}
            disabled={creating}
            className="text-sm px-5 py-2.5 rounded-lg font-semibold transition-opacity disabled:opacity-50 glow-amber"
            style={{ background: "var(--accent)", color: "#0F1117" }}
          >
            {creating ? "Creating…" : "▶ Run"}
          </button>
        </div>
      </div>

      {/* ── Job list ── */}
      {loading ? (
        <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>Loading…</p>
      ) : !jobs?.items.length ? (
        <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          No jobs yet. Create one above.
        </p>
      ) : (
        <div className="space-y-2">
          {jobs.items.map((job) => (
            <Link
              key={job.id}
              href={`/dashboard/jobs/${job.id}`}
              className="card-surface flex items-center gap-4 px-5 py-3.5 transition-all hover:border-white/10 block"
            >
              {/* Status pill */}
              <span className={`status-${job.status} text-xs px-2.5 py-0.5 rounded-full font-mono shrink-0 capitalize`}>
                {job.status}
              </span>

              {/* Keywords */}
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate" style={{ color: "var(--text-primary)" }}>
                  {job.keywords.join(" · ")}
                </p>
                <p className="text-xs font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                  #{job.id} · {new Date(job.created_at).toLocaleDateString("en-IN")}
                  {job.status === "running" && job.total_keywords != null &&
                    ` · ${job.done_keywords ?? 0}/${job.total_keywords} kw`}
                  {job.status === "completed" &&
                    ` · ${job.total_tenders ?? 0} tenders`}
                </p>
              </div>

              {/* Delete */}
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  deleteJob(job.id, job.keywords.join(", "));
                }}
                disabled={deletingId === job.id}
                aria-label={`Delete job ${job.id}`}
                title="Delete this job and all related data"
                className="text-xs px-3 py-1.5 rounded-md font-mono transition-opacity disabled:opacity-50 shrink-0"
                style={{
                  background: "transparent",
                  border: "1px solid var(--border-bright)",
                  color: "#F87171",
                }}
              >
                {deletingId === job.id ? "…" : "Delete"}
              </button>

              {/* Arrow */}
              <span style={{ color: "var(--text-muted)", fontSize: "16px" }}>›</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
