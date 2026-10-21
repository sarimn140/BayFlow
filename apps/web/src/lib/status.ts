/**
 * Booking status vocabulary — exactly glossary §3 (spec 18). Staff labels are used in the POS,
 * customer labels in the customer portal (UX rule R5); phases group statuses for colour and
 * filters (spec 09 §3.3). The UI never derives permissions from a status: buttons come only
 * from `allowed_actions` (D48).
 *
 * TODO(api types): once the API's OpenAPI document exports `BookingStatus`, assert at compile
 * time that `BookingStatus` below equals `components['schemas']['BookingStatus']` (D50, D76).
 */

/** All 17 values in glossary §3 order. */
export const BOOKING_STATUSES = [
  'PENDING',
  'CONFIRMED',
  'ASSIGNED',
  'INSPECTING',
  'ESTIMATE_REVIEW',
  'AWAITING_CUSTOMER',
  'ESTIMATE_APPROVED',
  'ESTIMATE_REJECTED',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
  'READY_FOR_PICKUP',
  'COMPLETED',
  'CANCELLED',
] as const

export type BookingStatus = (typeof BOOKING_STATUSES)[number]

/** `StatusPhase` (glossary §5): UI grouping only, never stored. */
export const STATUS_PHASES = [
  'INTAKE',
  'INSPECTION',
  'ESTIMATE',
  'PARTS',
  'REPAIR_QC',
  'HANDOVER',
  'CLOSED',
] as const

export type StatusPhase = (typeof STATUS_PHASES)[number]

/** Display names of the phases (spec 09 §3.3). */
export const STATUS_PHASE_LABELS = {
  INTAKE: 'Intake',
  INSPECTION: 'Inspection',
  ESTIMATE: 'Estimate',
  PARTS: 'Parts',
  REPAIR_QC: 'Repair & QC',
  HANDOVER: 'Hand-over',
  CLOSED: 'Closed',
} as const satisfies Record<StatusPhase, string>

export interface BookingStatusMeta {
  /** POS label (glossary §3 "Staff label"). */
  staffLabel: string
  /** Customer portal label (glossary §3 "Customer-facing label"). */
  customerLabel: string
  phase: StatusPhase
  /** `COMPLETED` and `CANCELLED` end the lifecycle. */
  terminal: boolean
}

/** One entry per status; `satisfies` makes the build fail if a status is missing. */
export const BOOKING_STATUS_META = {
  PENDING: {
    staffLabel: 'Pending',
    customerLabel: 'Booking received',
    phase: 'INTAKE',
    terminal: false,
  },
  CONFIRMED: {
    staffLabel: 'Confirmed',
    customerLabel: 'Booking confirmed',
    phase: 'INTAKE',
    terminal: false,
  },
  ASSIGNED: {
    staffLabel: 'Assigned',
    customerLabel: 'Technician assigned',
    phase: 'INSPECTION',
    terminal: false,
  },
  INSPECTING: {
    staffLabel: 'Inspecting',
    customerLabel: 'Inspection in progress',
    phase: 'INSPECTION',
    terminal: false,
  },
  ESTIMATE_REVIEW: {
    staffLabel: 'Estimate review',
    customerLabel: 'Preparing your estimate',
    phase: 'ESTIMATE',
    terminal: false,
  },
  AWAITING_CUSTOMER: {
    staffLabel: 'Awaiting customer',
    customerLabel: 'Estimate awaiting your approval',
    phase: 'ESTIMATE',
    terminal: false,
  },
  ESTIMATE_APPROVED: {
    staffLabel: 'Estimate approved',
    customerLabel: 'Estimate approved',
    phase: 'ESTIMATE',
    terminal: false,
  },
  ESTIMATE_REJECTED: {
    staffLabel: 'Estimate rejected',
    customerLabel: 'Estimate declined — the shop will follow up',
    phase: 'ESTIMATE',
    terminal: false,
  },
  PARTS_PENDING: {
    staffLabel: 'Parts pending',
    customerLabel: 'Checking parts',
    phase: 'PARTS',
    terminal: false,
  },
  PARTS_ORDERED: {
    staffLabel: 'Parts ordered',
    customerLabel: 'Parts ordered',
    phase: 'PARTS',
    terminal: false,
  },
  PARTS_READY: {
    staffLabel: 'Parts ready',
    customerLabel: 'Parts ready',
    phase: 'PARTS',
    terminal: false,
  },
  IN_REPAIR: {
    staffLabel: 'In repair',
    customerLabel: 'Repair in progress',
    phase: 'REPAIR_QC',
    terminal: false,
  },
  QC_PENDING: {
    staffLabel: 'QC pending',
    customerLabel: 'Waiting for quality check',
    phase: 'REPAIR_QC',
    terminal: false,
  },
  QC_IN_PROGRESS: {
    staffLabel: 'QC in progress',
    customerLabel: 'Quality check in progress',
    phase: 'REPAIR_QC',
    terminal: false,
  },
  READY_FOR_PICKUP: {
    staffLabel: 'Ready for pick-up',
    customerLabel: 'Ready for pick-up',
    phase: 'HANDOVER',
    terminal: false,
  },
  COMPLETED: {
    staffLabel: 'Completed',
    customerLabel: 'Completed',
    phase: 'HANDOVER',
    terminal: true,
  },
  CANCELLED: {
    staffLabel: 'Cancelled',
    customerLabel: 'Cancelled',
    phase: 'CLOSED',
    terminal: true,
  },
} as const satisfies Record<BookingStatus, BookingStatusMeta>

/** Glossary §3: the 11 statuses a customer or SA may cancel from ("before IN_REPAIR"). */
export const CANCELLABLE_STATUSES = [
  'PENDING',
  'CONFIRMED',
  'ASSIGNED',
  'INSPECTING',
  'ESTIMATE_REVIEW',
  'AWAITING_CUSTOMER',
  'ESTIMATE_APPROVED',
  'ESTIMATE_REJECTED',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
] as const satisfies ReadonlyArray<BookingStatus>

export type StatusAudience = 'staff' | 'customer'

export function isBookingStatus(value: unknown): value is BookingStatus {
  return typeof value === 'string' && (BOOKING_STATUSES as ReadonlyArray<string>).includes(value)
}

/** The label for one audience: POS screens use `staff`, the customer portal `customer`. */
export function statusLabel(status: BookingStatus, audience: StatusAudience): string {
  const meta = BOOKING_STATUS_META[status]
  return audience === 'customer' ? meta.customerLabel : meta.staffLabel
}

export function statusPhase(status: BookingStatus): StatusPhase {
  return BOOKING_STATUS_META[status].phase
}

/** Statuses of one phase, in lifecycle order (filter chips, overview bars). */
export function statusesInPhase(phase: StatusPhase): BookingStatus[] {
  return BOOKING_STATUSES.filter((status) => BOOKING_STATUS_META[status].phase === phase)
}
