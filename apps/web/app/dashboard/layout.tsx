import { auth, currentUser } from "@clerk/nextjs/server";
import { headers } from "next/headers";
import Image from "next/image";
import { redirect } from "next/navigation";
import AccessWatchdog from "@/components/AccessWatchdog";
import DashboardSidebar from "@/components/DashboardSidebar";
import ExpiryBanner from "@/components/ExpiryBanner";

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
  // Billing page is always reachable — expired users must be able to pay.
  const pathname = headers().get("x-pathname") ?? "";
  const isBillingPage = pathname.startsWith("/dashboard/billing");

  const token = await getToken();
  // Admins default to true — their access is never gated by license/subscription.
  // Regular users default to false until the API confirms active access.
  let hasAccess = isAdmin;
  let accessExpiresAt: string | null = null;
  let accessReason: string | null = null;

  if (!isAdmin && token) {
    const access = await getAccessStatus(token);

    if (!isBillingPage && access !== null && !access.has_access) {
      if (access.reason === "trial_expired") {
        redirect("/dashboard/billing?reason=trial_expired");
      } else {
        // no_access — user has never activated a license key
        redirect("/activate?reason=no_license");
      }
    }

    if (access !== null && access.has_access) {
      hasAccess = true;
      accessExpiresAt = access.expires_at ?? null;
      accessReason = access.reason;
    }
    // If access is null (API unreachable): hasAccess stays false.
    // AccessWatchdog will call check() but fail open on network error,
    // so users are not incorrectly blocked when the backend is briefly down.
  }

  return (
    <div className="min-h-screen flex relative z-10">
      {/* Sidebar — client component; disables gated links when hasAccess is false */}
      <DashboardSidebar hasAccess={hasAccess} isAdmin={isAdmin} />

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

        {/* Watchdog: redirects to billing the moment a license expires mid-session,
            and immediately on client-side navigation when access is already denied.
            Not rendered for admins — they are always granted full access. */}
        {!isAdmin && <AccessWatchdog expiresAt={accessExpiresAt} hasAccess={hasAccess} />}
        {/* Countdown banner — visible when ≤ 3 days remain; updates every minute */}
        {!isAdmin && <ExpiryBanner expiresAt={accessExpiresAt} reason={accessReason} />}

        <main className="flex-1 p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
