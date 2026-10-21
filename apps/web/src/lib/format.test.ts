import { describe, expect, it } from 'vitest'

import {
  DEFAULT_SHOP_TZ,
  formatDate,
  formatDateTime,
  formatPKR,
  formatRelative,
  formatSlot,
  formatTime,
  shopDateKey,
} from './format'

const NBSP = ' '
/** ICU builds differ in which space they use before "am"/"pm"; compare plain spaces. */
const plain = (text: string) => text.replace(/[  ]/g, ' ')

describe('formatPKR (D41, WEB-01)', () => {
  it('formats API decimal strings in whole rupees with a non-breaking space after "Rs"', () => {
    expect(formatPKR('16100.00')).toBe(`Rs${NBSP}16,100`)
    expect(formatPKR('16600.00')).toBe(`Rs${NBSP}16,600`)
    expect(formatPKR('900.00')).toBe(`Rs${NBSP}900`)
    expect(formatPKR('0.00')).toBe(`Rs${NBSP}0`)
  })

  it('accepts numbers', () => {
    expect(formatPKR(6500)).toBe(`Rs${NBSP}6,500`)
  })

  it('is exactly the D41 formatter', () => {
    const d41 = new Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })
    for (const amount of ['5200.00', '3500.00', '1234567.00']) {
      expect(formatPKR(amount)).toBe(d41.format(Number(amount)))
    }
  })

  it('shows no decimals and rounds paisa half-expand (labour lines may carry paisa)', () => {
    expect(formatPKR('16100.50')).toBe(`Rs${NBSP}16,101`)
    expect(formatPKR('16100.49')).toBe(`Rs${NBSP}16,100`)
  })

  it('has no float drift up to the numeric(12,2) maximum', () => {
    expect(formatPKR('9999999999.00')).toBe(`Rs${NBSP}9,999,999,999`)
  })

  it('rejects empty and non-numeric amounts instead of showing a wrong price', () => {
    expect(() => formatPKR('')).toThrow(RangeError)
    expect(() => formatPKR('  ')).toThrow(RangeError)
    expect(() => formatPKR('abc')).toThrow(RangeError)
    expect(() => formatPKR(Number.NaN)).toThrow(RangeError)
    expect(() => formatPKR(Number.POSITIVE_INFINITY)).toThrow(RangeError)
  })
})

describe('dates and times in the shop timezone (D38, WEB-02)', () => {
  // 05:00 UTC = 10:00 in Asia/Karachi (UTC+5, no DST).
  const slotStart = '2026-10-16T05:00:00Z'

  it('defaults to Asia/Karachi', () => {
    expect(DEFAULT_SHOP_TZ).toBe('Asia/Karachi')
  })

  it('formats the date', () => {
    expect(plain(formatDate(slotStart))).toBe('Fri, 16 Oct 2026')
  })

  it('formats the time', () => {
    expect(plain(formatTime(slotStart))).toBe('10:00 am')
    expect(plain(formatTime('2026-10-16T09:31:00Z'))).toBe('2:31 pm')
  })

  it('formats date and time together; formatSlot is the same format', () => {
    expect(plain(formatDateTime(slotStart))).toBe('Fri, 16 Oct 2026 · 10:00 am')
    expect(formatSlot(slotStart)).toBe(formatDateTime(slotStart))
  })

  it('uses the shop day, not the UTC day, around midnight', () => {
    // 19:30 UTC on the 16th is 00:30 on the 17th in Karachi.
    expect(plain(formatDate('2026-10-16T19:30:00Z'))).toBe('Sat, 17 Oct 2026')
    expect(plain(formatTime('2026-10-16T19:30:00Z'))).toBe('12:30 am')
  })

  it('accepts Date objects and other timezones', () => {
    expect(plain(formatTime(new Date(slotStart), 'UTC'))).toBe('5:00 am')
  })

  it('builds the YYYY-MM-DD availability key in shop time', () => {
    expect(shopDateKey('2026-10-16T18:59:59Z')).toBe('2026-10-16')
    expect(shopDateKey('2026-10-16T19:00:00Z')).toBe('2026-10-17')
    expect(shopDateKey(new Date('2026-01-05T00:00:00Z'))).toBe('2026-01-05')
  })

  it('rejects invalid timestamps', () => {
    expect(() => formatDate('not-a-date')).toThrow(RangeError)
    expect(() => shopDateKey('2026-13-45')).toThrow(RangeError)
  })
})

describe('formatRelative', () => {
  const now = new Date('2026-10-16T10:00:00Z')

  it('describes past and future times', () => {
    expect(formatRelative('2026-10-16T09:55:00Z', now)).toBe('5 minutes ago')
    expect(formatRelative('2026-10-15T10:00:00Z', now)).toBe('yesterday')
    expect(formatRelative('2026-10-16T12:00:00Z', now)).toBe('in 2 hours')
    expect(formatRelative(now, now)).toBe('now')
  })
})
