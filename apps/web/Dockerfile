# BayFlow web — image for `docker compose up` only. Vercel builds the web app itself (spec 07).
# Pattern: official Next.js with-docker example (Node 24 slim, Corepack pnpm, standalone output,
# non-root `node` user, `node server.js`).

FROM node:24-slim AS base
# Corepack installs the pnpm version pinned in package.json ("packageManager").
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable pnpm
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time values: the /api rewrite target and NEXT_PUBLIC_* are fixed during `next build` (D7).
ARG API_BASE_URL=http://api:4000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:4000/api/v1/ws
ARG NEXT_PUBLIC_CALL_PROVIDER_URL=
ENV API_BASE_URL=$API_BASE_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_CALL_PROVIDER_URL=$NEXT_PUBLIC_CALL_PROVIDER_URL \
    NEXT_OUTPUT=standalone
RUN pnpm build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
RUN mkdir .next && chown node:node .next
# The standalone server does not copy public/ or .next/static; once copied next to server.js
# it serves them itself.
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
