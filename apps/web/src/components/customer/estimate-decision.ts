import type { MockBooking } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/** Where the customer's decision on the estimate stands (C-01 card, C-02 estimate card). */
export type EstimateDecision = 'pending' | 'approved' | 'declined'

/** Statuses in which the customer has seen the estimate and it was not declined. */
const ESTIMATE_APPROVED_OR_LATER: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'ESTIMATE_APPROVED',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
  'READY_FOR_PICKUP',
  'COMPLETED',
])

/**
 * The estimate the customer may see (D39: only a version the shop has sent) and where their
 * decision stands: awaiting it, declined or approved. Null before the shop sends one (E-11
 * `estimate_summary: null`), so neither My bookings nor the booking page shows a price the shop
 * hasn't quoted. One rule for both screens.
 */
export function estimateDecisionOf(
  booking: Pick<MockBooking, 'status' | 'estimateItems' | 'estimateApproved'>,
): EstimateDecision | null {
  if (booking.status === 'AWAITING_CUSTOMER') return 'pending'
  if (booking.status === 'ESTIMATE_REJECTED') return 'declined'
  if (booking.estimateItems.length === 0) return null
  if (ESTIMATE_APPROVED_OR_LATER.has(booking.status)) return 'approved'
  if (booking.status === 'CANCELLED' && booking.estimateApproved) return 'approved'
  return null
}
