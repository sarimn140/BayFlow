import { describe, expect, it } from 'vitest'

import type { MockBooking, MockEstimateItem, MockPart } from '@/lib/mock-data'

import {
  UNMATCHED_SKU,
  availabilityLabel,
  availablePercent,
  jobHealth,
  jobStage,
  lineState,
  orderTotal,
  partRequirements,
  partsSummary,
  queueByStage,
  queueSummary,
  shortList,
  waitingFor,
} from './parts-data'

const part = (sku: string, name: string, onHand: number): MockPart => ({
  id: `part-${sku}`,
  shopId: 'shop-1',
  sku,
  name,
  category: 'Misc',
  on_hand: onHand,
  reserved: 0,
  reorder_level: 1,
  unit_price: 1000,
})

const line = (
  id: string,
  description: string,
  quantity: number,
  unitPrice: number,
  type: MockEstimateItem['type'] = 'PART',
): MockEstimateItem => ({
  id,
  description,
  type,
  quantity,
  unit_price: unitPrice,
  total: quantity * unitPrice,
})

const INVENTORY = [
  part('BR-VENT-01', 'Vented Brake Rotors Pair (Civic/Corolla)', 2),
  part('OF-TY-01', 'Oil Filter Cartridge (Toyota/Honda)', 10),
  part('BP-FR-02', 'Semi-Metallic Front Brake Pads Set', 0),
]

describe('partRequirements', () => {
  const rows = partRequirements(
    [
      line('l1', 'Vented Brake Rotors Pair (Civic/Corolla)', 3, 12000),
      line('l2', 'Oil Filter Cartridge', 1, 1500),
      line('l3', 'Front Brake Pads Set', 2, 5500),
      line('l4', 'Ignition Coil Pack', 1, 9500),
      line('l5', 'Labour', 1, 2000, 'LABOR'),
    ],
    INVENTORY,
  )

  it('keeps only the part lines', () => {
    expect(rows.map((r) => r.id)).toEqual(['l1', 'l2', 'l3', 'l4'])
  })

  it('matches a part when either name contains the other, ignoring case', () => {
    // The inventory name contains the line ("Oil Filter Cartridge (Toyota/Honda)").
    expect(rows[1]).toMatchObject({ sku: 'OF-TY-01', inInventory: true, onHand: 10 })
    // "Semi-Metallic Front Brake Pads Set" contains "front brake pads set".
    expect(rows[2]).toMatchObject({ sku: 'BP-FR-02', inInventory: true, onHand: 0 })
  })

  it('computes the shortage as max(0, required − on hand)', () => {
    expect(rows.map((r) => r.shortage)).toEqual([1, 0, 2, 1])
  })

  it('orders an unmatched part under the generic SKU with nothing on hand', () => {
    expect(rows[3]).toMatchObject({
      sku: UNMATCHED_SKU,
      inInventory: false,
      onHand: 0,
      required: 1,
      shortage: 1,
      unitCost: 9500,
    })
  })

  it('summarises what stock covers', () => {
    const summary = partsSummary(rows)
    expect(summary).toMatchObject({ requiredCount: 4, availableCount: 1, allAvailable: false })
    expect(summary.short.map((r) => r.id)).toEqual(['l1', 'l3', 'l4'])
    expect(availabilityLabel(summary)).toBe('1 of 4 parts in stock')
    expect(availablePercent(summary)).toBe(25)
    expect(shortList(summary.short)).toBe(
      'Vented Brake Rotors Pair (Civic/Corolla) × 1, Front Brake Pads Set × 2, Ignition Coil Pack × 1',
    )
  })

  it('totals a purchase order as shortage × unit cost', () => {
    expect(orderTotal(partsSummary(rows).short)).toBe(1 * 12000 + 2 * 5500 + 1 * 9500)
  })
})

describe('a labour-only job (D31)', () => {
  const summary = partsSummary(partRequirements([line('l1', 'Alignment', 1, 2500, 'LABOR')], []))

  it('has nothing short and nothing to show as progress', () => {
    expect(summary).toMatchObject({ requiredCount: 0, availableCount: 0, allAvailable: true })
    expect(availabilityLabel(summary)).toBe('No parts on the estimate')
    expect(availablePercent(summary)).toBe(100)
    expect(jobHealth(summary, 'PARTS_PENDING')).toBe('no-parts')
  })
})

