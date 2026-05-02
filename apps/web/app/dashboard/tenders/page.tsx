"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

const API = "/api-backend";
const PER_PAGE = 50;

type Tender = {
  id: number;
  job_id: number;
  keyword: string;
  tender_ref_no: string | null;
  tender_type: string | null;
  title: string | null;
  description: string | null;
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
  bid_end_date: string | null;
  published_date: string | null;
  scraped_date: string | null;
};

type TenderList = { items: Tender[]; total: number; page: number; per_page: number };

function fmt(v: number | null | undefined, prefix = "") {
  if (v == null) return "—";
  return prefix + v.toLocaleString("en-IN");
}

function fmtDate(s: string | null | undefined) {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("en-IN"); } catch { return s; }
}

const COLS: { key: keyof Tender; label: string; sticky?: boolean; mono?: boolean }[] = [
  { key: "keyword",              label: "Keyword",    sticky: true, mono: true },
  { key: "tender_ref_no",        label: "Reference",  sticky: true, mono: true },
  { key: "tender_type",          label: "Type",       mono: true },
  { key: "title",                label: "Title" },
  { key: "organisation",         label: "Organisation" },
  { key: "ministry",             label: "Ministry" },
  { key: "tender_value",         label: "Value (₹)",  mono: true },
  { key: "emd",                  label: "EMD (₹)",    mono: true },
  { key: "state",                label: "State" },
  { key: "pincode",              label: "Pincode",    mono: true },
  { key: "delivery_period",      label: "Delivery" },
  { key: "product_type",         label: "Product Type" },
  { key: "exemption",            label: "Exemption" },
  { key: "email",                label: "Email",      mono: true },
  { key: "it_relevant",          label: "IT" },
  { key: "quantity",             label: "Quantity" },
  { key: "bid_end_date",            label: "Deadline", mono: true },
  { key: "published_date",       label: "Published",  mono: true },
  { key: "scraped_date",         label: "Scraped",    mono: true },
];

const SORT_OPTIONS = [
  { value: "bid_start_latest", label: "Bid Start Date: Latest First" },
  { value: "bid_start_oldest", label: "Bid Start Date: Oldest First" },
  { value: "bid_end_latest",   label: "Bid End Date: Latest First" },
  { value: "bid_end_oldest",   label: "Bid End Date: Oldest First" },
];

