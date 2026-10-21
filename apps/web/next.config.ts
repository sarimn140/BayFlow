import type { NextConfig } from 'next'

// VERCEL=1 is a Vercel system variable (build and runtime). Rewrites and NEXT_PUBLIC_* values are
// fixed at build time, so a Vercel build without them would ship a broken app (spec 07).
const isVercelBuild = Boolean(process.env.VERCEL)
for (const name of ['API_BASE_URL', 'NEXT_PUBLIC_WS_URL'] as const) {
  if (isVercelBuild && !process.env[name]) {
    throw new Error(`${name} must be set in the Vercel project settings`)
  }
}

/** Where `/api/*` is proxied to (D7). Local dev and CI fall back to the local API on port 4000. */
const apiBaseUrl = (process.env.API_BASE_URL || 'http://localhost:4000').replace(/\/+$/, '')

/** Spec 04 "Security headers (Tier 1 values)" — every path, including the rewritten `/api/*`. */
export const securityHeaders = [
  { key: 'X-Frame-Options', value: 'DENY' },
  // Only directives that cannot break the app; the full CSP is spec 04 Tier 2.
  {
    key: 'Content-Security-Policy',
    value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  // In-app calling (spec 05 §9) needs the microphone on our own origin only.
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(self), geolocation=()' },
]

const nextConfig: NextConfig = {
  // Minimal Node server for the Docker Compose image only (the Dockerfile sets
  // NEXT_OUTPUT=standalone). Vercel and local `pnpm build` / `pnpm start` use the default output.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  poweredByHeader: false,
  // Tailwind CSS 4 through its Turbopack loader (create-next-app 16.4 default; no PostCSS config).
  turbopack: {
    rules: {
      '*.css': {
        loaders: ['@tailwindcss/turbopack'],
        as: '*.css',
      },
    },
  },
  async headers() {
    return [{ source: '/(.*)', headers: securityHeaders }]
  },
  async rewrites() {
    // Array form = afterFiles: checked after app routes, so nothing may live under app/api/**.
    return [{ source: '/api/:path*', destination: `${apiBaseUrl}/api/:path*` }]
  },
}

export default nextConfig
