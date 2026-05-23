/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produce a self-contained output bundle — required by the production Dockerfile
  output: "standalone",

  // API proxy is handled by app/api-backend/[[...path]]/route.ts (route handler).
  // That handler forwards to INTERNAL_API_URL (http://api:8000 inside Docker),
  // preserving the Authorization header. No next.config.js rewrite needed.
};

module.exports = nextConfig;