export default function TendersPage() {
  const { getToken } = useAuth();
  const [tenders, setTenders] = useState<TenderList | null>(null);
  const [search, setSearch]   = useState("");
  const [page, setPage]       = useState(1);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [sort, setSort]       = useState("bid_start_latest");
  const [match, setMatch]     = useState<"any" | "all">("any");
  const [selectedMinistries, setSelectedMinistries] = useState<string[]>([]);
  const [ministries, setMinistries] = useState<string[]>([]);
  const [ministryOpen, setMinistryOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function fetchMinistries() {
    const token = await getToken();
    const res = await fetch(`${API}/api/tenders/ministries`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setMinistries(await res.json());
  }

  async function fetchTenders(
    q = search,
    p = page,
    s = sort,
    m = selectedMinistries,
    mt = match,
  ) {
    setLoading(true);
    try {
      const token = await getToken();
      const params = new URLSearchParams({ per_page: String(PER_PAGE), page: String(p) });
      if (q) {
        params.set("search", q);
        params.set("match", mt);
      }
      if (s) params.set("sort", s);
      if (m.length) params.set("ministry", m.join(","));
      const res = await fetch(`${API}/api/tenders?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTenders(await res.json());
    } finally {
      setLoading(false);
    }
  }

  // Export to Excel
  async function handleExport() {
    setExporting(true);
    try {
      const token = await getToken();
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      const url = `${API}/api/tenders/export/xlsx${params.toString() ? "?" + params.toString() : ""}`;
      
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) throw new Error("Export failed");

      // Get filename from Content-Disposition header
      const contentDisposition = res.headers.get("Content-Disposition");
      let filename = "GeM_Tenders.xlsx";
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="([^"]+)"/);
        if (match) filename = match[1];
      }

      // Create blob and trigger download
      const blob = await res.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      console.error("Export error:", error);
      alert("Failed to export tenders");
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => { fetchTenders(); fetchMinistries(); }, []);

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

  // Debounced search
  function handleSearch(val: string) {
    setSearch(val);
    if (searchRef.current) clearTimeout(searchRef.current);
    searchRef.current = setTimeout(() => {
      setPage(1);
      fetchTenders(val, 1, sort, selectedMinistries, match);
    }, 400);
  }

  function handleSort(val: string) {
    setSort(val);
    setPage(1);
    fetchTenders(search, 1, val, selectedMinistries, match);
  }

  function handleMatch(val: "any" | "all") {
    if (val === match) return;
    setMatch(val);
    setPage(1);
    fetchTenders(search, 1, sort, selectedMinistries, val);
  }

  function toggleMinistry(m: string) {
    const next = selectedMinistries.includes(m)
      ? selectedMinistries.filter((x) => x !== m)
      : [...selectedMinistries, m];
    setSelectedMinistries(next);
    setPage(1);
    fetchTenders(search, 1, sort, next, match);
  }

  function clearMinistries() {
    setSelectedMinistries([]);
    setPage(1);
    fetchTenders(search, 1, sort, [], match);
  }

  function goPage(p: number) {
    setPage(p);
    fetchTenders(search, p, sort, selectedMinistries, match);
  }

  async function deleteTender(id: number, ref: string | null) {
    const label = ref ? `tender ${ref}` : `tender #${id}`;
    if (!window.confirm(`Delete ${label}?\n\nThis cannot be undone.`)) return;
    setDeletingId(id);
    try {
      const token = await getToken();
      const res = await fetch(`${API}/api/tenders/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok && res.status !== 204) {
        alert(`Failed to delete tender (status ${res.status})`);
        return;
      }
      // Instant UI update — remove row and decrement counter, no refetch needed
      setTenders((prev) =>
        prev
          ? {
              ...prev,
              items: prev.items.filter((t) => t.id !== id),
              total: Math.max(0, prev.total - 1),
            }
          : prev,
      );
    } catch (err) {
      console.error("Delete error:", err);
      alert("Failed to delete tender");
    } finally {
      setDeletingId(null);
    }
  }

  const totalPages = tenders ? Math.ceil(tenders.total / PER_PAGE) : 1;

  function cellValue(t: Tender, col: (typeof COLS)[number]): string {
    const v = t[col.key];
    if (col.key === "tender_value" || col.key === "emd")
      return fmt(v as number | null, col.key === "tender_value" ? "₹" : "₹");
    if (col.key === "bid_end_date" || col.key === "published_date" || col.key === "scraped_date")
      return fmtDate(v as string | null);
    return (v as string | null) ?? "—";
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
            Tenders
          </h1>
          <p className="text-xs font-mono mt-1" style={{ color: "var(--text-muted)" }}>
            {tenders?.total ?? 0} results
          </p>
        </div>
      </div>

      {/* Search + filters + export row */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="Search — type multiple keywords separated by commas (e.g. laptop, server, amc)"
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          title="Enter multiple keywords separated by commas. Toggle ANY / ALL to control match mode."
          className="flex-1 min-w-[260px] max-w-xl text-sm px-4 py-2 rounded-lg font-mono outline-none transition-all"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-bright)",
            color: "var(--text-primary)",
          }}
        />
        <div
          className="flex items-center rounded-lg overflow-hidden"
          style={{ border: "1px solid var(--border-bright)" }}
          title={
            match === "any"
              ? "ANY — show tenders matching at least one keyword"
              : "ALL — show tenders matching every keyword"
          }
        >
          {(["any", "all"] as const).map((m) => (
            <button
              key={m}
              onClick={() => handleMatch(m)}
              className="text-xs font-mono px-3 py-2 transition-colors"
              style={{
                background: match === m ? "var(--accent)" : "var(--bg-elevated)",
                color: match === m ? "white" : "var(--text-secondary)",
                minWidth: "56px",
              }}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>
        <div ref={ministryRef} className="relative flex items-center gap-1.5">
          <span className="text-xs font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>Ministry:</span>
          <button
            onClick={() => setMinistryOpen((o) => !o)}
            className="text-sm px-3 py-2 rounded-lg font-mono outline-none text-left flex items-center gap-2"
            style={{
              background: "var(--bg-elevated)",
              border: `1px solid ${selectedMinistries.length ? "var(--accent)" : "var(--border-bright)"}`,
              color: "var(--text-primary)",
              minWidth: "180px",
              maxWidth: "260px",
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
              onClick={clearMinistries}
              className="text-xs font-mono px-1.5 py-0.5 rounded transition-colors"
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
                maxHeight: "280px",
                overflowY: "auto",
                minWidth: "260px",
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
                    className="flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors hover:bg-white/[0.04]"
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedMinistries.includes(m)}
                      onChange={() => toggleMinistry(m)}
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
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-mono whitespace-nowrap" style={{ color: "var(--accent)" }}>Sort by:</span>
          <select
            value={sort}
            onChange={(e) => handleSort(e.target.value)}
            className="text-sm px-3 py-2 rounded-lg font-mono outline-none"
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-bright)",
              color: "var(--text-primary)",
            }}
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting || !tenders?.items.length}
          className="text-sm px-4 py-2 rounded-lg font-mono transition-all whitespace-nowrap"
          style={{
            background: "var(--accent)",
            color: "white",
            opacity: exporting || !tenders?.items.length ? 0.5 : 1,
            cursor: exporting || !tenders?.items.length ? "not-allowed" : "pointer",
          }}
        >
          {exporting ? "Exporting…" : "↓ Export XLSX"}
        </button>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          {loading ? "Loading…" : `${tenders?.items.length ?? 0} shown`}
        </span>
      </div>

      {/* Table */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ border: "1px solid var(--border)", background: "var(--bg-card)" }}
      >
        <div className="overflow-x-auto">
          <table className="text-xs w-full" style={{ minWidth: "1600px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th
                  className="px-4 py-3 text-left font-mono font-medium"
                  style={{
                    color: "var(--text-muted)",
                    position: "sticky",
                    left: 0,
                    background: "var(--bg-card)",
                    zIndex: 2,
                  }}
                >
                  #
                </th>
                {COLS.map((col) => (
                  <th
                    key={col.key}
                    className="px-4 py-3 text-left font-mono font-medium whitespace-nowrap"
                    style={{
                      color: "var(--text-muted)",
                      ...(col.sticky
                        ? {
                            position: "sticky",
                            left: col.key === "keyword" ? "40px" : "160px",
                            background: "var(--bg-card)",
                            zIndex: 2,
                          }
                        : {}),
                    }}
                  >
                    {col.label}
                  </th>
                ))}
                <th
                  className="px-4 py-3 text-left font-mono font-medium whitespace-nowrap"
                  style={{ color: "var(--text-muted)" }}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {!tenders?.items.length ? (
                <tr>
                  <td
                    colSpan={COLS.length + 2}
                    className="px-4 py-12 text-center font-mono"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {loading ? "Loading…" : "No tenders found."}
                  </td>
                </tr>
              ) : (
                tenders.items.map((t, i) => (
                  <tr
                    key={t.id}
                    className="transition-colors hover:bg-white/[0.02]"
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    {/* Row number — sticky */}
                    <td
                      className="px-4 py-2.5 font-mono"
                      style={{
                        color: "var(--text-muted)",
                        position: "sticky",
                        left: 0,
                        background: "var(--bg-card)",
                        zIndex: 1,
                      }}
                    >
                      {(page - 1) * PER_PAGE + i + 1}
                    </td>

                    {COLS.map((col) => {
                      const val = cellValue(t, col);
                      const isIt = col.key === "it_relevant";
                      const isRef = col.key === "tender_reference_no";
                      const isTitle = col.key === "title" || col.key === "organisation" || col.key === "ministry";

                      return (
                        <td
                          key={col.key}
                          className="px-4 py-2.5"
                          style={{
                            ...(col.sticky
                              ? {
                                  position: "sticky",
                                  left: col.key === "keyword" ? "40px" : "160px",
                                  background: "var(--bg-card)",
                                  zIndex: 1,
                                }
                              : {}),
                            color: isRef
                              ? "var(--accent)"
                              : isIt
                              ? val === "YES" ? "#34D399" : "var(--text-muted)"
                              : isTitle
                              ? "var(--text-primary)"
                              : "var(--text-secondary)",
                            fontFamily: col.mono ? "'JetBrains Mono', monospace" : undefined,
                            maxWidth: isTitle ? "180px" : undefined,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={isTitle ? val : undefined}
                        >
                          {col.key === "link" && t.link ? (
                            <a
                              href={t.link}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ color: "var(--accent)", textDecoration: "underline" }}
                            >
                              Open
                            </a>
                          ) : val}
                        </td>
                      );
                    })}
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => deleteTender(t.id, t.tender_reference_no)}
                        disabled={deletingId === t.id}
                        className="text-xs px-2.5 py-1 rounded font-mono transition-colors disabled:opacity-40"
                        style={{
                          border: "1px solid var(--border-bright)",
                          color: "#F87171",
                          background: "transparent",
                        }}
                        title="Delete this tender"
                      >
                        {deletingId === t.id ? "Deleting…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
            Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => goPage(page - 1)}
              disabled={page === 1}
              className="text-xs px-3 py-1.5 rounded font-mono transition-colors disabled:opacity-30"
              style={{ border: "1px solid var(--border-bright)", color: "var(--text-secondary)" }}
            >
              ← Prev
            </button>
            <button
              onClick={() => goPage(page + 1)}
              disabled={page >= totalPages}
              className="text-xs px-3 py-1.5 rounded font-mono transition-colors disabled:opacity-30"
              style={{ border: "1px solid var(--border-bright)", color: "var(--text-secondary)" }}
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
