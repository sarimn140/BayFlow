import { describe, expect, it } from 'vitest'

import {
  INITIAL_BOOKINGS,
  INITIAL_PARTS,
  INITIAL_SHOPS,
  INITIAL_TEAM,
  type MockBooking,
  type MockPart,
  type MockTeamMember,
} from '@/lib/mock-data'

import {
  DEFAULT_WORKING_HOURS,
  SLOT_DURATIONS,
  availableSlug,
  durationLabel,
  isValidPhone,
  listOf,
  newShopSlug,
  ownedShopIds,
  ownerSummary,
  parseCapacity,
  plural,
  safeTimeZone,
  slotsPerDay,
  summaryTotals,
  validateShop,
  weeklyHours,
  workspaceHref,
  workspacesOf,
  type ShopDraft,
} from './hub-data'

const FATIMA = 'fatima.owner@bayflow.test'
const LAHORE = 'shop-lahore-auto-care'
const RAZA = 'shop-raza-auto-works'
/** Saturday 10 October 2026, noon in Karachi. */
const NOW = new Date('2026-10-10T07:00:00Z')

const member = (id: string): MockTeamMember => INITIAL_TEAM.find((m) => m.id === id)!

describe('workspacesOf (S-02: the /me memberships)', () => {
  it("lists Fatima's two shops by name, as their Owner", () => {
    expect(
      workspacesOf(FATIMA, INITIAL_TEAM, INITIAL_SHOPS).map((w) => [w.shop.id, w.role]),
    ).toEqual([
      [LAHORE, 'OWNER'],
      [RAZA, 'OWNER'],
    ])
  })

  it('gives a staff member their role in their shop', () => {
    expect(
      workspacesOf('bilal.sa@bayflow.test', INITIAL_TEAM, INITIAL_SHOPS).map((w) => [
        w.shop.id,
        w.role,
      ]),
    ).toEqual([[LAHORE, 'SERVICE_ADVISOR']])
  })

  it('leaves out inactive memberships, unknown shops and other people', () => {
    const bilal = member('usr-bilal')
    const team = [
      { ...bilal, is_active: false },
      { ...bilal, id: 'mbr-gone', shopId: 'shop-that-does-not-exist' },
    ]
    expect(workspacesOf(bilal.email, team, INITIAL_SHOPS)).toEqual([])
    expect(workspacesOf('nobody@bayflow.test', INITIAL_TEAM, INITIAL_SHOPS)).toEqual([])
  })

  it("opens the role's home in that shop (S-04)", () => {
    const shop = INITIAL_SHOPS.find((s) => s.id === LAHORE)!
    expect(workspaceHref({ shop, role: 'OWNER' })).toBe(`/pos/shops/${LAHORE}/overview`)
    expect(workspaceHref({ shop, role: 'SERVICE_ADVISOR' })).toBe(`/pos/shops/${LAHORE}/bookings`)
    expect(workspaceHref({ shop, role: 'TECHNICIAN' })).toBe(`/pos/shops/${LAHORE}/jobs`)
    expect(workspaceHref({ shop, role: 'PARTS_PERSON' })).toBe(`/pos/shops/${LAHORE}/parts`)
    expect(workspaceHref({ shop, role: 'QC_INSPECTOR' })).toBe(`/pos/shops/${LAHORE}/qc`)
  })
})

describe('ownedShopIds', () => {
  it('counts active Owner memberships only', () => {
    expect([...ownedShopIds(FATIMA, INITIAL_TEAM)].sort()).toEqual([LAHORE, RAZA])
    expect(ownedShopIds('bilal.sa@bayflow.test', INITIAL_TEAM).size).toBe(0)
    const team = INITIAL_TEAM.map((m) => (m.shopId === RAZA ? { ...m, is_active: false } : m))
    expect([...ownedShopIds(FATIMA, team)]).toEqual([LAHORE])
  })
})

