import Image from "next/image";
import Link from "next/link";
import { SignInButton, SignUpButton, SignedIn, SignedOut, UserButton } from "@clerk/nextjs";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 to-slate-800 text-white">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto">
        <span className="text-xl font-bold text-blue-400">GeM Tender</span>
        <div className="flex items-center gap-4">
          <Link href="/dashboard/billing" className="text-sm text-slate-300 hover:text-white">
            Pricing
          </Link>
          <SignedOut>
            <SignInButton mode="modal">
              <button className="text-sm text-slate-300 hover:text-white">Sign in</button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg">
                Get started
              </button>
            </SignUpButton>
          </SignedOut>
          <SignedIn>
            <Link
              href="/dashboard"
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg"
            >
              Dashboard
            </Link>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
        </div>
      </nav>

      {/* Hero */}
      <main className="max-w-6xl mx-auto px-6 py-24 text-center">
        <h1 className="text-5xl font-bold leading-tight mb-6">
          Find GeM tenders before<br />
          <span className="text-blue-400">your competitors do</span>
        </h1>
        <p className="text-xl text-slate-300 mb-10 max-w-2xl mx-auto">
          AI-powered discovery across Government e-Marketplace. Get structured
          tender intelligence — keywords, BOQ, deadlines, values — delivered
          to your inbox the moment they go live.
        </p>
        <SignedOut>
          <SignUpButton mode="modal">
            <button className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl text-lg font-semibold">
              Start for free — no credit card
            </button>
          </SignUpButton>
        </SignedOut>
        <SignedIn>
          <Link
            href="/dashboard"
            className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl text-lg font-semibold"
          >
            Go to dashboard
          </Link>
        </SignedIn>

        {/* Feature grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-20 text-left">
          {[
            {
              icon: "🔍",
              title: "Keyword monitoring",
              body: "Set up keywords once. We scrape GeM continuously and alert you to matching tenders.",
            },
            {
              icon: "📄",
              title: "PDF intelligence",
              body: "Claude AI extracts BOQ, quantities, eligibility criteria, and contact emails from bid documents.",
            },
            {
              icon: "📊",
              title: "Excel export",
              body: "One-click 23-column XLSX export matching the exact format your sales team already uses.",
            },
          ].map((f) => (
            <div key={f.title} className="bg-slate-800 rounded-xl p-6 border border-slate-700">
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="font-semibold text-lg mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm">{f.body}</p>
            </div>
          ))}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-20">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="text-sm text-slate-500">
            © {new Date().getFullYear()} GeM Tender. All rights reserved.
          </span>
          <a
            href="https://ariella.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            <span>Designed by</span>
            <Image
              src="/ariella-logo.png"
              alt="Ariella"
              width={96}
              height={28}
              className="h-7 w-auto bg-white rounded px-1.5 py-0.5"
              priority={false}
            />
          </a>
        </div>
      </footer>
    </div>
  );
}
