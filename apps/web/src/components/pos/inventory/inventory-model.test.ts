import { describe, expect, it } from 'vitest'

import { isLowStock } from '@/lib/kpis'
import { INITIAL_PARTS, INITIAL_PURCHASE_ORDERS, type MockPart } from '@/lib/mock-data'

import {
  adjustmentError,
  availableOf,
  categoriesOf,
  filterParts,
  inventorySummary,
  skuTakenBy,
  stockState,
} from './inventory-model'
import { adjustSchemaFor, partSchema, signedDelta } from './inventory-schemas'

/** One shop's parts, as the screen passes them (the seed also holds the other shops' parts). */
const LAHORE_PARTS = INITIAL_PARTS.filter((p) => p.shopId === 'shop-lahore-auto-care')

function part(changes: Partial<MockPart>): MockPart {
  return { ...INITIAL_PARTS[0]!, ...changes }
}

describe('stock state (D45)', () => {
  it('reads what is available (on hand minus reserved), with OUT winning over LOW', () => {
    expect(stockState(part({ on_hand: 10, reserved: 0, reorder_level: 5 }))).toBe('OK')
    expect(stockState(part({ on_hand: 6, reserved: 1, reorder_level: 5 }))).toBe('LOW')
    expect(stockState(part({ on_hand: 5, reserved: 0, reorder_level: 5 }))).toBe('LOW')
    expect(stockState(part({ on_hand: 2, reserved: 2, reorder_level: 0 }))).toBe('OUT')
    expect(stockState(part({ on_hand: 0, reserved: 0, reorder_level: 3 }))).toBe('OUT')
    expect(availableOf(part({ on_hand: 4, reserved: 1 }))).toBe(3)
  })

  it('agrees with the low-stock rule the overview counts with (isLowStock)', () => {
    for (const onHand of [0, 1, 2, 3, 4, 5, 6]) {
      for (const reserved of [0, 1, 2]) {
        const p = part({ on_hand: Math.max(onHand, reserved), reserved, reorder_level: 3 })
        expect(stockState(p) !== 'OK').toBe(isLowStock(p))
      }
    }
  })
})

describe('inventory summary', () => {
  it('values the stock on hand and counts what needs restocking and what is on order', () => {
    const summary = inventorySummary(LAHORE_PARTS, INITIAL_PURCHASE_ORDERS)
    expect(summary).toEqual({
      partCount: 6,
      unitsOnHand: 37,
      stockValue: 153_200,
      lowCount: 0,
      outCount: 0,
      openOrders: 1,
    })
  })

  it('splits low from out of stock', () => {
    const parts = [
      part({ id: 'a', on_hand: 3, reserved: 1, reorder_level: 4 }),
      part({ id: 'b', on_hand: 1, reserved: 1, reorder_level: 1 }),
      part({ id: 'c', on_hand: 9, reserved: 0, reorder_level: 2 }),
    ]
    expect(inventorySummary(parts, [])).toMatchObject({ lowCount: 1, outCount: 1, openOrders: 0 })
  })
})

describe('search and stock filters', () => {
  const parts = [
    part({ id: 'a', sku: 'BP-FR-02', name: 'Brake pads', category: 'Brakes', on_hand: 9 }),
    part({ id: 'b', sku: 'OF-TY-01', name: 'Oil filter', category: 'Filters', on_hand: 2 }),
    part({ id: 'c', sku: 'SP-IRID-04', name: 'Spark plugs', category: 'Ignition', on_hand: 0 }),
  ]

  it('matches SKU, name or category, ignoring case and spaces around the query', () => {
    expect(filterParts(parts, 'all', ' bp-fr ').map((p) => p.id)).toEqual(['a'])
    expect(filterParts(parts, 'all', 'FILTER').map((p) => p.id)).toEqual(['b'])
    expect(filterParts(parts, 'all', 'ignition').map((p) => p.id)).toEqual(['c'])
    expect(filterParts(parts, 'all', '')).toHaveLength(3)
  })

  it('keeps LOW and OUT apart, like the pills', () => {
    expect(filterParts(parts, 'low', '').map((p) => p.id)).toEqual(['b'])
    expect(filterParts(parts, 'out', '').map((p) => p.id)).toEqual(['c'])
    expect(filterParts(parts, 'out', 'brake')).toEqual([])
  })
})

