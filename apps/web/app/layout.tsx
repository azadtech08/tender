import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "GeM Tender Intelligence",
  description: "AI-powered Government e-Marketplace tender discovery and analysis",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en" className="dark">
        <body className="min-h-screen relative z-10">{children}</body>
      </html>
    </ClerkProvider>
  );
}
