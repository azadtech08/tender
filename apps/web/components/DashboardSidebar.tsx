"use client";

import { UserButton } from "@clerk/nextjs";
import Link from "next/link";

const GATED_LINKS = [
  { href: "/dashboard",             label: "Jobs",        icon: "⚡" },
  { href: "/dashboard/live-search", label: "Live Search", icon: "🔍" },
  { href: "/dashboard/tenders",     label: "Tenders",     icon: "📋" },
  { href: "/dashboard/alerts",      label: "Alerts",      icon: "🔔" },
];

export default function DashboardSidebar({
  hasAccess,
  isAdmin,
}: {
  hasAccess: boolean;
  isAdmin: boolean;
}) {
  // Regular users with no active license/subscription cannot access gated routes.
  const gatedBlocked = !hasAccess && !isAdmin;

  return (
    <aside
      className="w-56 flex flex-col py-6 px-3 shrink-0"
      style={{
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* Logo */}
      <div className="px-3 mb-8">
        <span
          className="text-base font-bold tracking-tight"
          style={{ color: "var(--accent)", fontFamily: "'JetBrains Mono', monospace" }}
        >
          GeM<span style={{ color: "var(--text-secondary)" }}>/tender</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5">
        {/* Gated links — Jobs, Tenders, Alerts */}
        {GATED_LINKS.map((link) =>
          gatedBlocked ? (
            <span
              key={link.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm select-none"
              style={{
                color: "var(--text-muted)",
                opacity: 0.4,
                cursor: "not-allowed",
              }}
              title="Activate a license or subscribe to access this section"
            >
              <span className="text-base leading-none">{link.icon}</span>
              <span className="font-medium">{link.label}</span>
            </span>
          ) : (
            <Link
              key={link.href}
              href={link.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              <span className="text-base leading-none">{link.icon}</span>
              <span className="font-medium">{link.label}</span>
            </Link>
          )
        )}

        {/* Billing — always accessible so expired users can pay */}
        <Link
          href="/dashboard/billing"
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
          style={{ color: "var(--text-secondary)" }}
        >
          <span className="text-base leading-none">💳</span>
          <span className="font-medium">Billing</span>
        </Link>

        {/* Admin link — only for tenzo_admin role users */}
        {isAdmin && (
          <Link
            href="/admin/licenses"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors mt-4"
            style={{
              color: "#F87171",
              borderTop: "1px dashed var(--border)",
              paddingTop: "14px",
            }}
          >
            <span className="text-base leading-none">🔑</span>
            <span className="font-medium">Admin · Licenses</span>
          </Link>
        )}
      </nav>

      {/* User button */}
      <div
        className="mt-auto flex items-center gap-3 px-3 pt-4"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <UserButton />
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Account
        </span>
      </div>
    </aside>
  );
}
