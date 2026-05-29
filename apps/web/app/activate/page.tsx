"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const API = "/api-backend";

// ── Browser fingerprint ───────────────────────────────────────────────────────
// Deterministic per-browser hash used to bind the license to this device.
function getBrowserFingerprint(): string {
  const parts = [
    navigator.userAgent,
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    navigator.language,
    String(navigator.hardwareConcurrency || 0),
    Intl.DateTimeFormat().resolvedOptions().timeZone,
  ];
  const str = parts.join("|");
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h + str.charCodeAt(i)) >>> 0;
  }
  return `web-${h.toString(16).padStart(8, "0")}-${screen.width}x${screen.height}`;
}

// ── Error code → user-friendly message ───────────────────────────────────────
const ERROR_MESSAGES: Record<string, string> = {
  INVALID_KEY:       "License key not recognised. Check for typos and try again.",
  KEY_EXPIRED:       "This license key has expired. Contact your administrator for a new one.",
  KEY_REVOKED:       "This license key has been revoked. Contact your administrator.",
  KEY_SUSPENDED:     "This license key is currently suspended. Contact support.",
  KEY_NOT_YET_VALID: "This license key is not yet active. Try again later.",
  DEVICE_LIMIT:      "Maximum devices already bound to this key. Contact your administrator.",
  DEVICE_REVOKED:    "This device has been revoked from the license. Contact support.",
  RATE_LIMITED:      "Too many activation attempts. Please wait a minute and try again.",
  SIGNING_FAILED:    "Internal error during activation. Please try again.",
};

type ActivateResult =
  | { ok: true; plan: string; license_expires_at: string }
  | { ok: false; error: string; message: string; retry_after_seconds?: number };

export default function ActivatePage() {
  const router = useRouter();
  const { getToken } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);

  const [key, setKey]           = useState("");
  const [loading, setLoading]   = useState(false);
  const [result, setResult]     = useState<ActivateResult | null>(null);

  // Auto-focus the input on mount
  useEffect(() => { inputRef.current?.focus(); }, []);

  // Auto-redirect to dashboard 2 s after a successful activation
  useEffect(() => {
    if (result?.ok) {
      const t = setTimeout(() => router.push("/dashboard"), 2000);
      return () => clearTimeout(t);
    }
  }, [result, router]);

  async function handleActivate() {
    const trimmed = key.trim().toUpperCase();
    if (!trimmed) return;

    setLoading(true);
    setResult(null);

    try {
      const token = await getToken();
      const reqHeaders: Record<string, string> = { "Content-Type": "application/json" };
      if (token) reqHeaders["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`${API}/api/license/activate`, {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify({
          key:         trimmed,
          fingerprint: getBrowserFingerprint(),
          hostname:    window.location.hostname,
          platform:    "web",
        }),
      });

      const body = await res.json();

      if (res.ok) {
        setResult({ ok: true, plan: body.plan, license_expires_at: body.license_expires_at });
      } else {
        setResult({
          ok:      false,
          error:   body.error   ?? "UNKNOWN",
          message: body.message ?? "Activation failed. Please try again.",
          retry_after_seconds: body.retry_after_seconds,
        });
      }
    } catch {
      setResult({
        ok:      false,
        error:   "NETWORK_ERROR",
        message: "Could not reach the server. Check your connection and try again.",
      });
    } finally {
      setLoading(false);
    }
  }

  const errorMessage =
    result && !result.ok
      ? ERROR_MESSAGES[result.error] ?? result.message
      : null;

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-4"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Logo */}
      <div className="mb-8 text-center">
        <span
          className="text-2xl font-bold tracking-tight"
          style={{ color: "var(--accent)", fontFamily: "'JetBrains Mono', monospace" }}
        >
          GeM<span style={{ color: "var(--text-secondary)" }}>/tender</span>
        </span>
      </div>

      {/* Card */}
      <div
        className="w-full max-w-md rounded-xl p-8 space-y-6"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-bright)",
        }}
      >
        {/* Heading */}
        <div className="space-y-1">
          <h1
            className="text-xl font-bold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            Activate Trial License
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Enter the key your administrator issued to start your 7-day free trial.
          </p>
        </div>

        {/* Success state */}
        {result?.ok && (
          <div
            className="rounded-lg px-4 py-3 text-sm font-mono space-y-1"
            style={{
              background: "rgba(16,185,129,0.08)",
              border: "1px solid #10B981",
              color: "#10B981",
            }}
          >
            <div className="font-semibold">✓ License activated</div>
            <div style={{ color: "var(--text-secondary)" }}>
              Plan: <span className="capitalize">{result.plan}</span> · License valid until{" "}
              {new Date(result.license_expires_at).toLocaleDateString("en-IN", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              Redirecting to dashboard…
            </div>
          </div>
        )}

        {/* Error state */}
        {errorMessage && (
          <div
            className="rounded-lg px-4 py-3 text-sm"
            style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid #EF4444",
              color: "#F87171",
            }}
          >
            {errorMessage}
            {result && !result.ok && result.retry_after_seconds && (
              <span className="block text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                Try again in {result.retry_after_seconds}s
              </span>
            )}
          </div>
        )}

        {/* Input + button */}
        {!result?.ok && (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label
                htmlFor="license-key"
                className="text-xs font-mono uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                License Key
              </label>
              <input
                id="license-key"
                ref={inputRef}
                type="text"
                value={key}
                onChange={(e) => {
                  setResult(null);
                  setKey(e.target.value);
                }}
                onKeyDown={(e) => e.key === "Enter" && !loading && handleActivate()}
                placeholder="XXXX-XXXX-XXXX-XXXX"
                spellCheck={false}
                autoComplete="off"
                className="w-full text-sm px-4 py-3 rounded-lg font-mono outline-none transition-all"
                style={{
                  background: "var(--bg-elevated)",
                  border: `1px solid ${errorMessage ? "#EF4444" : "var(--border-bright)"}`,
                  color: "var(--text-primary)",
                  letterSpacing: "0.08em",
                }}
              />
            </div>

            <button
              onClick={handleActivate}
              disabled={loading || !key.trim()}
              className="w-full text-sm px-4 py-3 rounded-lg font-semibold transition-opacity disabled:opacity-50 "
              style={{ background: "#FFFFFF", color: "#0F1117" }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="inline-block w-3.5 h-3.5 border-2 border-[#0F1117] border-t-transparent rounded-full animate-spin" />
                  Activating…
                </span>
              ) : (
                "Activate License"
              )}
            </button>
          </div>
        )}

        {/* Divider + alternate path */}
        {!result?.ok && (
          <div className="pt-2 text-center space-y-2">
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Don&apos;t have a key?
            </p>
            <Link
              href="/dashboard/billing"
              className="text-xs font-mono transition-opacity hover:opacity-80"
              style={{ color: "var(--accent)" }}
            >
              Subscribe directly via PhonePe →
            </Link>
          </div>
        )}
      </div>

      {/* Footer */}
      <p className="mt-6 text-xs" style={{ color: "var(--text-muted)" }}>
        Already have access?{" "}
        <Link
          href="/dashboard"
          className="hover:opacity-80 transition-opacity"
          style={{ color: "var(--text-secondary)" }}
        >
          Go to dashboard
        </Link>
      </p>
    </div>
  );
}
