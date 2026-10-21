import { describe, expect, it } from 'vitest'

import { formatPKR } from '@/lib/format'
import { INITIAL_BOOKINGS, type MockBooking } from '@/lib/mock-data'
import { BOOKING_STATUSES, type BookingStatus } from '@/lib/status'

import {
  DEFAULT_FILTERS,
  PAGE_SIZE,
  countBookings,
  estimateLabel,
  inPreset,
  matchesDate,
  matchesQuery,
  nextStepFor,
  normaliseQuery,
  paginate,
  parseQueueParams,
  queueSearchString,
  selectBookings,
  slotDateTime,
  slotLabel,
  updatedLabel,
  type QueueFilters,
} from './queue-model'

const SHOP = 'shop-lahore-auto-care'
const TODAY = '2026-10-10'
const seed = INITIAL_BOOKINGS.filter((b) => b.shopId === SHOP)

const filters = (patch: Partial<QueueFilters> = {}): QueueFilters => ({
  ...DEFAULT_FILTERS,
  ...patch,
})
const refs = (rows: ReadonlyArray<MockBooking>) => rows.map((b) => b.reference)
const params = (query: string) => new URLSearchParams(query)

describe('presets (spec 10 SA-01, lib/kpis)', () => {
  it('splits every open status between "Needs action" and "In progress"', () => {
    for (const status of BOOKING_STATUSES) {
      const groups = [inPreset(status, 'needs_action'), inPreset(status, 'in_progress')]
      const closed = status === 'COMPLETED' || status === 'CANCELLED'
      expect(groups.filter(Boolean).length, status).toBe(closed ? 0 : 1)
      expect(inPreset(status, 'all'), status).toBe(true)
    }
  })

  it('leaves a sent estimate with the customer, not in the advisor queue', () => {
    expect(inPreset('AWAITING_CUSTOMER', 'needs_action')).toBe(false)
    expect(inPreset('AWAITING_CUSTOMER', 'in_progress')).toBe(true)
  })

  it('counts each preset and status over all bookings', () => {
    const counts = countBookings(seed)
    // Lahore Auto Care's 7 bookings: BF-2026-006 completed and BF-2026-007 cancelled are "All" only.
    expect(counts.presets).toEqual({ needs_action: 2, in_progress: 3, all: 7 })
    expect(counts.statuses.READY_FOR_PICKUP).toBe(1)
    expect(counts.statuses.PENDING).toBe(0)
    expect(Object.keys(counts.statuses)).toHaveLength(17)
  })
})

describe('selectBookings', () => {
  it('opens on the advisor queue, soonest slot first', () => {
    expect(refs(selectBookings(seed, DEFAULT_FILTERS, TODAY))).toEqual([
      'BF-2026-005', // ready for pick-up, 8 Oct 10:00
      'BF-2026-004', // confirmed, 10 Oct 09:00
    ])
  })

  it('orders "In progress" by slot, 10 am before 2 pm', () => {
    expect(refs(selectBookings(seed, filters({ preset: 'in_progress' }), TODAY))).toEqual([
      'BF-2026-003', // 8 Oct 02:00 pm
      'BF-2026-001', // 9 Oct 10:00 am
      'BF-2026-002', // 9 Oct 11:00 am
    ])
  })

  it('orders "All" by the latest change', () => {
    expect(refs(selectBookings(seed, filters({ preset: 'all' }), TODAY))).toEqual([
      'BF-2026-002',
      'BF-2026-001',
      'BF-2026-004',
      'BF-2026-003',
      'BF-2026-005',
      'BF-2026-006',
      'BF-2026-007',
    ])
  })

  it('narrows by status, slot day and search', () => {
    const all = filters({ preset: 'all' })
    expect(refs(selectBookings(seed, { ...all, status: 'COMPLETED' }, TODAY))).toEqual([
      'BF-2026-006',
    ])
    expect(refs(selectBookings(seed, { ...all, date: 'today' }, TODAY))).toEqual(['BF-2026-004'])
    expect(refs(selectBookings(seed, { ...all, query: 'zainab' }, TODAY))).toEqual(['BF-2026-004'])
  })

  it('does not change the array it reads', () => {
    const copy = [...seed]
    selectBookings(seed, filters({ preset: 'all' }), TODAY)
    expect(seed).toEqual(copy)
  })
})

