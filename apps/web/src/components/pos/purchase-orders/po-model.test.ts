import { beforeEach, describe, expect, it } from 'vitest'

import {
  INITIAL_BOOKINGS,
  INITIAL_PURCHASE_ORDERS,
  adjustPartStock,
  getInventory,
  type MockPart,
  type MockPurchaseOrder,
} from '@/lib/mock-data'

import {
  contentsLabel,
  filterCounts,
  isOpen,
  jobHref,
  lineTotal,
  matchesFilter,
  matchesQuery,
  newPurchaseOrderIdentity,
  orderForJob,
  poJob,
  receiptPreview,
  sortForList,
  stockState,
  unitCount,
  unitsAdded,
  validateNewPo,
} from './po-model'

const [RECEIVED_PO, ORDERED_PO] = INITIAL_PURCHASE_ORDERS as [MockPurchaseOrder, MockPurchaseOrder]

function po(overrides: Partial<MockPurchaseOrder>): MockPurchaseOrder {
  return { ...ORDERED_PO, ...overrides }
}

function part(overrides: Partial<MockPart>): MockPart {
  return {
    id: 'part-x',
    shopId: 'shop-lahore-auto-care',
    sku: 'X-01',
    name: 'Part X',
    category: 'Test',
    on_hand: 10,
    reserved: 0,
    reorder_level: 2,
    unit_price: 1000,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('order figures', () => {
  it('open means ORDERED or PARTIALLY_RECEIVED', () => {
    expect(isOpen({ status: 'ORDERED' })).toBe(true)
    expect(isOpen({ status: 'PARTIALLY_RECEIVED' })).toBe(true)
    expect(isOpen({ status: 'RECEIVED' })).toBe(false)
  })

  it('adds up lines and units like the stored total', () => {
    expect(ORDERED_PO.items.map(lineTotal)).toEqual([42000, 28800])
    expect(ORDERED_PO.items.map(lineTotal).reduce((a, b) => a + b, 0)).toBe(ORDERED_PO.total_amount)
    expect(unitCount(RECEIVED_PO)).toBe(21)
    expect(contentsLabel(RECEIVED_PO)).toBe('2 parts · 21 units')
    expect(contentsLabel(po({ items: [{ ...ORDERED_PO.items[0]!, quantity: 1 }] }))).toBe(
      '1 part · 1 unit',
    )
    expect(contentsLabel(po({ items: [{ ...ORDERED_PO.items[0]!, quantity: 1730 }] }))).toBe(
      '1 part · 1,730 units',
    )
  })
})

describe('list filters', () => {
  it('filters by open, received or all, and counts each', () => {
    const pos = [RECEIVED_PO, ORDERED_PO, po({ id: 'po-3', status: 'PARTIALLY_RECEIVED' })]
    expect(pos.filter((p) => matchesFilter(p, 'open')).map((p) => p.id)).toEqual([
      'po-1002',
      'po-3',
    ])
    expect(pos.filter((p) => matchesFilter(p, 'received')).map((p) => p.id)).toEqual(['po-1001'])
    expect(pos.filter((p) => matchesFilter(p, 'all'))).toHaveLength(3)
    expect(filterCounts(pos)).toEqual({ open: 2, received: 1, all: 3 })
  })

  it('searches the PO number, supplier, part names and SKUs, ignoring case', () => {
    expect(matchesQuery(ORDERED_PO, '  po-2026-002 ')).toBe(true)
    expect(matchesQuery(ORDERED_PO, 'atlas')).toBe(true)
    expect(matchesQuery(ORDERED_PO, 'spark plugs')).toBe(true)
    expect(matchesQuery(ORDERED_PO, 'br-vent')).toBe(true)
    expect(matchesQuery(ORDERED_PO, 'oil filter')).toBe(false)
    expect(matchesQuery(ORDERED_PO, '')).toBe(true)
  })

  it('lists open orders first, then the newest', () => {
    const older = po({ id: 'old-open', created_at: '2026-10-01T09:00:00Z' })
    const newer = po({ id: 'new-open', created_at: '2026-10-09T09:00:00.123Z' })
    const received = po({ id: 'received', status: 'RECEIVED', created_at: '2026-10-10T09:00:00Z' })
    expect(sortForList([received, older, newer]).map((p) => p.id)).toEqual([
      'new-open',
      'old-open',
      'received',
    ])
  })
})

describe('stock state (D45)', () => {
  it('is out when nothing is available, low at the reorder level, else ok', () => {
    expect(stockState(part({ on_hand: 3, reserved: 3 }))).toBe('out')
    expect(stockState(part({ on_hand: 2, reorder_level: 2 }))).toBe('low')
    expect(stockState(part({ on_hand: 3, reorder_level: 2 }))).toBe('ok')
  })
})

describe('receipt preview', () => {
  it('matches what receiving does to stock (adjustPartStock on every line)', () => {
    const order = po({
      items: [
        { part_sku: 'BR-VENT-01', part_name: 'Rotors', quantity: 4, unit_price: 10500 },
        { part_sku: 'part-sp-01', part_name: 'Spark plugs (by id)', quantity: 8, unit_price: 3600 },
        { part_sku: 'BR-VENT-01', part_name: 'Rotors again', quantity: 1, unit_price: 10500 },
        { part_sku: 'PRT-GEN', part_name: 'Not stocked', quantity: 2, unit_price: 500 },
      ],
    })
    const preview = receiptPreview(order, getInventory())
    expect(preview.map(({ before, after }) => [before, after])).toEqual([
      [2, 6],
      [6, 14],
      [6, 7],
      [null, null],
    ])
    expect(unitsAdded(preview)).toBe(13)

    const applied = order.items.map((line) => adjustPartStock(line.part_sku, line.quantity))
    expect(applied.map((updated) => updated?.on_hand ?? null)).toEqual(
      preview.map(({ after }) => after),
    )
  })
})

describe('new order identity', () => {
  it('keeps the PO-2026-NNN format and never reuses a number or id', () => {
    const existing = [
      { id: 'po-1000', po_number: 'PO-2026-100' },
      { id: 'po-1000-2', po_number: 'PO-2026-101' },
    ]
    // random() = 0 draws PO-2026-100, which is taken: the next free number is used instead.
    expect(newPurchaseOrderIdentity(existing, 1000, () => 0)).toEqual({
      id: 'po-1000-3',
      po_number: 'PO-2026-102',
    })
    expect(newPurchaseOrderIdentity([], 42, () => 0.999).po_number).toBe('PO-2026-999')
  })

  it('moves to four digits once every three-digit number is taken', () => {
    const all = Array.from({ length: 900 }, (_, i) => ({
      id: `po-${i}`,
      po_number: `PO-2026-${100 + i}`,
    }))
    expect(newPurchaseOrderIdentity(all, 5, () => 0.5).po_number).toBe('PO-2026-1000')
  })
})

describe('new order form rules', () => {
  const valid = { supplier: 'Atlas Automotive Imports', quantity: '10', unitCost: '1500' }

  it('accepts a supplier, a whole quantity from 1 to 10,000 and a whole unit cost', () => {
    expect(validateNewPo(valid)).toEqual({})
    expect(validateNewPo({ ...valid, quantity: '10000' })).toEqual({})
  })

  it('names every field that is wrong', () => {
    expect(validateNewPo({ supplier: '  ', quantity: '0', unitCost: '0' })).toEqual({
      supplier: expect.any(String),
      quantity: expect.any(String),
      unitCost: expect.any(String),
    })
    for (const quantity of ['', '-5', '2.5', '1e3', '10001']) {
      expect(validateNewPo({ ...valid, quantity }).quantity).toBeDefined()
    }
    for (const unitCost of ['', '-1', '99.5', '10000000000']) {
      expect(validateNewPo({ ...valid, unitCost }).unitCost).toBeDefined()
    }
  })
})

describe('the job an order was raised for (D43)', () => {
  const base = '/pos/shops/shop-lahore-auto-care'
  const lahore = INITIAL_BOOKINGS.filter((b) => b.shopId === 'shop-lahore-auto-care')

  it('opens the parts job for Parts staff and the booking for the Owner (D16)', () => {
    expect(jobHref(base, 'bk-001', 'PARTS_PERSON')).toBe(`${base}/parts/bk-001`)
    expect(jobHref(base, 'bk-001', 'OWNER')).toBe(`${base}/bookings/bk-001`)
  })

  it('names the job by reference and vehicle, from this shop only (D20)', () => {
    expect(poJob(po({ bookingId: 'bk-001' }), lahore, base, 'PARTS_PERSON')).toEqual({
      bookingId: 'bk-001',
      reference: 'BF-2026-001',
      vehicle: '2022 Honda Civic Oriel',
      href: `${base}/parts/bk-001`,
    })
    // A general restock has no job, and another shop's booking is never named.
    expect(poJob(po({ bookingId: undefined }), lahore, base, 'PARTS_PERSON')).toBeUndefined()
    expect(poJob(po({ bookingId: 'bk-009' }), lahore, base, 'PARTS_PERSON')).toBeUndefined()
  })

  it('finds the order a job waits on: its newest open one, else its newest received one', () => {
    const older = po({ id: 'a', bookingId: 'bk-001', created_at: '2026-10-01T09:00:00.000Z' })
    const newer = po({ id: 'b', bookingId: 'bk-001', created_at: '2026-10-05T09:00:00.000Z' })
    const received = po({
      id: 'c',
      bookingId: 'bk-001',
      status: 'RECEIVED',
      created_at: '2026-10-08T09:00:00.000Z',
    })
    const other = po({ id: 'd', bookingId: 'bk-003', created_at: '2026-10-09T09:00:00.000Z' })
    expect(orderForJob('bk-001', [older, received, newer, other])?.id).toBe('b')
    expect(orderForJob('bk-001', [received, other])?.id).toBe('c')
    expect(orderForJob('bk-001', INITIAL_PURCHASE_ORDERS)).toBeUndefined()
  })
})
