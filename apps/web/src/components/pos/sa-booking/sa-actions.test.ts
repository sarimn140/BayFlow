import { describe, expect, it } from 'vitest'

import { BOOKING_STATUSES, type BookingStatus } from '@/lib/status'

import { planActionBar, saAllowedActions, type SaActionSlug } from './sa-actions'

/** Spec 08 rule table (T02–T22, O1, O3) for an SA or Owner caller; reassignment is P1. */
const EXPECTED: Record<BookingStatus, SaActionSlug[]> = {
  PENDING: ['confirm', 'decline', 'cancel'],
  CONFIRMED: ['assign-technician', 'cancel'],
  ASSIGNED: ['cancel'],
  INSPECTING: ['cancel'],
  ESTIMATE_REVIEW: ['edit-estimate', 'send-estimate', 'cancel'],
  AWAITING_CUSTOMER: ['cancel'],
  ESTIMATE_APPROVED: ['assign-parts-person', 'cancel'],
  ESTIMATE_REJECTED: ['revise-estimate', 'return-to-technician', 'cancel'],
  PARTS_PENDING: ['cancel'],
  PARTS_ORDERED: ['cancel'],
  PARTS_READY: ['cancel'],
  IN_REPAIR: [],
  QC_PENDING: [],
  QC_IN_PROGRESS: [],
  READY_FOR_PICKUP: ['notify-ready', 'complete'],
  COMPLETED: [],
  CANCELLED: [],
}

describe('saAllowedActions', () => {
  it.each(BOOKING_STATUSES)('lists the spec 08 actions for %s', (status) => {
    expect(saAllowedActions(status)).toEqual(EXPECTED[status])
  })
})

describe('planActionBar (spec 09 §4.6)', () => {
  const plan = (status: BookingStatus, readyNotified = false) =>
    planActionBar(saAllowedActions(status), { readyNotified })

  it('makes the first forward action the primary and puts destructive actions last', () => {
    expect(plan('PENDING')).toEqual({
      primary: 'confirm',
      secondary: [],
      destructive: ['decline', 'cancel'],
    })
    expect(plan('ESTIMATE_REJECTED')).toEqual({
      primary: 'revise-estimate',
      secondary: ['return-to-technician'],
      destructive: ['cancel'],
    })
  })

  it('keeps edit-estimate out of the bar (it lives in the estimate panel)', () => {
    expect(plan('ESTIMATE_REVIEW')).toEqual({
      primary: 'send-estimate',
      secondary: [],
      destructive: ['cancel'],
    })
  })

  it('has no primary when the SA can only cancel, and nothing on a closed booking', () => {
    expect(plan('AWAITING_CUSTOMER')).toEqual({
      primary: null,
      secondary: [],
      destructive: ['cancel'],
    })
    expect(plan('COMPLETED')).toEqual({ primary: null, secondary: [], destructive: [] })
  })

  it('makes completing the primary once the customer has been told the car is ready', () => {
    expect(plan('READY_FOR_PICKUP')).toMatchObject({
      primary: 'notify-ready',
      secondary: ['complete'],
    })
    expect(plan('READY_FOR_PICKUP', true)).toMatchObject({
      primary: 'complete',
      secondary: ['notify-ready'],
    })
  })
})
