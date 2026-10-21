import { describe, expect, it } from 'vitest'

import { INITIAL_BOOKINGS, type MockBooking } from '@/lib/mock-data'
import { BOOKING_STATUSES } from '@/lib/status'

import { estimateDecisionOf } from './estimate-decision'

function booking(id: string, overrides: Partial<MockBooking> = {}): MockBooking {
  return { ...INITIAL_BOOKINGS.find((b) => b.id === id)!, ...overrides }
}

describe('estimateDecisionOf (C-01 and C-02)', () => {
  it('shows only an estimate the shop has sent (D39)', () => {
    // The seeded confirmed booking carries a services total but no estimate lines.
    expect(estimateDecisionOf(booking('bk-004'))).toBeNull()
    expect(estimateDecisionOf(booking('bk-001', { status: 'ESTIMATE_REVIEW' }))).toBeNull()
  })

  it('tells pending, declined and approved apart', () => {
    expect(estimateDecisionOf(booking('bk-002'))).toBe('pending')
    expect(estimateDecisionOf(booking('bk-002', { status: 'ESTIMATE_REJECTED' }))).toBe('declined')
    expect(estimateDecisionOf(booking('bk-001'))).toBe('approved')
    expect(estimateDecisionOf(booking('bk-006'))).toBe('approved')
  })

  it('keeps an approved estimate on a cancelled booking, and only that', () => {
    const cancelled = booking('bk-001', { status: 'CANCELLED' })
    expect(estimateDecisionOf({ ...cancelled, estimateApproved: true })).toBe('approved')
    expect(estimateDecisionOf({ ...cancelled, estimateApproved: false })).toBeNull()
  })

  it('shows no price before the shop has quoted one, whatever the status', () => {
    const before = ['PENDING', 'CONFIRMED', 'ASSIGNED', 'INSPECTING', 'ESTIMATE_REVIEW'] as const
    for (const status of before) {
      expect(estimateDecisionOf(booking('bk-001', { status }))).toBeNull()
    }
    // Every status is answered: pending, declined, approved or nothing to show.
    for (const status of BOOKING_STATUSES) {
      expect([null, 'pending', 'declined', 'approved']).toContain(
        estimateDecisionOf(booking('bk-001', { status })),
      )
    }
  })
})
