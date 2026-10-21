import { beforeEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_USER,
  INITIAL_BOOKINGS,
  INITIAL_PARTS,
  INITIAL_PURCHASE_ORDERS,
  INITIAL_SHOPS,
  INITIAL_TEAM,
  adjustPartStock,
  getBookingById,
  getBookings,
  getCurrentUser,
  getCustomerBooking,
  getCustomerBookings,
  getInventory,
  getPurchaseOrders,
  getServices,
  getShopById,
  getShopBySlug,
  getShops,
  getTeamMembers,
  readSeedSnapshot,
  saveBooking,
  savePart,
  savePurchaseOrder,
  saveService,
  saveShop,
  saveTeamMember,
  setCurrentUser,
} from './mock-data'

const SHOP_ID = 'shop-lahore-auto-care'

/** Every read the screens hand to `useMockStore` as a useSyncExternalStore snapshot. */
const SNAPSHOT_READS: ReadonlyArray<[string, () => unknown]> = [
  ['getCurrentUser()', () => getCurrentUser()],
  ['getShops()', () => getShops()],
  ['getShopBySlug(slug)', () => getShopBySlug('lahore-auto-care')],
  ['getShopById(id)', () => getShopById(SHOP_ID)],
  ['getServices()', () => getServices()],
  ['getServices(shopId)', () => getServices(SHOP_ID)],
  ['getBookings()', () => getBookings()],
  ['getBookings(shopId)', () => getBookings(SHOP_ID)],
  ['getBookingById(id)', () => getBookingById('bk-001')],
  ['getInventory()', () => getInventory()],
  ['getInventory(shopId)', () => getInventory(SHOP_ID)],
  ['getPurchaseOrders()', () => getPurchaseOrders()],
  ['getPurchaseOrders(shopId)', () => getPurchaseOrders(SHOP_ID)],
  ['getTeamMembers()', () => getTeamMembers()],
  ['getTeamMembers(shopId)', () => getTeamMembers(SHOP_ID)],
  ['getCustomerBookings(email)', () => getCustomerBookings('ayesha.customer@bayflow.test')],
  [
    'getCustomerBooking(id, email)',
    () => getCustomerBooking('bk-002', 'ayesha.customer@bayflow.test'),
  ],
]

/** One write per stored key, so every read above then comes from localStorage. */
function writeEveryKey() {
  saveShop({ ...getShopById(SHOP_ID)!, phone: '+92 42 0000000' })
  const service = getServices(SHOP_ID)[0]!
  saveService({ ...service, description: `${service.description} (edited)` })
  saveBooking({ ...getBookingById('bk-001')!, status: 'QC_PENDING' })
  adjustPartStock('part-of-01', 1)
  savePurchaseOrder({ ...getPurchaseOrders(SHOP_ID)[0]!, supplier: 'Test Supplier' })
  const member = getTeamMembers(SHOP_ID)[0]!
  saveTeamMember({ ...member, name: `${member.name} (edited)` })
  setCurrentUser({ ...DEFAULT_USER, name: 'Imran', role: 'TECHNICIAN' })
}

beforeEach(() => {
  localStorage.clear()
})

describe('mock store snapshots are referentially stable', () => {
  it.each(SNAPSHOT_READS)('%s: same reference on repeated seed reads', (_, read) => {
    expect(read()).toBeDefined()
    expect(Object.is(read(), read())).toBe(true)
  })

  it.each(SNAPSHOT_READS)('%s: same reference on repeated stored reads', (_, read) => {
    writeEveryKey()
    expect(read()).toBeDefined()
    expect(Object.is(read(), read())).toBe(true)
  })

  it.each(SNAPSHOT_READS)('%s: same reference on repeated server-snapshot reads', (_, read) => {
    writeEveryKey()
    expect(Object.is(readSeedSnapshot(read), readSeedSnapshot(read))).toBe(true)
  })
})

