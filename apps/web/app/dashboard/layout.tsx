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

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = auth();
  if (!userId) redirect("/sign-in");

  // Show an Admin link only to users with the tenzo_admin role.
  const user = await currentUser();
  const isAdmin =
    (user?.publicMetadata as { role?: string } | undefined)?.role === "tenzo_admin";

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
          <UserButton afterSignOutUrl="/" />
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

        <main className="flex-1 p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