describe('matchesQuery', () => {
  const booking = seed.find((b) => b.reference === 'BF-2026-001')!

  it.each([
    'BF-2026-001',
    'bf-2026-001',
    '2026001',
    'ayesha',
    'LEA-22-4589',
    'lea 22',
    'lea224589',
    'civic',
    'honda civic',
    '  ayesha  ',
    '',
  ])('finds BF-2026-001 by %j', (query) => {
    expect(matchesQuery(booking, query)).toBe(true)
  })

  it.each(['tariq', 'LEE-21', 'corolla', '#', 'bf 2026 002'])('does not find it by %j', (query) => {
    expect(matchesQuery(booking, query)).toBe(false)
  })
})

describe('matchesDate', () => {
  it('keeps today, and today plus six days for "Next 7 days"', () => {
    expect(matchesDate({ scheduledDate: '2026-10-10' }, 'today', TODAY)).toBe(true)
    expect(matchesDate({ scheduledDate: '2026-10-11' }, 'today', TODAY)).toBe(false)
    expect(matchesDate({ scheduledDate: '2026-10-16' }, 'next_7_days', TODAY)).toBe(true)
    expect(matchesDate({ scheduledDate: '2026-10-17' }, 'next_7_days', TODAY)).toBe(false)
    expect(matchesDate({ scheduledDate: '2026-10-09' }, 'next_7_days', TODAY)).toBe(false)
    expect(matchesDate({ scheduledDate: '2020-01-01' }, 'any', TODAY)).toBe(true)
  })
})

describe('URL (spec 09 §4.7)', () => {
  it('reads the defaults from an empty query', () => {
    expect(parseQueueParams(params(''))).toEqual(DEFAULT_FILTERS)
  })

  it.each<[string, Partial<QueueFilters>]>([
    ['filter=needs_action', { preset: 'needs_action' }],
    ['filter=needs_sa', { preset: 'needs_action' }],
    ['filter=in_progress', { preset: 'in_progress' }],
    ['filter=in-progress', { preset: 'in_progress' }],
    ['filter=all', { preset: 'all' }],
    ['filter=ready', { preset: 'all', status: 'READY_FOR_PICKUP' }],
    ['filter=completed', { preset: 'all', status: 'COMPLETED' }],
    ['status=PENDING', { preset: 'all', status: 'PENDING' }],
    ['status=ready_for_pickup', { preset: 'all', status: 'READY_FOR_PICKUP' }],
    ['filter=in_progress&status=IN_REPAIR', { preset: 'all', status: 'IN_REPAIR' }],
    ['status=NOPE&status=QC_PENDING', { preset: 'all', status: 'QC_PENDING' }],
    ['filter=nope&status=nope', {}],
    ['date=today', { date: 'today' }],
    ['date=next_7_days', { date: 'next_7_days' }],
    ['date=yesterday', {}],
    ['q=LEA-22', { query: 'LEA-22' }],
    ['q=%20%20lea%2022%20', { query: 'lea 22' }],
    [
      'status=AWAITING_CUSTOMER&q=tariq',
      { preset: 'all', status: 'AWAITING_CUSTOMER', query: 'tariq' },
    ],
    ['page=3', { page: 3 }],
    ['page=0', {}],
    ['page=abc', {}],
  ])('reads ?%s', (query, expected) => {
    expect(parseQueueParams(params(query))).toEqual(filters(expected))
  })

  it('caps the search at 100 characters', () => {
    expect(parseQueueParams(params(`q=${'x'.repeat(150)}`)).query).toHaveLength(100)
  })

  it('writes nothing for the defaults and round-trips every other state', () => {
    expect(queueSearchString(DEFAULT_FILTERS)).toBe('')
    const states: QueueFilters[] = [
      filters({ preset: 'in_progress' }),
      filters({ preset: 'all', status: 'ESTIMATE_REJECTED', date: 'today' }),
      filters({ preset: 'all', query: 'lea 22', page: 2 }),
      filters({ date: 'next_7_days' }),
    ]
    for (const state of states) {
      expect(parseQueueParams(params(queueSearchString(state)))).toEqual(state)
    }
  })

  it('trims the search it writes, exactly as it reads it back', () => {
    expect(queueSearchString(filters({ query: '  lea  ' }))).toBe('q=lea')
    expect(queueSearchString(filters({ query: '   ' }))).toBe('')
    expect(normaliseQuery(` ${'y'.repeat(99)} z`)).toBe('y'.repeat(99))
    for (const typed of ['lea ', ' lea 22', `${'x'.repeat(99)} `, '']) {
      const written = new URLSearchParams(queueSearchString(filters({ query: typed })))
      expect(parseQueueParams(written).query).toBe(normaliseQuery(typed))
    }
  })
})

