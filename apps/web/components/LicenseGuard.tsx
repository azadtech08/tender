"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LicenseGuard({ children }: { children: React.ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.replace("/sign-in");
      return;
    }

    async function check() {
      try {
        const token = await getToken();
        const res = await fetch("/api-backend/api/license/status", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          cache: "no-store",
        });
        if (!res.ok) {
          router.replace("/activate");
          return;
        }
        const data = await res.json();
        if (!data.active) {
          router.replace("/activate");
          return;
        }
        setChecked(true);
      } catch {
        // Network error — fail open so a brief API blip doesn't lock everyone out.
        setChecked(true);
      }
    }

    check();
  }, [isLoaded, isSignedIn, getToken, router]);

  if (!checked) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--bg-base)" }}
      >
        <span style={{ color: "var(--text-muted)", fontFamily: "'JetBrains Mono', monospace" }}>
          Verifying license…
        </span>
      </div>
    );
  }

  return <>{children}</>;
}