describe('ownerSummary (O-07, E-32)', () => {
  const base = {
    shops: INITIAL_SHOPS,
    ownedIds: ownedShopIds(FATIMA, INITIAL_TEAM),
    bookings: INITIAL_BOOKINGS,
    parts: INITIAL_PARTS,
    suspendedIds: new Set<string>(),
    now: NOW,
  }

  it("counts each owned shop's day, by name", () => {
    const { rows, suspended } = ownerSummary(base)
    expect(suspended).toEqual([])
    expect(rows.map(({ shop, ...counts }) => [shop.id, counts])).toEqual([
      [LAHORE, { today: 1, needsAction: 2, inProgress: 3, ready: 1, lowStock: 0 }],
      // Spec 11: Raza Auto Works' pending booking (12 Oct) and its own catalogue, where the
      // ignition coil, front brake disc and battery are LOW and the AC gas is OUT.
      [RAZA, { today: 0, needsAction: 1, inProgress: 0, ready: 0, lowStock: 4 }],
    ])
    expect(summaryTotals(rows)).toEqual({
      today: 1,
      needsAction: 3,
      inProgress: 3,
      ready: 1,
      lowStock: 4,
    })
  })

  it('leaves a suspended shop out of the rows and the totals, and names it (D99)', () => {
    const { rows, suspended } = ownerSummary({ ...base, suspendedIds: new Set([LAHORE]) })
    expect(rows.map((row) => row.shop.id)).toEqual([RAZA])
    expect(suspended.map((shop) => shop.id)).toEqual([LAHORE])
    // Only Raza Auto Works' pending booking is left in the totals.
    expect(summaryTotals(rows).needsAction).toBe(1)
  })

  it("reads today on each shop's own calendar (D38)", () => {
    // 20:00 UTC on 9 October is already 10 October in Karachi (UTC+5).
    const evening = new Date('2026-10-09T20:00:00Z')
    expect(ownerSummary({ ...base, now: evening }).rows[0]!.today).toBe(1)
    const utcShops = INITIAL_SHOPS.map((s) => (s.id === LAHORE ? { ...s, timezone: 'UTC' } : s))
    // Still 9 October in UTC: BF-2026-001 and BF-2026-002.
    expect(ownerSummary({ ...base, shops: utcShops, now: evening }).rows[0]!.today).toBe(2)
  })

  it("leaves cancelled bookings out of today's count", () => {
    const bookings: MockBooking[] = INITIAL_BOOKINGS.map((b) =>
      b.id === 'bk-004' ? { ...b, status: 'CANCELLED' } : b,
    )
    expect(ownerSummary({ ...base, bookings }).rows[0]!.today).toBe(0)
  })

  it('counts low and out-of-stock parts per shop (D45)', () => {
    const lahorePart = INITIAL_PARTS.find((p) => p.shopId === LAHORE)!
    const parts: MockPart[] = [
      ...INITIAL_PARTS,
      { ...lahorePart, id: 'low', sku: 'LOW-1', on_hand: 3, reserved: 1, reorder_level: 2 },
      { ...lahorePart, id: 'raza', sku: 'RZ-1', shopId: RAZA, on_hand: 0, reorder_level: 1 },
    ]
    // Raza Auto Works: its 4 seeded LOW/OUT parts (spec 11) and the OUT part added here.
    expect(ownerSummary({ ...base, parts }).rows.map((row) => row.lowStock)).toEqual([1, 5])
  })

  it('falls back to the default time zone for an unknown one', () => {
    expect(safeTimeZone('Not/AZone')).toBe('Asia/Karachi')
    expect(safeTimeZone(undefined)).toBe('Asia/Karachi')
    expect(safeTimeZone('UTC')).toBe('UTC')
    const broken = INITIAL_SHOPS.map((s) => (s.id === LAHORE ? { ...s, timezone: 'Mars/Base' } : s))
    expect(ownerSummary({ ...base, shops: broken }).rows[0]!.today).toBe(1)
  })
})

describe('slots (S-03)', () => {
  it('offers every multiple of 15 from 15 to 240 minutes (D37)', () => {
    expect(SLOT_DURATIONS).toHaveLength(16)
    expect(SLOT_DURATIONS[0]).toBe(15)
    expect(SLOT_DURATIONS.at(-1)).toBe(240)
    expect(SLOT_DURATIONS.every((m) => m % 15 === 0)).toBe(true)
  })

  it('names a duration in words', () => {
    expect(durationLabel(15)).toBe('15 minutes')
    expect(durationLabel(60)).toBe('1 hour')
    expect(durationLabel(75)).toBe('1 hour 15 minutes')
    expect(durationLabel(120)).toBe('2 hours')
    expect(durationLabel(225)).toBe('3 hours 45 minutes')
  })

  it('fits whole slots between 09:00 and 18:00, like the booking wizard', () => {
    expect(slotsPerDay(60)).toBe(9)
    expect(slotsPerDay(75)).toBe(7)
    expect(slotsPerDay(240)).toBe(2)
    expect(slotsPerDay(0)).toBe(0)
    expect(slotsPerDay(Number.NaN)).toBe(0)
  })

  it('summarises the default week in two lines', () => {
    expect(weeklyHours(DEFAULT_WORKING_HOURS)).toEqual([
      { days: 'Monday to Saturday', hours: '09:00 am – 06:00 pm' },
      { days: 'Sunday', hours: null },
    ])
  })

  it('joins two days with "and" and keeps hours it cannot read', () => {
    expect(
      weeklyHours([
        { day: 'Friday', hours: '10:00 - 14:30' },
        { day: 'Saturday', hours: 'Closed', is_closed: true },
        { day: 'Sunday', hours: 'Closed', is_closed: true },
        { day: 'Monday', hours: 'by appointment' },
      ]),
    ).toEqual([
      { days: 'Friday', hours: '10:00 am – 02:30 pm' },
      { days: 'Saturday and Sunday', hours: null },
      { days: 'Monday', hours: 'by appointment' },
    ])
  })
})

