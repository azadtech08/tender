"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const API = "/api-backend";

const PLANS = [
  { id: "free",     name: "Free",     price: "₹0",       features: ["3 runs/month", "50 tenders/run"] },
  { id: "starter",  name: "Starter",  price: "₹1,499",   features: ["30 runs/month", "200 tenders/run", "XLSX export"] },
  { id: "pro",      name: "Pro",      price: "₹4,999",   features: ["150 runs/month", "500 tenders/run", "AI summaries", "Schedules"] },
  { id: "business", name: "Business", price: "₹14,999",  features: ["600 runs/month", "Unlimited tenders", "Priority support"] },
];

type PlanData = {
  plan: string;
  status: string;
  cancel_at_period_end: boolean;
  current_period_end: string | null;
};

type UsageData = {
  runs: number;
  tenders: number;
  ai_summaries: number;
};

export default function BillingPage() {
  const { getToken } = useAuth();
  const searchParams = useSearchParams();
  const [planData, setPlanData] = useState<PlanData | null>(null);
  const [usageData, setUsageData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgradingPlan, setUpgradingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<"success" | "cancelled" | "pending" | null>(null);

  // Read ?payment= query param set by PhonePe redirect
  useEffect(() => {
    const p = searchParams.get("payment");
    if (p === "success") setPaymentStatus("success");
    else if (p === "cancelled") setPaymentStatus("cancelled");
    else if (p === "pending") setPaymentStatus("pending");
  }, [searchParams]);

  useEffect(() => {
    async function load() {
      const token = await getToken();
      const headers = { Authorization: `Bearer ${token}` };
      const [planRes, usageRes] = await Promise.all([
        fetch(`${API}/api/billing/plan`, { headers }),
        fetch(`${API}/api/billing/usage`, { headers }),
      ]);
      if (planRes.ok) setPlanData(await planRes.json());
      if (usageRes.ok) setUsageData(await usageRes.json());
      setLoading(false);
    }
    load();
  }, []);

  async function handleUpgrade(plan: string) {
    setError(null);
    setUpgradingPlan(plan);
    try {
      const token = await getToken();
      const res = await fetch(`${API}/api/billing/phonepe/initiate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          plan,
          success_path: "/dashboard/billing?payment=success",
          cancel_path: "/dashboard/billing?payment=cancelled",
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Error ${res.status}`);
      }

      const { redirect_url } = await res.json();
      // Redirect user to PhonePe hosted payment page
      window.location.href = redirect_url;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Payment initiation failed");
      setUpgradingPlan(null);
    }
  }

  if (loading) return <div className="text-slate-500 text-sm">Loading…</div>;

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Billing</h1>
      <p className="text-slate-500 text-sm mb-6">
        Current plan:{" "}
        <span className="font-semibold text-slate-800 capitalize">
          {planData?.plan ?? "—"}
        </span>
        {planData?.status === "past_due" && (
          <span className="ml-2 text-red-500 text-xs">(payment overdue)</span>
        )}
      </p>

      {/* Payment return banners */}
      {paymentStatus === "success" && (
        <div className="mb-6 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
          ✓ Payment successful! Your plan will be updated within a few seconds.
        </div>
      )}
      {paymentStatus === "cancelled" && (
        <div className="mb-6 rounded-lg bg-yellow-50 border border-yellow-200 px-4 py-3 text-sm text-yellow-800">
          Payment was cancelled. You can try again anytime.
        </div>
      )}
      {paymentStatus === "pending" && (
        <div className="mb-6 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-800">
          Payment is being processed. Refresh this page in a moment.
        </div>
      )}
      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Usage summary */}
      {usageData && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Runs (all time)",        value: usageData.runs },
            { label: "Tenders (all time)",     value: usageData.tenders },
            { label: "AI summaries (all time)", value: usageData.ai_summaries },
          ].map((u) => (
            <div key={u.label} className="bg-white rounded-xl border border-slate-200 p-4 text-center">
              <div className="text-2xl font-bold text-slate-900">{u.value}</div>
              <div className="text-xs text-slate-500 mt-1">{u.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Plan cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {PLANS.map((p) => {
          const isCurrent = planData?.plan === p.id;
          const isUpgrading = upgradingPlan === p.id;
          return (
            <div
              key={p.id}
              className={`bg-white rounded-xl border p-5 flex flex-col ${
                isCurrent ? "border-blue-500 ring-2 ring-blue-200" : "border-slate-200"
              }`}
            >
              <div className="font-bold text-lg text-slate-900 mb-1">{p.name}</div>
              <div className="text-2xl font-bold text-blue-600 mb-3">
                {p.price}
                <span className="text-sm text-slate-400 font-normal">/mo</span>
              </div>
              <ul className="text-sm text-slate-600 space-y-1 mb-4 flex-1">
                {p.features.map((f) => <li key={f}>✓ {f}</li>)}
              </ul>

              {isCurrent ? (
                <div className="text-center text-sm text-blue-600 font-semibold py-2">
                  ✓ Current plan
                </div>
              ) : p.id !== "free" ? (
                <button
                  onClick={() => handleUpgrade(p.id)}
                  disabled={!!upgradingPlan}
                  className="text-sm bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg py-2 flex items-center justify-center gap-2"
                >
                  {isUpgrading ? (
                    <>
                      <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Redirecting…
                    </>
                  ) : (
                    "Buy with PhonePe"
                  )}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
