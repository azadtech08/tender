"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

const API = "/api-backend";

const SORT_OPTIONS = [
  { value: "bid_end_latest",   label: "Bid End Date: Latest First" },
  { value: "bid_end_oldest",   label: "Bid End Date: Oldest First" },
  { value: "bid_start_latest", label: "Bid Start Date: Latest First" },
  { value: "bid_start_oldest", label: "Bid Start Date: Oldest First" },
];

type Bid = {
  gem_position: number;
  bid_number: string;
  items: string;
  quantity: string;
  department: string;
  start_date: string;
  end_date: string;
  pdf_url: string;
};

export default function LiveSearchPage() {
  const { getToken } = useAuth();
  const [keyword, setKeyword]   = useState("");
  const [sort, setSort]         = useState("bid_end_latest");
  const [page, setPage]         = useState(1);
  const [bids, setBids]         = useState<Bid[]>([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [searched, setSearched] = useState(false);

  async function search(p = 1) {
    if (!keyword.trim()) return;
    setLoading(true);
    setError("");
    try {
      const token = await getToken();
      const params = new URLSearchParams({
        keyword,
        sort,
        page: String(p),
      });
      const res = await fetch(`${API}/api/tenders/gem-live?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const data = await res.json();
      setBids(data.bids ?? []);
      setTotal(data.total ?? 0);
      setPage(p);
      setSearched(true);
    } catch (e: any) {
      setError(e.message ?? "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
          Live Search
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
          Real-time GeM portal search — same bids, same order as GeM.
        </p>
      </div>

      {/* Search bar */}
      <div className="card-surface p-5 space-y-3">
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Enter keyword e.g. amc, laptop..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search(1)}
            className="flex-1 text-sm px-4 py-2.5 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
              minWidth: "200px",
            }}
          />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="text-sm px-3 py-2.5 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <button
            onClick={() => search(1)}
            disabled={loading}
            className="text-sm px-6 py-2.5 rounded-lg font-semibold disabled:opacity-50 glow-amber"
            style={{ background: "var(--accent)", color: "#d6dbe7" }}
          >
            {loading ? "Searching…" : "🔍 Search"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-sm px-4 py-3 rounded-lg font-mono"
          style={{ background: "#1F0D0D", color: "#F87171", border: "1px solid #5B1A1A" }}>
          {error}
        </div>
      )}

      {/* Results */}
      {searched && (
        <div className="card-surface overflow-hidden">
          <div className="px-5 py-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              Results{" "}
              <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                ({bids.length} shown of {total.toLocaleString()} on GeM)
              </span>
            </h2>
          </div>

          {bids.length === 0 ? (
            <div className="px-5 py-10 text-center text-xs font-mono"
              style={{ color: "var(--text-muted)" }}>
              No bids found for "{keyword}"
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs" style={{ minWidth: "900px" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
                    {["#", "Bid Number", "Items", "Qty", "Department", "Start Date", "End Date", "Link"].map((h) => (
                      <th key={h} className="px-3 py-3 text-left font-medium font-mono whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {bids.map((bid) => (
                    <tr key={bid.bid_number}
                      style={{ borderBottom: "1px solid var(--border)" }}
                      className="hover:bg-white/[0.02]">
                      <td className="px-3 py-2.5 font-mono"
                        style={{ color: "var(--accent)" }}>
                        {bid.gem_position}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap"
                        style={{ color: "var(--accent)" }}>
                        {bid.bid_number}
                      </td>
                      <td className="px-3 py-2.5 max-w-[240px] truncate"
                        style={{ color: "var(--text-primary)" }}>
                        {bid.items}
                      </td>
                      <td className="px-3 py-2.5 font-mono"
                        style={{ color: "var(--text-secondary)" }}>
                        {bid.quantity}
                      </td>
                      <td className="px-3 py-2.5 max-w-[200px] truncate"
                        style={{ color: "var(--text-secondary)" }}>
                        {bid.department}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap"
                        style={{ color: "var(--text-secondary)" }}>
                        {bid.start_date}
                      </td>
                      <td className="px-3 py-2.5 font-mono whitespace-nowrap"
                        style={{ color: "var(--text-secondary)" }}>
                        {bid.end_date}
                      </td>
                      <td className="px-3 py-2.5">
                        {bid.pdf_url && (
                          <a href={bid.pdf_url} target="_blank" rel="noopener noreferrer"
                            style={{ color: "var(--accent)" }}>
                            ↗ GeM
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > 10 && (
            <div className="px-5 py-4 flex items-center gap-4"
              style={{ borderTop: "1px solid var(--border)" }}>
              <button
                onClick={() => search(page - 1)}
                disabled={page <= 1 || loading}
                className="text-xs px-4 py-2 rounded-lg font-mono disabled:opacity-40"
                style={{ border: "1px solid var(--border-bright)", color: "var(--text-secondary)" }}
              >
                ← Prev
              </button>
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                Page {page}
              </span>
              <button
                onClick={() => search(page + 1)}
                disabled={bids.length < 10 || loading}
                className="text-xs px-4 py-2 rounded-lg font-mono disabled:opacity-40"
                style={{ border: "1px solid var(--border-bright)", color: "var(--text-secondary)" }}
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
