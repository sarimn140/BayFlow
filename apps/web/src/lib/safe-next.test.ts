import { describe, expect, it } from 'vitest'

import { safeNextPath } from './safe-next'

describe('safeNextPath', () => {
  it.each([
    ['/pos', '/pos'],
    ['/bookings/bk-002?tab=estimate#lines', '/bookings/bk-002?tab=estimate#lines'],
    ['/pos/shops/new', '/pos/shops/new'],
  ])('keeps the in-app path %s', (next, expected) => {
    expect(safeNextPath(next)).toBe(expected)
  })

  it.each([
    null,
    undefined,
    '',
    'pos',
    'https://evil.example/pos',
    '//evil.example',
    '/\\evil.example',
    '/\t/evil.example',
    '/\n/evil.example',
    'javascript:alert(1)',
  ])('refuses %j', (next) => {
    expect(safeNextPath(next)).toBeNull()
  })
})
