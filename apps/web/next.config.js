/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce a self-contained output bundle — required by the production Dockerfile
  output: "standalone",

  // Proxy API requests to the FastAPI backend in development
  async rewrites() {
    return [
      {
        source: "/api-backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
