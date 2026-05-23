# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

COPY apps/web/package*.json ./
RUN npm ci

# ── Stage 2: build the Next.js app ───────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ .

# Build-time env vars (baked into the static bundle)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

# Produce a standalone output bundle for a lean production image
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 3: production runner ────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Least-privilege runtime user
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copy only what the server needs at runtime
COPY --from=builder /app/public          ./public
COPY --from=builder /app/.next/static    ./.next/static
COPY --from=builder /app/.next/standalone ./

# sharp is required for image optimisation in standalone mode
# Install directly — it is not in package.json so cannot be copied from builder
RUN npm install --os=linux --cpu=x64 sharp

# Create cache dir with correct ownership before switching to non-root user
RUN mkdir -p .next/cache && chown -R nextjs:nodejs .next

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
