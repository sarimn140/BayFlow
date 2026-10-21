import { describe, expect, it } from 'vitest'

import {
  INITIAL_BOOKINGS,
  INITIAL_PARTS,
  INITIAL_PURCHASE_ORDERS,
  INITIAL_SERVICES,
  INITIAL_SHOPS,
  INITIAL_TEAM,
  type MockBooking,
  type MockPart,
} from '@/lib/mock-data'

import {
  attentionQueue,
  countByPhase,
  dayLabel,
  greetingAt,
  inventoryHealth,
  listOf,
  longDate,
  openJobs,
  overviewKpis,
  overviewSummary,
  recentlyUpdated,
  safeTimeZone,
  scheduledOn,
  setupState,
  slotMinutes,
  sortTeam,
  updatedAgo,
} from './overview-data'

const LAHORE = 'shop-lahore-auto-care'
const TZ = 'Asia/Karachi'
const bookings = INITIAL_BOOKINGS.filter((b) => b.shopId === LAHORE)
const team = INITIAL_TEAM.filter((m) => m.shopId === LAHORE)
const shop = INITIAL_SHOPS.find((s) => s.id === LAHORE)!

function booking(overrides: Partial<MockBooking>): MockBooking {
  return { ...bookings[0]!, ...overrides }
}

function part(overrides: Partial<MockPart>): MockPart {
  return { ...INITIAL_PARTS[0]!, ...overrides }
}

describe('overviewKpis (E-31 today + lib/kpis groups)', () => {
  it('counts the seeded Lahore shop', () => {
    expect(overviewKpis(bookings, '2026-10-10', TZ)).toEqual({
      needsSaAction: 2,
      inProgress: 3,
      readyForPickup: 1,
      completedToday: 0,
      completedTotal: 1,
      scheduledToday: 1,
    })
  })

  it("counts a booking completed today on the shop's calendar, not UTC's", () => {
    // 20:30 UTC on the 9th is 01:30 on the 10th in Karachi.
    const done = booking({ status: 'COMPLETED', updatedAt: '2026-10-09T20:30:00Z' })
    expect(overviewKpis([done], '2026-10-10', TZ).completedToday).toBe(1)
    expect(overviewKpis([done], '2026-10-09', TZ).completedToday).toBe(0)
  })

  it("leaves cancelled bookings off today's schedule and ignores bad timestamps", () => {
    const cancelled = booking({ status: 'CANCELLED', scheduledDate: '2026-10-10' })
    const broken = booking({ status: 'COMPLETED', updatedAt: 'not a date' })
    const kpis = overviewKpis([cancelled, broken], '2026-10-10', TZ)
    expect(kpis.scheduledToday).toBe(0)
    expect(kpis.completedToday).toBe(0)
    expect(kpis.completedTotal).toBe(1)
  })
})

describe('openJobs (API OPEN_JOB_EXCLUDED_STATUSES)', () => {
  it('counts open bookings where the member is technician, parts person or QC picker', () => {
    expect(openJobs('usr-imran', bookings)).toBe(2) // IN_REPAIR, QC_PENDING; COMPLETED is closed
    expect(openJobs('usr-hamza', bookings)).toBe(1) // AWAITING_CUSTOMER; READY_FOR_PICKUP is not open
    expect(openJobs('usr-sara', bookings)).toBe(0) // QC picker of READY_FOR_PICKUP and COMPLETED only
  })

  it('counts the parts person and the QC picker too', () => {
    const parts = booking({ status: 'PARTS_ORDERED', assignedPartsPersonId: 'usr-usman' })
    const qc = booking({ status: 'QC_IN_PROGRESS', qcInspectorId: 'usr-hina' })
    expect(openJobs('usr-usman', [parts, qc])).toBe(1)
    expect(openJobs('usr-hina', [parts, qc])).toBe(1)
  })
})

describe('sortTeam', () => {
  it('orders by role (glossary §2.1), then name', () => {
    expect(sortTeam(team).map((m) => m.name)).toEqual([
      'Fatima Raza',
      'Bilal',
      'Hamza',
      'Imran',
      'Usman',
      'Hina',
      'Sara',
    ])
  })
})

describe('setupState (OverviewSetup)', () => {
  const services = INITIAL_SERVICES.filter((s) => s.shopId === LAHORE)

  it('is complete for the seeded shop', () => {
    expect(setupState(shop, services, team, INITIAL_PARTS)).toEqual({
      hasServices: true,
      hasTeam: true,
      hasParts: true,
      isListed: true,
    })
  })

  it('needs an active service, an active member besides the owner, a part and a listing', () => {
    const owner = team.filter((m) => m.role === 'OWNER')
    const inactiveTech = { ...team[2]!, is_active: false }
    expect(
      setupState(
        { is_listed: false },
        services.map((s) => ({ ...s, is_active: false })),
        [...owner, inactiveTech],
        [],
      ),
    ).toEqual({ hasServices: false, hasTeam: false, hasParts: false, isListed: false })
  })
})

describe('countByPhase (status_counts by StatusPhase)', () => {
  it('returns all seven phases with every status, zeros included', () => {
    const phases = countByPhase(bookings)
    expect(phases.map((p) => p.phase)).toEqual([
      'INTAKE',
      'INSPECTION',
      'ESTIMATE',
      'PARTS',
      'REPAIR_QC',
      'HANDOVER',
      'CLOSED',
    ])
    expect(phases.flatMap((p) => p.statuses)).toHaveLength(17)
    expect(phases.reduce((sum, p) => sum + p.total, 0)).toBe(bookings.length)
    expect(phases.find((p) => p.phase === 'REPAIR_QC')?.total).toBe(2)
    expect(phases.find((p) => p.phase === 'PARTS')?.total).toBe(0)
  })
})

