import { UserButton } from "@clerk/nextjs";
import { auth, currentUser } from "@clerk/nextjs/server";
import Link from "next/link";
import { redirect } from "next/navigation";

const ADMIN_NAV = [
  { href: "/admin/licenses", label: "Licenses", icon: "🔑" },
  { href: "/dashboard",      label: "← Dashboard", icon: "↩" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = auth();
  if (!userId) redirect("/sign-in");

  const user = await currentUser();
  const role = (user?.publicMetadata as { role?: string } | undefined)?.role;
  if (role !== "tenzo_admin") {
    // Non-admins get bounced back to the dashboard. The backend also
    // enforces this — we mirror the check here for UX.
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen flex relative z-10">
      <aside
        className="w-56 flex flex-col py-6 px-3 shrink-0"
        style={{
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border)",
        }}
      >
        <div className="px-3 mb-8">
          <span
            className="text-base font-bold tracking-tight"
            style={{ color: "var(--accent)", fontFamily: "'JetBrains Mono', monospace" }}
          >
            GeM<span style={{ color: "var(--text-secondary)" }}>/admin</span>
          </span>
          <p
            className="text-[10px] font-mono mt-1 uppercase tracking-wider"
            style={{ color: "var(--text-muted)" }}
          >
            Tenzo · licensing
          </p>
        </div>

        <nav className="flex-1 space-y-0.5">
          {ADMIN_NAV.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors hover:bg-white/[0.04]"
              style={{ color: "var(--text-secondary)" }}
            >
              <span className="text-base leading-none">{link.icon}</span>
              <span className="font-medium">{link.label}</span>
            </Link>
          ))}
        </nav>

        <div
          className="mt-auto flex items-center gap-3 px-3 pt-4"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <UserButton afterSignOutUrl="/" />
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            {user?.emailAddresses?.[0]?.emailAddress ?? "Admin"}
          </span>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header
          className="flex items-center justify-between px-8 py-3 shrink-0"
          style={{
            background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span
            className="text-xs font-mono uppercase tracking-wider px-2 py-1 rounded"
            style={{
              background: "rgba(239, 68, 68, 0.12)",
              color: "#F87171",
              border: "1px solid rgba(239, 68, 68, 0.3)",
            }}
          >
            ⚠ admin mode
          </span>
          <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
            role: tenzo_admin
          </span>
        </header>

        <main className="flex-1 p-8 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