describe('validateShop (ShopCreate rules, spec 09 §2.10)', () => {
  const valid: ShopDraft = {
    name: 'Falcon Auto Works',
    address: 'Shop 2, Ferozepur Road',
    city: 'Lahore',
    phone: '+92 42 3500 1234',
    slotDuration: '60',
    slotCapacity: '2',
  }

  it('accepts a complete shop', () => {
    expect(validateShop(valid)).toEqual({})
  })

  it('needs a name, address, city and phone that are not blank', () => {
    expect(validateShop({ ...valid, name: '   ', address: '', city: ' ', phone: '' })).toEqual({
      name: 'Enter the name of your shop.',
      address: 'Enter the street address.',
      city: 'Enter the city.',
      phone: 'Enter a phone number customers can call.',
    })
  })

  it('caps the name at 120, the address at 255 and the city at 80 characters', () => {
    expect(
      validateShop({
        ...valid,
        name: 'n'.repeat(120),
        address: 'a'.repeat(255),
        city: 'c'.repeat(80),
      }),
    ).toEqual({})
    expect(
      Object.keys(
        validateShop({
          ...valid,
          name: 'n'.repeat(121),
          address: 'a'.repeat(256),
          city: 'c'.repeat(81),
        }),
      ),
    ).toEqual(['name', 'address', 'city'])
  })

  it('checks the phone like the API (7–20 characters, 7–15 digits)', () => {
    for (const phone of [
      '0300-1234567',
      '+92 42 35789011',
      ' 042 3578 9011 ',
      '1234567',
      '+123456789012345',
    ]) {
      expect(isValidPhone(phone)).toBe(true)
    }
    for (const phone of [
      '123456',
      '+------',
      '92+3001234567',
      'call 0300-1234567',
      '+1234567890123456',
      '1234567890 1234567890',
    ]) {
      expect(isValidPhone(phone)).toBe(false)
    }
    expect(validateShop({ ...valid, phone: '12-34' }).phone).toBe(
      'Use 7 to 15 digits; spaces, hyphens and a leading + are allowed.',
    )
  })

  it('takes a slot length from the list and 1 to 50 cars', () => {
    expect(validateShop({ ...valid, slotDuration: '50' }).slotDuration).toBe(
      'Choose a slot length.',
    )
    for (const capacity of ['0', '51', '2.5', '', '-1', '1e1']) {
      expect(parseCapacity(capacity)).toBeNull()
      expect(validateShop({ ...valid, slotCapacity: capacity }).slotCapacity).toBe(
        'Enter a whole number from 1 to 50.',
      )
    }
    expect(parseCapacity(' 7 ')).toBe(7)
    expect(parseCapacity('50')).toBe(50)
  })
})

describe('new shop slug (spec 03 §4.9)', () => {
  it('kebab-cases the name', () => {
    expect(newShopSlug('  Ali & Sons Motors ', INITIAL_SHOPS)).toBe('ali-sons-motors')
  })

  it('adds a suffix instead of taking an existing shop', () => {
    expect(newShopSlug('Lahore Auto Care', INITIAL_SHOPS)).toBe('lahore-auto-care-2')
    const taken = [...INITIAL_SHOPS, { id: 'shop-lahore-auto-care-2', slug: 'lahore-auto-care-2' }]
    expect(availableSlug('lahore-auto-care', taken)).toBe('lahore-auto-care-3')
    expect(availableSlug('falcon', INITIAL_SHOPS)).toBe('falcon')
  })

  it('falls back to a timestamp for a name without letters or digits', () => {
    expect(newShopSlug('!!!', [])).toMatch(/^shop-\d+$/)
  })
})

describe('copy helpers', () => {
  it('pluralises and lists', () => {
    expect(plural(1, 'shop')).toBe('1 shop')
    expect(plural(2, 'shop')).toBe('2 shops')
    expect(listOf(['A'])).toBe('A')
    expect(listOf(['A', 'B'])).toBe('A and B')
    expect(listOf(['A', 'B', 'C'])).toBe('A, B and C')
  })
})
