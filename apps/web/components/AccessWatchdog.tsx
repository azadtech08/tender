"use client";

import { useAuth } from "@clerk/nextjs";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const API = "/api-backend";
// JS setTimeout overflows at ~24.8 days — cap at 24h and reschedule.
const MAX_TIMER_MS = 24 * 60 * 60 * 1000;
const POLL_MS = 60_000;

export default function AccessWatchdog({
  expiresAt,
  hasAccess,
}: {
  expiresAt: string | null;
  hasAccess: boolean;
}) {
  const { getToken } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let dead = false;

    async function check() {
      if (dead) return;
      // Already on billing — user is where they need to be, never redirect from here.
      if (pathname.startsWith("/dashboard/billing")) return;
      try {
        const token = await getToken();
        if (!token) return; // Clerk session gone — let Clerk middleware handle it
        const res = await fetch(`${API}/api/billing/access-status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || dead) return; // 401 / network error — fail open
        const data = await res.json();
        if (dead) return;
        if (!data.has_access) {
          if (data.reason === "trial_expired") {
            router.push("/dashboard/billing?reason=trial_expired");
          } else {
            router.push("/activate?reason=no_license");
          }
        } else if (data.expires_at) {
          // License may have been extended mid-session — reset timer to new expiry.
          arm(data.expires_at);
        }
      } catch {
        // Network failure — fail open, next poll will retry.
      }
    }

    function arm(exp: string) {
      if (timer) clearTimeout(timer);
      const ms = new Date(exp).getTime() - Date.now();
      if (ms <= 0) { check(); return; }
      timer = setTimeout(() => {
        const remaining = new Date(exp).getTime() - Date.now();
        if (remaining > 0) {
          arm(exp); // Hit the 24h cap — reschedule.
        } else {
          check(); // At/past expiry — confirm with server before redirecting.
        }
      }, Math.min(ms, MAX_TIMER_MS));
    }

    if (!hasAccess) {
      // Server already confirmed no access on this render.
      // Call check() immediately so the correct redirect fires without waiting
      // for a poll cycle. This blocks client-side navigation to protected routes.
      // check() is a no-op when on billing, so the billing page is never trapped.
      check();
    } else {
      // Access is valid — arm the expiry timer and run the safety-net poll.
      if (expiresAt) arm(expiresAt);
      poll = setInterval(check, POLL_MS);
    }

    return () => {
      dead = true;
      if (timer) clearTimeout(timer);
      if (poll) clearInterval(poll);
    };
  }, [expiresAt, hasAccess, pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  return null; // invisible — purely behavioural
}