describe('attentionQueue and recentlyUpdated', () => {
  it('lists bookings waiting on an advisor, longest wait first', () => {
    expect(attentionQueue(bookings).map((b) => b.reference)).toEqual(['BF-2026-005', 'BF-2026-004'])
  })

  it('lists the most recently updated bookings first, up to the limit', () => {
    expect(recentlyUpdated(bookings, 3).map((b) => b.reference)).toEqual([
      'BF-2026-002',
      'BF-2026-001',
      'BF-2026-004',
    ])
    expect(recentlyUpdated(bookings)).toHaveLength(5)
  })
})

describe("slotMinutes and today's schedule", () => {
  it('reads 12-hour and 24-hour slot labels', () => {
    expect(slotMinutes('09:00 am')).toBe(540)
    expect(slotMinutes('12:00 am')).toBe(0)
    expect(slotMinutes('12:30 pm')).toBe(750)
    expect(slotMinutes('02:00 PM')).toBe(840)
    expect(slotMinutes('14:00')).toBe(840)
    expect(slotMinutes('soon')).toBe(Number.MAX_SAFE_INTEGER)
  })

  it('lists the day by slot time, without cancelled bookings', () => {
    const day = [
      booking({ id: 'a', scheduledDate: '2026-10-10', scheduledTime: '02:00 pm' }),
      booking({ id: 'b', scheduledDate: '2026-10-10', scheduledTime: '09:00 am' }),
      booking({
        id: 'c',
        scheduledDate: '2026-10-10',
        scheduledTime: '11:00 am',
        status: 'CANCELLED',
      }),
      booking({ id: 'd', scheduledDate: '2026-10-11', scheduledTime: '08:00 am' }),
    ]
    expect(scheduledOn(day, '2026-10-10').map((b) => b.id)).toEqual(['b', 'a'])
  })
})

describe('inventoryHealth (OverviewInventory, D45)', () => {
  it('sums the seeded stock and counts open purchase orders', () => {
    const parts = INITIAL_PARTS.filter((p) => p.shopId === LAHORE)
    const health = inventoryHealth(parts, INITIAL_PURCHASE_ORDERS)
    expect(health).toMatchObject({
      partsCount: 6,
      lowCount: 0,
      outCount: 0,
      stockValue: 153_200,
      openPurchaseOrders: 1,
      restock: [],
    })
  })

  it('judges stock on what is available and lists OUT first, then the least available', () => {
    const parts = [
      part({ id: 'ok', sku: 'A', on_hand: 9, reserved: 0, reorder_level: 2 }),
      part({ id: 'low-reserved', sku: 'B', on_hand: 5, reserved: 4, reorder_level: 2 }),
      part({ id: 'low', sku: 'C', on_hand: 2, reserved: 0, reorder_level: 2 }),
      part({ id: 'out', sku: 'D', on_hand: 1, reserved: 1, reorder_level: 1 }),
    ]
    const health = inventoryHealth(parts, [])
    expect(health.lowCount).toBe(3)
    expect(health.outCount).toBe(1)
    expect(health.restock.map((p) => p.id)).toEqual(['out', 'low-reserved', 'low'])
  })
})

describe('copy helpers', () => {
  it('joins lists in plain English', () => {
    expect(listOf(['Parts'])).toBe('Parts')
    expect(listOf(['Inspection', 'Parts', 'Closed'])).toBe('Inspection, Parts and Closed')
  })

  it("summarises the floor, or says why there's nothing to say", () => {
    const kpis = overviewKpis(bookings, '2026-10-10', TZ)
    expect(overviewSummary(kpis, bookings.length)).toBe(
      "3 jobs in progress, 2 bookings waiting on a service advisor and 1 booking on today's schedule.",
    )
    expect(overviewSummary(overviewKpis([], '2026-10-10', TZ), 0)).toMatch(/^No bookings yet/)
    const quiet = overviewKpis([booking({ status: 'COMPLETED' })], '2026-10-10', TZ)
    expect(overviewSummary(quiet, 1)).toBe('Nothing is waiting on your team right now.')
  })

  it("greets by the shop's local hour and dates in the shop's zone", () => {
    expect(greetingAt('2026-10-10T03:00:00Z', TZ)).toBe('Good morning') // 08:00
    expect(greetingAt('2026-10-10T08:00:00Z', TZ)).toBe('Good afternoon') // 13:00
    expect(greetingAt('2026-10-10T14:00:00Z', TZ)).toBe('Good evening') // 19:00
    expect(greetingAt('2026-10-09T22:00:00Z', TZ)).toBe('Good evening') // 03:00
    expect(longDate('2026-10-09T20:30:00Z', TZ)).toBe('Saturday, 10 October')
  })

  it('falls back to the default shop zone for an unknown one', () => {
    expect(safeTimeZone('Asia/Karachi')).toBe('Asia/Karachi')
    expect(safeTimeZone('Not/AZone')).toBe('Asia/Karachi')
    expect(safeTimeZone(undefined)).toBe('Asia/Karachi')
  })
})

describe('date labels of stored values', () => {
  const now = new Date('2026-10-10T12:00:00Z')

  it('formats good values', () => {
    expect(dayLabel('2026-10-09')).toBe('Fri 9 Oct')
    expect(updatedAgo('2026-10-10T09:00:00Z', now)).toBe('Updated 3 hours ago')
  })

  it('never throws on a value that is not a date', () => {
    expect(dayLabel('someday')).toBe('someday')
    expect(updatedAgo('not a date', now)).toBe('')
  })
})
