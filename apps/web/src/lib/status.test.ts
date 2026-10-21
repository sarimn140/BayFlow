import { describe, expect, it } from 'vitest'

import {
  BOOKING_STATUSES,
  BOOKING_STATUS_META,
  CANCELLABLE_STATUSES,
  STATUS_PHASES,
  isBookingStatus,
  statusLabel,
  statusPhase,
  statusesInPhase,
  type BookingStatus,
  type StatusPhase,
} from './status'

/** Glossary §3, copied row by row: value, staff label, customer label, phase, terminal. */
const GLOSSARY_SECTION_3: ReadonlyArray<[BookingStatus, string, string, StatusPhase, boolean]> = [
  ['PENDING', 'Pending', 'Booking received', 'INTAKE', false],
  ['CONFIRMED', 'Confirmed', 'Booking confirmed', 'INTAKE', false],
  ['ASSIGNED', 'Assigned', 'Technician assigned', 'INSPECTION', false],
  ['INSPECTING', 'Inspecting', 'Inspection in progress', 'INSPECTION', false],
  ['ESTIMATE_REVIEW', 'Estimate review', 'Preparing your estimate', 'ESTIMATE', false],
  ['AWAITING_CUSTOMER', 'Awaiting customer', 'Estimate awaiting your approval', 'ESTIMATE', false],
  ['ESTIMATE_APPROVED', 'Estimate approved', 'Estimate approved', 'ESTIMATE', false],
  [
    'ESTIMATE_REJECTED',
    'Estimate rejected',
    'Estimate declined — the shop will follow up',
    'ESTIMATE',
    false,
  ],
  ['PARTS_PENDING', 'Parts pending', 'Checking parts', 'PARTS', false],
  ['PARTS_ORDERED', 'Parts ordered', 'Parts ordered', 'PARTS', false],
  ['PARTS_READY', 'Parts ready', 'Parts ready', 'PARTS', false],
  ['IN_REPAIR', 'In repair', 'Repair in progress', 'REPAIR_QC', false],
  ['QC_PENDING', 'QC pending', 'Waiting for quality check', 'REPAIR_QC', false],
  ['QC_IN_PROGRESS', 'QC in progress', 'Quality check in progress', 'REPAIR_QC', false],
  ['READY_FOR_PICKUP', 'Ready for pick-up', 'Ready for pick-up', 'HANDOVER', false],
  ['COMPLETED', 'Completed', 'Completed', 'HANDOVER', true],
  ['CANCELLED', 'Cancelled', 'Cancelled', 'CLOSED', true],
]

describe('BookingStatus vocabulary (glossary §3, WEB-03)', () => {
  it('has exactly the 17 statuses, in glossary order', () => {
    expect(BOOKING_STATUSES).toHaveLength(17)
    expect([...BOOKING_STATUSES]).toEqual(GLOSSARY_SECTION_3.map(([status]) => status))
    expect(Object.keys(BOOKING_STATUS_META).sort()).toEqual([...BOOKING_STATUSES].sort())
  })

  it.each(GLOSSARY_SECTION_3)(
    '%s → staff "%s", customer "%s", phase %s, terminal %s',
    (status, staffLabel, customerLabel, phase, terminal) => {
      expect(BOOKING_STATUS_META[status]).toEqual({ staffLabel, customerLabel, phase, terminal })
      expect(statusLabel(status, 'staff')).toBe(staffLabel)
      expect(statusLabel(status, 'customer')).toBe(customerLabel)
      expect(statusPhase(status)).toBe(phase)
    },
  )

  it('lists the 11 cancellable statuses (everything before IN_REPAIR)', () => {
    expect(CANCELLABLE_STATUSES).toHaveLength(11)
    expect([...CANCELLABLE_STATUSES]).toEqual(
      BOOKING_STATUSES.slice(0, BOOKING_STATUSES.indexOf('IN_REPAIR')),
    )
  })

  it('assigns every status to exactly one of the 7 phases', () => {
    expect(STATUS_PHASES).toHaveLength(7)
    const grouped = STATUS_PHASES.flatMap((phase) => statusesInPhase(phase))
    expect(grouped.sort()).toEqual([...BOOKING_STATUSES].sort())
    expect(statusesInPhase('CLOSED')).toEqual(['CANCELLED'])
  })

  it('recognises status strings', () => {
    expect(isBookingStatus('QC_PENDING')).toBe(true)
    expect(isBookingStatus('qc_pending')).toBe(false)
    expect(isBookingStatus('DONE')).toBe(false)
    expect(isBookingStatus(undefined)).toBe(false)
  })
})