describe('nextStepFor', () => {
  it('asks the advisor to act only on their own statuses', () => {
    for (const status of BOOKING_STATUSES) {
      const step = nextStepFor(status)
      expect(step.kind === 'action', status).toBe(inPreset(status, 'needs_action'))
    }
  })

  it.each<[BookingStatus, string]>([
    ['PENDING', 'Confirm booking'],
    ['CONFIRMED', 'Assign technician'],
    ['ESTIMATE_REVIEW', 'Send estimate'],
    ['ESTIMATE_APPROVED', 'Assign parts person'],
    ['ESTIMATE_REJECTED', 'Revise estimate'],
    ['READY_FOR_PICKUP', 'Notify customer'],
    ['AWAITING_CUSTOMER', 'Waiting on customer'],
    ['IN_REPAIR', 'Waiting on technician'],
    ['PARTS_ORDERED', 'Waiting on parts'],
    ['QC_PENDING', 'Waiting on QC'],
  ])('%s → %s', (status, label) => {
    expect(nextStepFor(status)).toMatchObject({ label })
  })

  it('has nothing for closed bookings', () => {
    expect(nextStepFor('COMPLETED')).toEqual({ kind: 'none' })
    expect(nextStepFor('CANCELLED')).toEqual({ kind: 'none' })
  })
})

describe('row labels', () => {
  it('names the slot day relative to the shop day', () => {
    const at = (scheduledDate: string) =>
      slotLabel({ scheduledDate, scheduledTime: '09:00 am' }, TODAY)
    expect(at('2026-10-10')).toBe('Today · 09:00 am')
    expect(at('2026-10-11')).toBe('Tomorrow · 09:00 am')
    expect(at('2026-10-09')).toBe('Yesterday · 09:00 am')
    expect(at('2026-10-06')).toBe('Tue 6 Oct · 09:00 am')
    expect(at('2025-12-30')).toBe('Tue 30 Dec 2025 · 09:00 am')
    expect(at('soon')).toBe('soon · 09:00 am')
  })

  it('gives the slot a machine-readable time', () => {
    expect(slotDateTime({ scheduledDate: '2026-10-08', scheduledTime: '02:00 pm' })).toBe(
      '2026-10-08T14:00',
    )
    expect(slotDateTime({ scheduledDate: '2026-10-08', scheduledTime: 'noon' })).toBeUndefined()
  })

  it('says when the booking last changed, and nothing for a bad timestamp', () => {
    expect(updatedLabel('2026-10-10T03:00:00Z', '2026-10-10T05:00:00Z')).toBe('Updated 2 hours ago')
    expect(updatedLabel('2026-10-09T05:00:00Z', '2026-10-10T05:00:00Z')).toBe('Updated yesterday')
    expect(updatedLabel('not a date', '2026-10-10T05:00:00Z')).toBeNull()
  })

  it('shows an estimate only once it has lines', () => {
    expect(estimateLabel({ estimateItems: [], estimateTotal: 0 })).toBeNull()
    const lines = seed.find((b) => b.reference === 'BF-2026-002')!
    expect(estimateLabel(lines)).toBe(`Estimate ${formatPKR(10800)}`)
  })
})

describe('paginate', () => {
  const rows = Array.from({ length: 45 }, (_, i) => i)

  it('cuts pages of 20 and clamps the page number', () => {
    expect(paginate(rows, 1)).toMatchObject({ page: 1, pageCount: 3, from: 1, to: PAGE_SIZE })
    expect(paginate(rows, 3)).toMatchObject({ page: 3, from: 41, to: 45 })
    expect(paginate(rows, 9)).toMatchObject({ page: 3, from: 41, to: 45 })
    expect(paginate([], 2)).toMatchObject({ page: 1, pageCount: 1, from: 0, to: 0, rows: [] })
  })
})
