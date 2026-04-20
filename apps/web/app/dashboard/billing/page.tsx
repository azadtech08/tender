"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  const [planData, setPlanData] = useState<PlanData | null>(null);
  const [usageData, setUsageData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

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
    const token = await getToken();
    const res = await fetch(`${API}/api/billing/checkout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ plan }),
    });
    if (res.ok) {
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
    }
  }

  async function handleManage() {
    const token = await getToken();
    const res = await fetch(`${API}/api/billing/portal`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ return_path: "/dashboard/billing" }),
    });
    if (res.ok) {
      const { portal_url } = await res.json();
      window.location.href = portal_url;
    }
  }

  if (loading) return <div className="text-slate-500 text-sm">Loading…</div>;

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Billing</h1>
      <p className="text-slate-500 text-sm mb-8">
        Current plan:{" "}
        <span className="font-semibold text-slate-800 capitalize">
          {planData?.plan ?? "—"}
        </span>
        {planData?.status === "past_due" && (
          <span className="ml-2 text-red-500 text-xs">(payment overdue)</span>
        )}
      </p>

      {/* Usage summary */}
      {usageData && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: "Runs", value: usageData.runs },
            { label: "Tenders", value: usageData.tenders },
            { label: "AI summaries", value: usageData.ai_summaries },
          ].map((u) => (
            <div key={u.label} className="bg-white rounded-xl border border-slate-200 p-4 text-center">
              <div className="text-2xl font-bold text-slate-900">{u.value}</div>
              <div className="text-xs text-slate-500 mt-1">{u.label} (all time)</div>
            </div>
          ))}
        </div>
      )}

      {/* Plan cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {PLANS.map((p) => {
          const isCurrent = planData?.plan === p.id;
          return (
            <div
              key={p.id}
              className={`bg-white rounded-xl border p-5 flex flex-col ${
                isCurrent ? "border-blue-500 ring-2 ring-blue-200" : "border-slate-200"
              }`}
            >
              <div className="font-bold text-lg text-slate-900 mb-1">{p.name}</div>
              <div className="text-2xl font-bold text-blue-600 mb-3">{p.price}<span className="text-sm text-slate-400 font-normal">/mo</span></div>
              <ul className="text-sm text-slate-600 space-y-1 mb-4 flex-1">
                {p.features.map((f) => <li key={f}>✓ {f}</li>)}
              </ul>
              {isCurrent ? (
                <button
                  onClick={handleManage}
                  className="text-sm text-slate-600 border border-slate-200 rounded-lg py-2 hover:bg-slate-50"
                >
                  Manage
                </button>
              ) : p.id !== "free" ? (
                <button
                  onClick={() => handleUpgrade(p.id)}
                  className="text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2"
                >
                  Upgrade
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