describe('part catalogue helpers', () => {
  it('finds a SKU in use, ignoring case and the part being edited', () => {
    expect(skuTakenBy(LAHORE_PARTS, 'of-ty-01')?.id).toBe('part-of-01')
    expect(skuTakenBy(LAHORE_PARTS, 'OF-TY-01', 'part-of-01')).toBeUndefined()
    expect(skuTakenBy(LAHORE_PARTS, 'NEW-01')).toBeUndefined()
  })

  it('suggests the most used categories first', () => {
    expect(categoriesOf(LAHORE_PARTS)).toEqual(['Brakes', 'Filters', 'Fluids', 'Ignition'])
  })
})

describe('stock adjustment rule (409 INSUFFICIENT_STOCK)', () => {
  const brakePads = part({ on_hand: 4, reserved: 1 })

  it('refuses a change that leaves less on hand than is reserved, or below zero', () => {
    expect(adjustmentError(brakePads, -3)).toBeNull()
    expect(adjustmentError(brakePads, -4)).toMatch(/less stock on hand than is reserved/)
    expect(adjustmentError(part({ on_hand: 2, reserved: 0 }), -3)).toMatch(/below zero/)
    expect(adjustmentError(brakePads, 5)).toBeNull()
  })

  it('validates the form: a whole, non-zero quantity, a reason, and the stock rule', () => {
    const schema = adjustSchemaFor(brakePads)
    const issues = (values: { direction: 'add' | 'remove'; quantity: string; reason: string }) =>
      schema.safeParse(values).error?.issues.map((issue) => [issue.path.join('.'), issue.message])

    expect(issues({ direction: 'add', quantity: '5', reason: 'Delivery received' })).toBeUndefined()
    expect(issues({ direction: 'add', quantity: '0', reason: 'Recount' })).toEqual([
      ['quantity', 'Enter 1 or more.'],
    ])
    expect(issues({ direction: 'add', quantity: '1.5', reason: '' })).toEqual([
      ['quantity', 'Enter a whole number, like 5.'],
      ['reason', 'Say why the stock changed.'],
    ])
    expect(issues({ direction: 'remove', quantity: '4', reason: 'Damaged' })).toEqual([
      [
        'quantity',
        'That adjustment would leave less stock on hand than is reserved for jobs, or below zero.',
      ],
    ])
    expect(signedDelta({ direction: 'remove', quantity: '1,200' })).toBe(-1200)
    expect(signedDelta({ direction: 'add', quantity: 'abc' })).toBe(0)
  })
})

describe('part form (PartCreate / PartUpdate limits)', () => {
  const valid = {
    sku: 'bp-fr-03',
    name: 'Pads',
    category: '',
    unit_cost: '3500',
    reorder_level: '0',
  }

  it('upper-cases the SKU and accepts a reorder level of 0', () => {
    const result = partSchema.safeParse(valid)
    expect(result.success && result.data).toMatchObject({ sku: 'BP-FR-03', reorder_level: '0' })
  })

  it('takes whole rupees, with or without thousands separators', () => {
    expect(partSchema.safeParse({ ...valid, unit_cost: '12,000' }).data?.unit_cost).toBe('12000')
    const decimals = partSchema.safeParse({ ...valid, unit_cost: '99.5' })
    expect(decimals.error?.issues[0]?.message).toBe('Enter whole rupees, like 3500.')
    const negative = partSchema.safeParse({ ...valid, unit_cost: '-5' })
    expect(negative.success).toBe(false)
  })

  it('refuses a SKU outside the pattern and a reorder level above 100,000', () => {
    const sku = partSchema.safeParse({ ...valid, sku: '-PADS' })
    expect(sku.error?.issues[0]?.path).toEqual(['sku'])
    const reorder = partSchema.safeParse({ ...valid, reorder_level: '100001' })
    expect(reorder.error?.issues[0]?.message).toBe('Enter 100,000 or less.')
  })
})