describe('mock store writes publish new snapshots', () => {
  /** `act(n)` writes data unique to round `n`; `changed(n)` checks the reads now show it. */
  const WRITES: ReadonlyArray<{
    write: string
    reads: ReadonlyArray<() => unknown>
    act: (n: number) => void
    changed: (n: number) => boolean
  }> = [
    {
      write: 'saveShop',
      reads: [getShops, () => getShopById(SHOP_ID), () => getShopBySlug('lahore-auto-care')],
      act: (n) => saveShop({ ...getShopById(SHOP_ID)!, phone: `+92 42 000000${n}` }),
      changed: (n) => getShopById(SHOP_ID)?.phone === `+92 42 000000${n}`,
    },
    {
      write: 'saveService',
      reads: [() => getServices(), () => getServices(SHOP_ID)],
      act: (n) => saveService({ ...getServices(SHOP_ID)[0]!, name: `Edited service ${n}` }),
      changed: (n) => getServices(SHOP_ID)[0]?.name === `Edited service ${n}`,
    },
    {
      write: 'saveBooking',
      reads: [() => getBookings(), () => getBookings(SHOP_ID), () => getBookingById('bk-001')],
      act: (n) => saveBooking({ ...getBookingById('bk-001')!, inspectionNotes: `Note ${n}` }),
      changed: (n) => getBookingById('bk-001')?.inspectionNotes === `Note ${n}`,
    },
    {
      write: 'adjustPartStock',
      reads: [() => getInventory(), () => getInventory(SHOP_ID)],
      act: () => adjustPartStock('part-of-01', 3),
      changed: (n) =>
        getInventory(SHOP_ID).find((p) => p.id === 'part-of-01')?.on_hand ===
        INITIAL_PARTS.find((p) => p.id === 'part-of-01')!.on_hand + 3 * n,
    },
    {
      write: 'savePurchaseOrder',
      reads: [() => getPurchaseOrders(), () => getPurchaseOrders(SHOP_ID)],
      act: (n) =>
        savePurchaseOrder({ ...getPurchaseOrders(SHOP_ID)[0]!, supplier: `Supplier ${n}` }),
      changed: (n) => getPurchaseOrders(SHOP_ID)[0]?.supplier === `Supplier ${n}`,
    },
    {
      write: 'saveTeamMember',
      reads: [() => getTeamMembers(), () => getTeamMembers(SHOP_ID)],
      act: (n) => saveTeamMember({ ...getTeamMembers(SHOP_ID)[0]!, name: `Member ${n}` }),
      changed: (n) => getTeamMembers(SHOP_ID)[0]?.name === `Member ${n}`,
    },
    {
      write: 'setCurrentUser',
      reads: [getCurrentUser],
      act: (n) => setCurrentUser({ ...DEFAULT_USER, name: `User ${n}` }),
      changed: (n) => getCurrentUser().name === `User ${n}`,
    },
  ]

  it.each(WRITES)('$write: reads return a new reference holding the new data', (entry) => {
    // Round 1 writes over the seed data, round 2 over data already stored by round 1.
    for (const n of [1, 2]) {
      const before = entry.reads.map((read) => read())
      entry.act(n)
      entry.reads.forEach((read, i) => expect(read(), `write ${n}, read #${i}`).not.toBe(before[i]))
      expect(entry.changed(n), `write ${n}`).toBe(true)
    }
  })

  it('never mutates the previous snapshot or the seed data', () => {
    const seedPart = INITIAL_PARTS.find((p) => p.id === 'part-of-01')!
    const onHand = seedPart.on_hand
    const before = getInventory(SHOP_ID)

    adjustPartStock('part-of-01', 5)
    saveBooking({ ...INITIAL_BOOKINGS[0]!, id: 'bk-new', reference: 'BF-NEW' })

    expect(before.find((p) => p.id === 'part-of-01')?.on_hand).toBe(onHand)
    expect(seedPart.on_hand).toBe(onHand)
    expect(getInventory(SHOP_ID).find((p) => p.id === 'part-of-01')?.on_hand).toBe(onHand + 5)
    expect(INITIAL_BOOKINGS.some((b) => b.id === 'bk-new')).toBe(false)
    expect(getBookingById('bk-new')?.reference).toBe('BF-NEW')
  })

  it('picks up a write made in another tab', () => {
    const before = getBookings(SHOP_ID)
    const changed = INITIAL_BOOKINGS.map((b) =>
      b.id === 'bk-004' ? { ...b, status: 'CANCELLED' as const } : b,
    )
    localStorage.setItem('bf:bookings', JSON.stringify(changed)) // what another tab's write leaves

    const after = getBookings(SHOP_ID)
    expect(after).not.toBe(before)
    expect(after.find((b) => b.id === 'bk-004')?.status).toBe('CANCELLED')
    expect(getBookings(SHOP_ID)).toBe(after)
  })

  it('serves seed data as the server snapshot, whatever is stored', () => {
    writeEveryKey()
    expect(readSeedSnapshot(getCurrentUser)).toBe(DEFAULT_USER)
    expect(readSeedSnapshot(() => getBookingById('bk-001'))).toBe(
      INITIAL_BOOKINGS.find((b) => b.id === 'bk-001'),
    )
    expect(getCurrentUser().role).toBe('TECHNICIAN')
  })
})

