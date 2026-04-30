/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce a self-contained output bundle — required by the production Dockerfile
  output: "standalone",

  // Proxy API requests through Next.js to the FastAPI backend via Docker internal DNS.
  // Browser calls /api-backend/... → Next.js server → http://api:8000/...
  // This avoids any IP/port issues on the browser side.
  async rewrites() {
    const dest = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api-backend/:path*",
        destination: `${dest}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
