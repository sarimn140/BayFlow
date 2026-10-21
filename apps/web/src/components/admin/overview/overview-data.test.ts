import { beforeEach, describe, expect, it } from 'vitest'

import {
  PLATFORM_ADMIN_ACCOUNT,
  getAdminShops,
  getAdminUsers,
  getAuditEvents,
  suspendShop,
} from '@/lib/mock-admin'
import { INITIAL_BOOKINGS, type MockBooking } from '@/lib/mock-data'

import {
  OPEN_PHASES,
  countByPhase,
  dailyActivity,
  dayLabel,
  firstName,
  greetingAt,
  isOpenBooking,
  longDate,
  overviewSummary,
  platformStats,
  shortDayLabel,
} from './overview-data'

/** Saturday 10 October 2026, 10:00 in Karachi. */
const NOW = new Date('2026-10-10T05:00:00Z')
const areeba = { name: PLATFORM_ADMIN_ACCOUNT.name, email: PLATFORM_ADMIN_ACCOUNT.email }

function stats(now = NOW) {
  return platformStats({
    users: getAdminUsers(),
    tenants: getAdminShops(),
    bookings: INITIAL_BOOKINGS,
    audit: getAuditEvents(),
    now,
  })
}

beforeEach(() => {
  localStorage.clear()
})

describe('isOpenBooking', () => {
  it('treats completed and cancelled bookings as finished', () => {
    expect(isOpenBooking('COMPLETED')).toBe(false)
    expect(isOpenBooking('CANCELLED')).toBe(false)
  })

  it('treats every other status as open, ready for pick-up included', () => {
    expect(isOpenBooking('PENDING')).toBe(true)
    expect(isOpenBooking('ESTIMATE_REJECTED')).toBe(true)
    expect(isOpenBooking('READY_FOR_PICKUP')).toBe(true)
  })
})

describe('platformStats (E-61)', () => {
  it('counts the seeded platform', () => {
    const s = stats()
    expect(s.shops).toBe(6)
    expect(s.activeShops).toBe(6)
    expect(s.suspended).toEqual([])
    expect(s.accounts).toBe(getAdminUsers().length)
    expect(s.admins).toBe(1)
    expect(s.customers + s.staff + s.admins).toBe(s.accounts)
    // BF-2026-004 is the only slot on Saturday 10 October.
    expect(s.bookingsToday).toBe(1)
  })

  it('leaves completed bookings out of the open count and the phases', () => {
    const s = stats()
    // Thirteen seeded bookings: three completed (BF-2026-006, -009, -013) and one cancelled
    // (BF-2026-007). Open: Lahore's five, plus the pending booking at each of four other shops.
    expect(s.open).toBe(9)
    expect(s.openByPhase).toEqual([
      { phase: 'INTAKE', count: 5 },
      { phase: 'INSPECTION', count: 0 },
      { phase: 'ESTIMATE', count: 1 },
      { phase: 'PARTS', count: 0 },
      { phase: 'REPAIR_QC', count: 2 },
      { phase: 'HANDOVER', count: 1 },
    ])
    expect(s.openByPhase.reduce((sum, p) => sum + p.count, 0)).toBe(s.open)
  })

  it('counts failed sign-ins of the last 24 hours only', () => {
    // Seeded failures: 9 Oct 03:54, 07:41 and 07:41:30 UTC.
    expect(stats(new Date('2026-10-10T03:00:00Z')).failedSignIns).toBe(3)
    expect(stats(NOW).failedSignIns).toBe(2)
    expect(stats(new Date('2026-10-11T00:00:00Z')).failedSignIns).toBe(0)
  })

  it('does not count a cancelled booking in today’s slots', () => {
    const cancelled: MockBooking = { ...INITIAL_BOOKINGS[0]!, id: 'x', scheduledDate: '2026-10-10' }
    const bookings = [
      ...INITIAL_BOOKINGS,
      cancelled,
      { ...cancelled, id: 'y', status: 'CANCELLED' as const },
    ]
    const s = platformStats({
      users: getAdminUsers(),
      tenants: getAdminShops(),
      bookings,
      audit: getAuditEvents(),
      now: NOW,
    })
    expect(s.bookingsToday).toBe(2)
  })

  it('ranks the busiest shops and lists suspended shops', () => {
    suspendShop('shop-raza-auto-works', 'Unpaid platform invoices', areeba)
    const s = stats()
    expect(s.busiest).toHaveLength(5)
    expect(s.busiest[0]!.shop.id).toBe('shop-lahore-auto-care')
    expect(s.suspended.map((t) => t.shop.id)).toEqual(['shop-raza-auto-works'])
    expect(s.activeShops).toBe(5)
  })
})