const OTHER_SHOPS = INITIAL_SHOPS.filter((shop) => shop.id !== SHOP_ID).map((shop) => shop.id)
const NEW_SHOP = 'shop-falcon-auto-works'

describe('tenant isolation (D20): a shop reads and writes only its own records', () => {
  it('never lends a shop another shop’s team, parts or purchase orders', () => {
    for (const shopId of [SHOP_ID, ...OTHER_SHOPS, NEW_SHOP]) {
      expect(
        getTeamMembers(shopId).every((m) => m.shopId === shopId),
        shopId,
      ).toBe(true)
      expect(
        getInventory(shopId).every((p) => p.shopId === shopId),
        shopId,
      ).toBe(true)
      expect(
        getPurchaseOrders(shopId).every((po) => po.shopId === shopId),
        shopId,
      ).toBe(true)
    }
    // A shop created in this browser starts empty: no borrowed staff, stock or orders.
    expect(getTeamMembers(NEW_SHOP)).toEqual([])
    expect(getInventory(NEW_SHOP)).toEqual([])
    expect(getPurchaseOrders(NEW_SHOP)).toEqual([])
  })

  it('keeps an edit to one shop’s member or part out of every other shop', () => {
    const adeel = getTeamMembers('shop-raza-auto-works').find((m) => m.name === 'Adeel Anwar')!
    saveTeamMember({ ...adeel, is_active: false })
    expect(getTeamMembers(SHOP_ID)).toEqual(INITIAL_TEAM.filter((m) => m.shopId === SHOP_ID))

    const clifton = getInventory('shop-clifton-car-clinic').find((p) => p.sku === 'FLT-OIL-01')!
    savePart({ ...clifton, name: 'Oil filter (Clifton)', unit_price: 950 })
    for (const part of INITIAL_PARTS.filter((p) => p.sku === 'FLT-OIL-01' && p !== clifton)) {
      expect(getInventory().find((p) => p.id === part.id)).toEqual(part)
    }
    expect(getInventory().find((p) => p.id === clifton.id)?.name).toBe('Oil filter (Clifton)')
  })

  it('adds stock by SKU to the named shop’s part only, and never guesses between shops', () => {
    const before = (shopId: string) =>
      INITIAL_PARTS.find((p) => p.shopId === shopId && p.sku === 'BRK-DSC-F')!.on_hand
    const updated = adjustPartStock('BRK-DSC-F', 2, 'shop-pindi-auto-garage')
    expect(updated).toMatchObject({ shopId: 'shop-pindi-auto-garage', on_hand: 2 })
    expect(before('shop-pindi-auto-garage')).toBe(0)
    for (const shopId of OTHER_SHOPS.filter((id) => id !== 'shop-pindi-auto-garage')) {
      const part = getInventory(shopId).find((p) => p.sku === 'BRK-DSC-F')!
      expect(part.on_hand, shopId).toBe(before(shopId))
    }
    // Five shops stock BRK-DSC-F: without a shop the SKU names no single part, so nothing changes.
    expect(adjustPartStock('BRK-DSC-F', 5)).toBeUndefined()
    // A SKU only one part carries, or a part id, still works on its own.
    expect(adjustPartStock('OF-TY-01', 1)?.shopId).toBe(SHOP_ID)
    expect(adjustPartStock('part-raza-auto-works-blb-h4', 1)?.on_hand).toBe(11)
  })

  it('keeps purchase order numbers apart per shop', () => {
    const lahoreOrder = INITIAL_PURCHASE_ORDERS[0]!
    savePurchaseOrder({ ...lahoreOrder, id: 'po-raza-1', shopId: 'shop-raza-auto-works' })
    expect(getPurchaseOrders(SHOP_ID)).toEqual(INITIAL_PURCHASE_ORDERS)
    expect(getPurchaseOrders('shop-raza-auto-works').map((po) => po.id)).toEqual(['po-raza-1'])
  })
})

