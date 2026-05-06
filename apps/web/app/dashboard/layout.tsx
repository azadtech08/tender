import { UserButton } from "@clerk/nextjs";
import { auth, currentUser } from "@clerk/nextjs/server";
import Image from "next/image";
import Link from "next/link";
import { redirect } from "next/navigation";

const NAV_LINKS = [
  { href: "/dashboard",          label: "Jobs",     icon: "⚡" },
  { href: "/dashboard/tenders",  label: "Tenders",  icon: "📋" },
  { href: "/dashboard/alerts",   label: "Alerts",   icon: "🔔" },
  { href: "/dashboard/billing",  label: "Billing",  icon: "💳" },
];

// Internal URL used for server-side API calls (bypasses the browser proxy).
const INTERNAL_API =
  process.env.INTERNAL_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

type AccessStatus = {
  has_access: boolean;
  reason: "subscribed" | "trial_active" | "trial_expired" | "no_access";
  days_remaining: number | null;
  expires_at: string | null;
  plan: string | null;
};

async function getAccessStatus(token: string): Promise<AccessStatus | null> {
  try {
    const res = await fetch(`${INTERNAL_API}/api/billing/access-status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    // API unreachable — fail open so a backend hiccup never locks out users.
    return null;
  }
}

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // ── Step 1: Clerk auth ───────────────────────────────────────────────────
  const { userId, getToken } = auth();
  if (!userId) redirect("/sign-in");

  // ── Step 2: Admin role check (must run BEFORE the license gate) ──────────
  // Admins always have full dashboard access — no license or subscription
  // check is applied to them.
  const user = await currentUser();
  const isAdmin =
    (user?.publicMetadata as { role?: string } | undefined)?.role === "tenzo_admin";

  // ── Step 3: License / subscription gate (regular users only) ────────────
  const token = await getToken();
  let trialDaysRemaining: number | null = null;

  if (!isAdmin && token) {
    const access = await getAccessStatus(token);

    if (access !== null && !access.has_access) {
      if (access.reason === "trial_expired") {
        redirect("/dashboard/billing?reason=trial_expired");
      } else {
        // no_access — user has never activated a license key
        redirect("/activate?reason=no_license");
      }
    }

    if (
      access !== null &&
      access.reason === "trial_active" &&
      access.days_remaining !== null &&
      access.days_remaining <= 3
    ) {
      trialDaysRemaining = access.days_remaining;
    }
  }

  const trialLabel =
    trialDaysRemaining === 0
      ? "Trial expires today"
      : trialDaysRemaining === 1
      ? "Trial expires tomorrow"
      : `Trial expires in ${trialDaysRemaining} days`;

  return (
    <div className="min-h-screen flex relative z-10">
      {/* Sidebar */}
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
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              <span className="text-base leading-none">{link.icon}</span>
              <span className="font-medium">{link.label}</span>
            </Link>
          ))}
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

        {/* User */}
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

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header
          className="flex items-center justify-end px-8 py-3 shrink-0"
          style={{
            background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <a
            href="https://ariella.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 opacity-90 hover:opacity-100 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            <span className="text-xs uppercase tracking-wider">Designed by</span>
            <Image
              src="/ariella-logo.png"
              alt="Ariella"
              width={120}
              height={36}
              className="h-9 w-auto bg-white rounded-md px-2 py-1"
              priority
            />
          </a>
        </header>

        {/* Trial expiry banner — shown only when ≤ 3 days remain */}
        {trialDaysRemaining !== null && (
          <div
            className="flex items-center justify-between px-8 py-2.5 text-sm shrink-0"
            style={{
              background: "rgba(245,158,11,0.10)",
              borderBottom: "1px solid rgba(245,158,11,0.30)",
            }}
          >
            <span style={{ color: "var(--accent)" }}>
              ⚠ {trialLabel} — upgrade to keep access.
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
        )}

        <main className="flex-1 p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