describe('dailyActivity', () => {
  it('returns 14 Karachi days, oldest first, ending today', () => {
    const days = dailyActivity(INITIAL_BOOKINGS, [], NOW)
    expect(days).toHaveLength(14)
    expect(days[0]!.day).toBe('2026-09-27')
    expect(days[13]!.day).toBe('2026-10-10')
  })

  it('counts bookings by the day they were created, in Karachi time', () => {
    const days = dailyActivity(INITIAL_BOOKINGS, [], NOW)
    const byDay = Object.fromEntries(days.map((d) => [d.day, d.bookings]))
    // BF-2026-001, -002 and -004, plus the four other shops' pending bookings made that evening.
    expect(byDay['2026-10-09']).toBe(7)
    expect(byDay['2026-10-08']).toBe(2)
    expect(days.reduce((sum, d) => sum + d.bookings, 0)).toBe(
      INITIAL_BOOKINGS.filter((b) => b.createdAt >= '2026-09-26T19:00:00Z').length,
    )
  })

  it('puts an event just after midnight in Karachi on the new day', () => {
    // 19:30 UTC on 9 October is 00:30 on 10 October in Karachi.
    const days = dailyActivity([], [{ occurredAt: '2026-10-09T19:30:00Z' }], NOW)
    expect(days[13]).toEqual({ day: '2026-10-10', bookings: 0, events: 1 })
    expect(days[12]!.events).toBe(0)
  })

  it('skips timestamps that are not dates', () => {
    const days = dailyActivity([], [{ occurredAt: 'not a date' }], NOW)
    expect(days.every((d) => d.events === 0)).toBe(true)
  })
})

describe('countByPhase', () => {
  it('counts every phase in workflow order, zeros included', () => {
    const phases = countByPhase(INITIAL_BOOKINGS)
    expect(phases.map((p) => p.phase)).toEqual([
      'INTAKE',
      'INSPECTION',
      'ESTIMATE',
      'PARTS',
      'REPAIR_QC',
      'HANDOVER',
      'CLOSED',
    ])
    expect(phases.reduce((sum, p) => sum + p.count, 0)).toBe(INITIAL_BOOKINGS.length)
  })

  it('takes a subset of phases', () => {
    expect(countByPhase([], OPEN_PHASES).map((p) => p.phase)).not.toContain('CLOSED')
  })
})

describe('overviewSummary', () => {
  it('says when nothing needs attention', () => {
    const accounts = getAdminUsers().length
    expect(overviewSummary({ ...stats(), failedSignIns: 0 })).toBe(
      `6 shops and ${accounts} accounts on BayFlow, with 9 open bookings. No shop is suspended and no sign-in failed in the last 24 hours.`,
    )
  })

  it('uses the singular for one of a kind', () => {
    const one = { ...stats(), shops: 1, accounts: 1, open: 1, failedSignIns: 1 }
    expect(overviewSummary(one)).toBe(
      '1 shop and 1 account on BayFlow, with 1 open booking. 1 sign-in failed in the last 24 hours.',
    )
  })

  it('names suspended shops and failed sign-ins', () => {
    suspendShop('shop-raza-auto-works', 'Unpaid platform invoices', areeba)
    expect(overviewSummary(stats())).toMatch(
      /1 shop is suspended and 2 sign-ins failed in the last 24 hours\.$/,
    )
  })
})

describe('labels', () => {
  it('greets by the hour in Karachi', () => {
    expect(greetingAt('2026-10-10T03:00:00Z')).toBe('Good morning') // 08:00
    expect(greetingAt('2026-10-10T09:00:00Z')).toBe('Good afternoon') // 14:00
    expect(greetingAt('2026-10-10T14:00:00Z')).toBe('Good evening') // 19:00
    expect(greetingAt('2026-10-09T22:00:00Z')).toBe('Good evening') // 03:00
  })

  it('formats the date and the first name', () => {
    expect(longDate('2026-10-10T05:00:00Z')).toBe('Saturday, 10 October')
    expect(firstName('Areeba Hashmi')).toBe('Areeba')
    expect(firstName('  ')).toBe('there')
  })

  it('formats day keys for the chart', () => {
    expect(dayLabel('2026-10-09')).toBe('Fri 9 Oct')
    expect(shortDayLabel('2026-10-09')).toBe('9 Oct')
    expect(shortDayLabel('nope')).toBe('nope')
  })
})