describe('spec 11 seed: every shop has its own team, stock and bookings', () => {
  const ROLE_TAG = {
    OWNER: 'owner',
    SERVICE_ADVISOR: 'sa',
    TECHNICIAN: 'tech',
    QC_INSPECTOR: 'qc',
    PARTS_PERSON: 'parts',
  } as const

  it('seeds the 31 staff accounts and 32 memberships, e-mails as the spec gives them', () => {
    expect(INITIAL_TEAM).toHaveLength(32)
    expect(new Set(INITIAL_TEAM.map((m) => m.email)).size).toBe(31)
    for (const shopId of OTHER_SHOPS) {
      const slug = getShopById(shopId)!.slug
      const team = INITIAL_TEAM.filter((m) => m.shopId === shopId)
      expect(team.map((m) => m.role).sort(), shopId).toEqual([
        'OWNER',
        'PARTS_PERSON',
        'QC_INSPECTOR',
        'SERVICE_ADVISOR',
        'TECHNICIAN',
      ])
      for (const m of team) {
        // Raza Auto Works is Fatima's second shop, so it has no `owner.` account.
        const expected =
          shopId === 'shop-raza-auto-works' && m.role === 'OWNER'
            ? 'fatima.owner@bayflow.test'
            : `${ROLE_TAG[m.role]}.${slug}@bayflow.test`
        expect(m.email).toBe(expected)
      }
    }
    expect(INITIAL_TEAM.filter((m) => m.shopId === SHOP_ID)).toHaveLength(7)
  })

  it('stocks each other shop with the 16-part catalogue at its opening quantities', () => {
    const raza = getInventory('shop-raza-auto-works')
    const pindi = getInventory('shop-pindi-auto-garage')
    for (const shopId of OTHER_SHOPS) expect(getInventory(shopId), shopId).toHaveLength(16)
    // Raza Auto Works after BF-SEED11 (8 → 7 oil filters, 10 → 8 engine oils), no AC gas.
    expect(raza.find((p) => p.sku === 'FLT-OIL-01')).toMatchObject({ on_hand: 7, unit_price: 900 })
    expect(raza.find((p) => p.sku === 'OIL-4L-01')).toMatchObject({ on_hand: 8, reorder_level: 3 })
    expect(raza.find((p) => p.sku === 'AC-R134A')?.on_hand).toBe(0)
    // Pindi Auto Garage is the "needs restocking" shop.
    expect(pindi.filter((p) => p.on_hand === 0).map((p) => p.sku)).toEqual([
      'IGN-COIL-01',
      'FLT-CAB-01',
      'BRK-DSC-F',
    ])
    expect(getInventory(SHOP_ID)).toEqual(INITIAL_PARTS.filter((p) => p.shopId === SHOP_ID))
    expect(getInventory(SHOP_ID)).toHaveLength(6)
  })

  it('gives each other shop’s Service Advisor their own bookings (first login)', () => {
    const statuses = (shopId: string) => getBookings(shopId).map((b) => b.status)
    expect(statuses('shop-raza-auto-works').sort()).toEqual(['COMPLETED', 'PENDING'])
    expect(statuses('shop-clifton-car-clinic')).toEqual(['PENDING'])
    expect(statuses('shop-margalla-motor-works')).toEqual(['PENDING'])
    expect(statuses('shop-pindi-auto-garage')).toEqual(['PENDING'])
    expect(statuses('shop-lyallpur-motors')).toEqual(['COMPLETED'])
    // Their own staff did the work, never Lahore Auto Care's.
    const team = (shopId: string) => INITIAL_TEAM.filter((m) => m.shopId === shopId)
    for (const b of INITIAL_BOOKINGS.filter((b) => b.shopId !== SHOP_ID)) {
      for (const id of [b.assignedTechnicianId, b.assignedPartsPersonId, b.qcInspectorId]) {
        if (id)
          expect(
            team(b.shopId).some((m) => m.id === id),
            `${b.reference} ${id}`,
          ).toBe(true)
      }
    }
  })

  it('gives Ayesha an estimate to approve, a car to collect, a completed and a cancelled booking', () => {
    const ayesha = getCustomerBookings('ayesha.customer@bayflow.test').map((b) => b.status)
    expect(ayesha).toEqual(
      expect.arrayContaining(['AWAITING_CUSTOMER', 'READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED']),
    )
  })
})

