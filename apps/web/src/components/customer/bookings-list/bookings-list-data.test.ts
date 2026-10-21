import { describe, expect, it } from 'vitest'

import { INITIAL_BOOKINGS, INITIAL_SHOPS, type MockBooking } from '@/lib/mock-data'

import {
  compareActive,
  comparePast,
  customerActionOf,
  joinNames,
  shopNowKey,
  suspendedShopNames,
  toListItems,
  type ListContext,
} from './bookings-list-data'

const LAHORE = 'shop-lahore-auto-care'
/** Sat 10 Oct 2026, 05:48 in Lahore (UTC+5): before BF-2026-004's 9:00 am slot. */
const EARLY = '2026-10-10T00:48:00.000Z'
/** Sat 10 Oct 2026, 10:00 in Lahore: BF-2026-004's slot has started. */
const LATER = '2026-10-10T05:00:00.000Z'

const isActive = (b: MockBooking) => b.status !== 'COMPLETED' && b.status !== 'CANCELLED'

function context(overrides: Partial<ListContext> = {}): ListContext {
  return { shops: INITIAL_SHOPS, suspensions: {}, nowIso: EARLY, ...overrides }
}

function booking(id: string, overrides: Partial<MockBooking> = {}): MockBooking {
  return { ...INITIAL_BOOKINGS.find((b) => b.id === id)!, ...overrides }
}

describe('customerActionOf', () => {
  it('asks for the estimate decision and the pick-up confirmation only', () => {
    expect(customerActionOf('AWAITING_CUSTOMER', false)).toBe('approve-estimate')
    expect(customerActionOf('READY_FOR_PICKUP', false)).toBe('complete')
    for (const status of ['PENDING', 'CONFIRMED', 'ESTIMATE_REJECTED', 'COMPLETED'] as const) {
      expect(customerActionOf(status, false)).toBeNull()
    }
  })

  it('asks for nothing while the shop is suspended (D96)', () => {
    expect(customerActionOf('AWAITING_CUSTOMER', true)).toBeNull()
    expect(customerActionOf('READY_FOR_PICKUP', true)).toBeNull()
  })
})

describe('shopNowKey', () => {
  it('is the shop-local date and 24-hour time', () => {
    expect(shopNowKey(EARLY, 'Asia/Karachi')).toBe('2026-10-10 05:48')
    expect(shopNowKey('2026-10-09T19:00:00.000Z', 'Asia/Karachi')).toBe('2026-10-10 00:00')
    expect(shopNowKey('2026-10-10T14:30:00.000Z', 'Asia/Karachi')).toBe('2026-10-10 19:30')
  })

  it('is null for a timezone Intl does not know', () => {
    expect(shopNowKey(EARLY, 'Mars/Olympus_Mons')).toBeNull()
  })
})

describe('toListItems', () => {
  it('finds the shop, its suspension, the action, the estimate and whether the slot is ahead', () => {
    const [item] = toListItems([booking('bk-004')], context())
    expect(item).toMatchObject({
      shopName: 'Lahore Auto Care',
      shopSuspended: false,
      action: null,
      estimate: null,
      upcoming: true,
    })
    expect(item?.shop?.id).toBe(LAHORE)
  })

  it('treats a slot that has started as not upcoming, and nothing as upcoming before mount', () => {
    expect(toListItems([booking('bk-004')], context({ nowIso: LATER }))[0]?.upcoming).toBe(false)
    expect(toListItems([booking('bk-004')], context({ nowIso: null }))[0]?.upcoming).toBe(false)
  })

  it('keeps the booking’s shop name when the shop is gone, and drops actions when suspended', () => {
    const [gone] = toListItems([booking('bk-002')], context({ shops: [] }))
    expect(gone?.shopName).toBe('Lahore Auto Care')
    expect(gone?.shop).toBeUndefined()

    const [suspended] = toListItems(
      [booking('bk-002')],
      context({ suspensions: { [LAHORE]: { at: EARLY } } }),
    )
    expect(suspended).toMatchObject({ shopSuspended: true, action: null, estimate: 'pending' })
  })
})

describe('list order (spec 10 C-01)', () => {
  // Lahore Auto Care's active bookings: one of each case the order has to handle (the seeded
  // bookings at other shops are further upcoming slots of other customers).
  const active = INITIAL_BOOKINGS.filter((b) => b.shopId === LAHORE && isActive(b))

  it('puts what needs the customer first, then upcoming slots, then the latest updates', () => {
    const early = toListItems(active, context()).sort(compareActive)
    expect(early.map((i) => i.booking.id)).toEqual([
      'bk-002',
      'bk-005',
      'bk-004',
      'bk-001',
      'bk-003',
    ])

    const later = toListItems(active, context({ nowIso: LATER })).sort(compareActive)
    expect(later.map((i) => i.booking.id)).toEqual([
      'bk-002',
      'bk-005',
      'bk-001',
      'bk-004',
      'bk-003',
    ])
  })

  it('orders upcoming slots soonest first', () => {
    const items = toListItems(
      [
        booking('bk-004', { id: 'late', scheduledDate: '2026-10-12', scheduledTime: '02:00 pm' }),
        booking('bk-004', { id: 'soon', scheduledDate: '2026-10-12', scheduledTime: '09:00 am' }),
        booking('bk-004', { id: 'today', scheduledDate: '2026-10-10', scheduledTime: '11:00 am' }),
      ],
      context(),
    ).sort(compareActive)
    expect(items.map((i) => i.booking.id)).toEqual(['today', 'soon', 'late'])
  })

  it('no longer puts a suspended shop’s estimate first', () => {
    const items = toListItems(active, context({ suspensions: { [LAHORE]: {} } })).sort(
      compareActive,
    )
    expect(items[0]?.booking.id).toBe('bk-004')
  })

  it('lists past bookings most recently closed first', () => {
    const past = toListItems(
      [
        booking('bk-006'),
        booking('bk-004', { status: 'CANCELLED', updatedAt: '2026-10-10T00:30:00.000Z' }),
      ],
      context(),
    ).sort(comparePast)
    expect(past.map((i) => i.booking.id)).toEqual(['bk-004', 'bk-006'])
  })
})

describe('suspended shops notice', () => {
  it('names each suspended shop once', () => {
    const items = toListItems(
      INITIAL_BOOKINGS.filter(isActive),
      context({ suspensions: { [LAHORE]: {} } }),
    )
    expect(suspendedShopNames(items)).toEqual(['Lahore Auto Care'])
    expect(suspendedShopNames(toListItems(INITIAL_BOOKINGS, context()))).toEqual([])
  })

  it('joins names as a sentence', () => {
    expect(joinNames([])).toBe('')
    expect(joinNames(['A'])).toBe('A')
    expect(joinNames(['A', 'B'])).toBe('A and B')
    expect(joinNames(['A', 'B', 'C'])).toBe('A, B and C')
  })
})