describe('stages and chips', () => {
  it('maps statuses to the parts person’s stage', () => {
    expect(jobStage('ESTIMATE_APPROVED')).toBe('not-yet')
    expect(jobStage('PARTS_PENDING')).toBe('check')
    expect(jobStage('PARTS_ORDERED')).toBe('ordered')
    expect(jobStage('PARTS_READY')).toBe('ready')
    expect(jobStage('IN_REPAIR')).toBe('allocated')
    expect(jobStage('COMPLETED')).toBe('allocated')
    expect(jobStage('CANCELLED')).toBe('cancelled')
  })

  it('labels a line in stock, short, on order or allocated', () => {
    expect(lineState({ shortage: 0 }, 'check')).toBe('in-stock')
    expect(lineState({ shortage: 2 }, 'check')).toBe('short')
    expect(lineState({ shortage: 2 }, 'ordered')).toBe('on-order')
    expect(lineState({ shortage: 2 }, 'allocated')).toBe('allocated')
  })

  it('labels a whole job for the queue', () => {
    const short = partsSummary(partRequirements([line('l1', 'Ignition Coil Pack', 1, 9500)], []))
    expect(jobHealth(short, 'PARTS_PENDING')).toBe('short')
    expect(jobHealth(short, 'PARTS_ORDERED')).toBe('on-order')
    const covered = partsSummary(
      partRequirements([line('l1', 'Oil Filter Cartridge', 1, 1500)], INVENTORY),
    )
    expect(jobHealth(covered, 'PARTS_READY')).toBe('in-stock')
  })
})

describe('the queue', () => {
  const booking = (id: string, status: MockBooking['status'], updatedAt: string) =>
    ({ id, reference: `BF-${id}`, status, updatedAt }) as MockBooking

  it('groups the parts statuses, longest wait first, and ignores the rest', () => {
    const byStage = queueByStage([
      booking('a', 'PARTS_PENDING', '2026-10-10T05:00:00Z'),
      booking('b', 'PARTS_PENDING', '2026-10-09T05:00:00Z'),
      booking('c', 'PARTS_ORDERED', '2026-10-10T01:00:00Z'),
      booking('d', 'IN_REPAIR', '2026-10-08T01:00:00Z'),
      booking('e', 'PARTS_READY', 'not a date'),
    ])
    expect(byStage.PARTS_PENDING.map((b) => b.id)).toEqual(['b', 'a'])
    expect(byStage.PARTS_ORDERED.map((b) => b.id)).toEqual(['c'])
    expect(byStage.PARTS_READY.map((b) => b.id)).toEqual(['e'])
  })

  it('describes the queue in one sentence', () => {
    expect(queueSummary({ PARTS_PENDING: 2, PARTS_ORDERED: 0, PARTS_READY: 1 })).toBe(
      '3 jobs waiting for parts: 2 to check and 1 ready to allocate.',
    )
    expect(queueSummary({ PARTS_PENDING: 0, PARTS_ORDERED: 1, PARTS_READY: 0 })).toBe(
      '1 job waiting for parts: 1 on order.',
    )
    expect(queueSummary({ PARTS_PENDING: 0, PARTS_ORDERED: 0, PARTS_READY: 0 })).toBe(
      'Check approved jobs against stock, order what is missing and hand the parts to technicians.',
    )
  })

  it('says how long a job has waited', () => {
    const now = new Date('2026-10-10T12:00:00Z')
    expect(waitingFor('2026-10-10T11:59:30Z', now)).toBe('Just arrived')
    expect(waitingFor('2026-10-10T12:00:30Z', now)).toBe('Just arrived')
    expect(waitingFor('2026-10-10T11:59:00Z', now)).toBe('Waiting 1 minute')
    expect(waitingFor('2026-10-10T11:15:00Z', now)).toBe('Waiting 45 minutes')
    expect(waitingFor('2026-10-10T09:00:00Z', now)).toBe('Waiting 3 hours')
    expect(waitingFor('2026-10-08T11:00:00Z', now)).toBe('Waiting 2 days')
    expect(waitingFor('not a date', now)).toBeNull()
  })
})
