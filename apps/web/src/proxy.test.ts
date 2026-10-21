// @vitest-environment node
import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { config, proxy } from './proxy'

describe('proxy (optimistic bf_session gate, spec 09 §2.8)', () => {
  it('redirects to /login with the original path and query in `next`', () => {
    const response = proxy(
      new NextRequest('http://localhost:3000/pos/shops/abc/bookings?status=PENDING'),
    )
    expect(response.status).toBe(307)
    const location = new URL(response.headers.get('location') ?? '')
    expect(location.pathname).toBe('/login')
    expect(location.searchParams.get('next')).toBe('/pos/shops/abc/bookings?status=PENDING')
  })

  it('lets the request through when the session cookie is present (no JWT check)', () => {
    const response = proxy(
      new NextRequest('http://localhost:3000/pos', { headers: { cookie: 'bf_session=opaque' } }),
    )
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it('guards the POS, the customer area and the admin console only', () => {
    expect(config.matcher).toEqual([
      '/pos/:path*',
      '/bookings/:path*',
      '/book/confirmed/:path*',
      '/admin/:path*',
    ])
  })
})
