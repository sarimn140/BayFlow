import type { MockPart } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/**
 * Status groups of the overview tiles and the owner summary, mirroring the API
 * (`apps/api/app/modules/reporting/domain/kpis.py`), so the screens and the API count alike.
 */

/** Waiting on a Service Advisor (READY_FOR_PICKUP is also counted on its own). */
export const SA_ACTION_STATUSES: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'PENDING',
  'CONFIRMED',
  'ESTIMATE_REVIEW',
  'ESTIMATE_APPROVED',
  'ESTIMATE_REJECTED',
  'READY_FOR_PICKUP',
])

/** Every other status that is not final: with the technician, the customer, parts or QC. */
export const IN_PROGRESS_STATUSES: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'ASSIGNED',
  'INSPECTING',
  'AWAITING_CUSTOMER',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
])

/** D45: LOW or OUT — what is available (on hand minus reserved) is at or below the reorder level. */
export function isLowStock(
  part: Pick<MockPart, 'on_hand' | 'reserved' | 'reorder_level'>,
): boolean {
  return part.on_hand - part.reserved <= part.reorder_level
}