describe('customer bookings (D21: a customer sees only their own)', () => {
  const AYESHA = 'ayesha.customer@bayflow.test'

  it('lists only the bookings of that account, matching the e-mail in any case', () => {
    const own = getCustomerBookings(AYESHA)
    expect(own.length).toBeGreaterThan(0)
    expect(own.every((b) => b.customerEmail === AYESHA)).toBe(true)
    expect(own).toEqual(INITIAL_BOOKINGS.filter((b) => b.customerEmail === AYESHA))
    expect(getCustomerBookings('  Ayesha.Customer@BayFlow.test ')).toEqual(own)
  })

  it('finds nothing for staff who never booked as customers, or for no e-mail', () => {
    expect(getCustomerBookings('bilal.sa@bayflow.test')).toEqual([])
    expect(getCustomerBookings('fatima.owner@bayflow.test')).toEqual([])
    expect(getCustomerBookings('')).toEqual([])
  })

  it('opens a booking for its customer only; for anyone else it does not exist', () => {
    expect(getCustomerBooking('bk-002', AYESHA)?.reference).toBe('BF-2026-002')
    expect(getCustomerBooking('BF-2026-002', 'AYESHA.customer@bayflow.test')?.id).toBe('bk-002')
    expect(getCustomerBooking('bk-002', 'zainab.customer@bayflow.test')).toBeUndefined()
    expect(getCustomerBooking('bk-002', 'bilal.sa@bayflow.test')).toBeUndefined()
    expect(getCustomerBooking('bk-404', AYESHA)).toBeUndefined()
  })

  it('follows a booking saved under this e-mail, and drops one moved to another account', () => {
    const before = getCustomerBookings(AYESHA)
    saveBooking({ ...getBookingById('bk-004')!, customerEmail: 'Ayesha.Customer@bayflow.test' })
    expect(getCustomerBookings(AYESHA)).not.toBe(before)
    expect(getCustomerBookings(AYESHA).map((b) => b.id)).toContain('bk-004')
    saveBooking({ ...getBookingById('bk-002')!, customerEmail: 'someone.else@bayflow.test' })
    expect(getCustomerBookings(AYESHA).map((b) => b.id)).not.toContain('bk-002')
  })
})
