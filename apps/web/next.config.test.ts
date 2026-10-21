// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'

/** next.config.ts reads the environment at import time, so load a fresh copy per case. */
async function loadConfig(env: Record<string, string | undefined> = {}) {
  vi.resetModules()
  vi.stubEnv('VERCEL', undefined)
  vi.stubEnv('API_BASE_URL', undefined)
  vi.stubEnv('NEXT_PUBLIC_WS_URL', undefined)
  vi.stubEnv('NEXT_OUTPUT', undefined)
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value)
  return import('./next.config')
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('next.config.ts', () => {
  it('sends the spec 04 security headers on every path (SEC-32)', async () => {
    const { default: config } = await loadConfig()
    const rules = await config.headers?.()
    expect(rules).toHaveLength(1)
    expect(rules?.[0]?.source).toBe('/(.*)')
    const headers = Object.fromEntries(
      (rules?.[0]?.headers ?? []).map((header) => [header.key, header.value]),
    )
    expect(headers).toMatchObject({
      'X-Frame-Options': 'DENY',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
    })
    expect(headers['Content-Security-Policy']).toContain("frame-ancestors 'none'")
    expect(config.poweredByHeader).toBe(false)
  })

  it('rewrites /api/* to the local API by default (D7)', async () => {
    const { default: config } = await loadConfig()
    expect(await config.rewrites?.()).toEqual([
      { source: '/api/:path*', destination: 'http://localhost:4000/api/:path*' },
    ])
  })

  it('rewrites to API_BASE_URL without a trailing slash', async () => {
    const { default: config } = await loadConfig({ API_BASE_URL: 'https://api.example.test/' })
    expect(await config.rewrites?.()).toEqual([
      { source: '/api/:path*', destination: 'https://api.example.test/api/:path*' },
    ])
  })

  it('builds standalone output only when NEXT_OUTPUT=standalone (Docker image)', async () => {
    expect((await loadConfig()).default.output).toBeUndefined()
    expect((await loadConfig({ NEXT_OUTPUT: 'standalone' })).default.output).toBe('standalone')
  })

  it('refuses a Vercel build without the build-time variables', async () => {
    await expect(loadConfig({ VERCEL: '1' })).rejects.toThrow('API_BASE_URL must be set')
    await expect(
      loadConfig({ VERCEL: '1', API_BASE_URL: 'https://api.example.test' }),
    ).rejects.toThrow('NEXT_PUBLIC_WS_URL must be set')
  })
})
