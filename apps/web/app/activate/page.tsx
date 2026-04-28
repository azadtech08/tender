"use client";

import { useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

const API = "/api-backend";

export default function ActivatePage() {
  const { user, isLoaded } = useUser();
  const router = useRouter();
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!user) return;

    setLoading(true);
    setError(null);

    try {
      const token = await user.reload(); // ensure fresh session
      // Use Clerk userId as the device fingerprint (unique per user, 16+ chars)
      const fingerprint = user.id;

      const res = await fetch(`${API}/api/license/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: key.trim(),
          fingerprint,
          hostname: window.location.hostname,
          platform: "web",
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.message ?? "Activation failed. Check your license key.");
        return;
      }

      setSuccess(true);
      setTimeout(() => router.push("/dashboard"), 1500);
    } catch {
      setError("Network error — please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--bg-base)" }}>
        <span style={{ color: "var(--text-muted)" }}>Loading…</span>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-4"
      style={{ background: "var(--bg-base)" }}
    >
      <div
        className="w-full max-w-md rounded-2xl p-8 space-y-6"
        style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
      >
        {/* Header */}
        <div className="space-y-1">
          <div
            className="text-lg font-bold tracking-tight"
            style={{ color: "var(--accent)", fontFamily: "'JetBrains Mono', monospace" }}
          >
            GeM<span style={{ color: "var(--text-secondary)" }}>/tender</span>
          </div>
          <h1 className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            Activate your license
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Enter the license key provided by your administrator to unlock the dashboard.
          </p>
        </div>

        {success ? (
          <div
            className="rounded-lg px-4 py-3 text-sm font-medium"
            style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e", border: "1px solid rgba(34,197,94,0.25)" }}
          >
            License activated! Redirecting to dashboard…
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                className="text-xs font-medium uppercase tracking-wider"
                style={{ color: "var(--text-secondary)" }}
              >
                License Key
              </label>
              <input
                type="text"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="TNZO-XXXX-XXXX-XXXX-XXXX"
                required
                spellCheck={false}
                autoComplete="off"
                className="w-full rounded-lg px-3 py-2.5 text-sm font-mono outline-none transition-colors"
                style={{
                  background: "var(--bg-base)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
                onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
                onBlur={(e) => (e.target.style.borderColor = "var(--border)")}
              />
            </div>

            {error && (
              <div
                className="rounded-lg px-4 py-3 text-sm"
                style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.25)" }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !key.trim()}
              className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-opacity disabled:opacity-50"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              {loading ? "Activating…" : "Activate License"}
            </button>
          </form>
        )}

        <p className="text-xs text-center" style={{ color: "var(--text-muted)" }}>
          Don&apos;t have a key?{" "}
          <a
            href="mailto:support@aetpl.org"
            style={{ color: "var(--accent)" }}
          >
            Contact support
          </a>
        </p>
      </div>
    </div>
  );
}
