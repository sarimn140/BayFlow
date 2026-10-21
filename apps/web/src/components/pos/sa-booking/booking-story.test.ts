import { describe, expect, it } from 'vitest'

import { INITIAL_BOOKINGS, type MockBooking } from '@/lib/mock-data'

import { buildActivity, historySince } from './activity'
import { describeNextStep, slotText, type NextStepContext } from './next-step'
import { EMPTY_SA_RECORD, type SaBookingRecord, type SaCancellation } from './sa-records'

function seed(id: string): MockBooking {
  const booking = INITIAL_BOOKINGS.find((candidate) => candidate.id === id)
  if (!booking) throw new Error(`no seed booking ${id}`)
  return { ...booking }
}

const context: NextStepContext = {
  technician: 'Hamza',
  estimateVersion: 1,
  saDraftOpen: false,
  readyNotified: false,
  timeZone: 'Asia/Karachi',
}

const decline: SaCancellation = {
  kind: 'decline',
  reason: 'Fully booked that day.',
  at: '2026-10-09T10:00:00Z',
  by: 'Bilal',
  role: 'SERVICE_ADVISOR',
  fromStatus: 'PENDING',
  previousUpdatedAt: '2026-10-09T03:00:00Z',
}

describe('describeNextStep', () => {
  it('says whose turn it is', () => {
    expect(describeNextStep(seed('bk-002'), context)).toMatchObject({
      kind: 'wait',
      label: 'Waiting on Ayesha Khan',
      title: 'Estimate sent for approval',
    })
    expect(describeNextStep(seed('bk-004'), context)).toMatchObject({
      kind: 'act',
      label: 'Next step',
      title: 'Assign a technician',
    })
  })

  it('moves from telling the customer to completing the booking', () => {
    expect(describeNextStep(seed('bk-005'), context).title).toBe('Tell the customer')
    expect(describeNextStep(seed('bk-005'), { ...context, readyNotified: true }).title).toBe(
      'Complete the booking',
    )
  })

  it('names who declined the booking and when, in shop time', () => {
    const booking: MockBooking = { ...seed('bk-004'), status: 'CANCELLED' }
    expect(describeNextStep(booking, { ...context, cancellation: decline })).toEqual({
      kind: 'done',
      label: 'Closed',
      title: 'Booking declined',
      description: 'Bilal declined it on Fri, 9 Oct 2026 at 3:00 pm.',
    })
  })

  it('asks for lines when an estimate under review is empty', () => {
    const booking: MockBooking = { ...seed('bk-002'), status: 'ESTIMATE_REVIEW', estimateItems: [] }
    expect(describeNextStep(booking, context).description).toMatch(/^The estimate has no lines yet/)
  })
})

describe('slotText', () => {
  it('formats the slot like every other date on the page', () => {
    expect(slotText(seed('bk-004'))).toBe('Sat, 10 Oct 2026 · 9:00 am')
    expect(slotText(seed('bk-004'), ' at ')).toBe('Sat, 10 Oct 2026 at 9:00 am')
  })
})

describe('buildActivity', () => {
  it('lists the shared history, newest first', () => {
    const titles = buildActivity(seed('bk-002'), EMPTY_SA_RECORD, { technician: 'Hamza' }).map(
      (entry) => entry.title,
    )
    expect(titles).toEqual([
      'Estimate sent to the customer',
      'Estimate submitted for review',
      'Inspection started',
      'Assigned to Hamza',
      'Booking confirmed',
      'Booking requested',
    ])
  })

  it('rebuilds the path a cancelled booking took, then the cancel and its reason', () => {
    const booking: MockBooking = {
      ...seed('bk-001'),
      status: 'CANCELLED',
      updatedAt: '2026-10-09T08:00:00Z',
    }
    const record: SaBookingRecord = {
      ...EMPTY_SA_RECORD,
      cancellation: {
        ...decline,
        kind: 'cancel',
        reason: 'Sold the car.',
        at: '2026-10-09T08:00:00Z',
        fromStatus: 'PARTS_ORDERED',
        previousUpdatedAt: '2026-10-09T07:00:00Z',
      },
    }
    const entries = buildActivity(booking, record, {})
    expect(entries).toHaveLength(10) // Pending … Parts ordered, then the cancel
    expect(entries[0]).toMatchObject({
      title: 'Booking cancelled',
      note: 'Sold the car.',
      actor: 'Bilal · Service advisor',
    })
    expect(entries[1]?.title).toBe('Missing parts ordered')
  })

  it('keeps the declined round when the estimate goes back to the technician', () => {
    const rejected: MockBooking = {
      ...seed('bk-002'),
      status: 'ESTIMATE_REJECTED',
      updatedAt: '2026-10-09T07:00:00Z',
    }
    const record: SaBookingRecord = {
      estimateVersion: 2,
      saDraftOpen: false,
      activity: [
        {
          id: 'returned',
          kind: 'returned-to-technician',
          at: '2026-10-09T08:00:00Z',
          by: 'Bilal',
          role: 'SERVICE_ADVISOR',
          version: 2,
          note: 'Skip the AC gas top-up.',
        },
      ],
      loops: [
        { at: '2026-10-09T08:00:00Z', reentry: 'INSPECTING', steps: historySince(rejected, []) },
      ],
    }
    const resubmitted: MockBooking = {
      ...rejected,
      status: 'ESTIMATE_REVIEW',
      updatedAt: '2026-10-09T09:00:00Z',
    }
    const entries = buildActivity(resubmitted, record, { technician: 'Hamza' })
    expect(entries.map((entry) => entry.title)).toEqual([
      'Estimate submitted for review',
      'Returned to Hamza to re-inspect',
      'Estimate declined',
      'Estimate sent to the customer',
      'Estimate submitted for review',
      'Inspection started',
      'Assigned to Hamza',
      'Booking confirmed',
      'Booking requested',
    ])
    expect(entries[0]?.at).toBe('2026-10-09T09:00:00.000Z')
    expect(entries[1]?.note).toBe('Skip the AC gas top-up.')
  })
})
