"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const THREE_DAYS_MS = 3 * 24 * 60 * 60 * 1000;
const ONE_HOUR_MS   = 60 * 60 * 1000;

function buildLabel(expiresAt: string): { text: string; urgent: boolean } | null {
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms > THREE_DAYS_MS) return null; // more than 3 days — no banner

  if (ms <= 0) return { text: "has expired", urgent: true };

  const totalMins = Math.floor(ms / 60_000);
  const hours     = Math.floor(totalMins / 60);
  const mins      = totalMins % 60;
  const days      = Math.floor(hours / 24);

  if (days >= 1) return { text: `expires in ${days} day${days !== 1 ? "s" : ""}`, urgent: false };
  if (hours >= 1) return { text: `expires in ${hours}h ${mins}m`, urgent: ms < ONE_HOUR_MS };
  return { text: `expires in ${mins}m`, urgent: true };
}

export default function ExpiryBanner({
  expiresAt,
  reason,
}: {
  expiresAt: string | null;
  reason: string | null;
}) {
  const [state, setState] = useState<{ text: string; urgent: boolean } | null>(null);

  useEffect(() => {
    if (!expiresAt) return;
    setState(buildLabel(expiresAt));
    const id = setInterval(() => setState(buildLabel(expiresAt)), 60_000);
    return () => clearInterval(id);
  }, [expiresAt]);

  if (!state || !expiresAt) return null;

  const noun = reason === "subscribed" ? "Subscription" : "License";

  return (
    <div
      className="flex items-center justify-between px-8 py-2.5 text-sm shrink-0"
      style={{
        background: state.urgent ? "rgba(245,158,11,0.18)" : "rgba(245,158,11,0.10)",
        borderBottom: "1px solid rgba(245,158,11,0.30)",
      }}
    >
      <span style={{ color: "var(--accent)" }}>
        ⚠ {noun} {state.text} — upgrade to keep access.
      </span>
      <Link
        href="/dashboard/billing"
        className="text-xs font-semibold font-mono px-3 py-1 rounded-md transition-opacity hover:opacity-80"
        style={{
          background: "var(--accent)",
          color: "#0F1117",
        }}
      >
        Upgrade now →
      </Link>
    </div>
  );
}
