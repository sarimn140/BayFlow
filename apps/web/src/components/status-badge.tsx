import {
  Ban,
  CalendarCheck,
  CarFront,
  CircleCheckBig,
  ClipboardCheck,
  ClipboardList,
  FileCheck,
  FileX,
  Hourglass,
  Inbox,
  ListChecks,
  PackageCheck,
  PackageSearch,
  ScanSearch,
  Truck,
  UserCheck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  BOOKING_STATUS_META,
  statusLabel,
  type BookingStatus,
  type StatusAudience,
  type StatusPhase,
} from '@/lib/status'
import { cn } from '@/lib/utils'

/** Icon per status (spec 09 §3.3). Colour is never the only signal: icon + text label always. */
/** The icon for each status, shared with timelines so a status looks the same everywhere. */
export const STATUS_ICONS = {
  PENDING: Inbox,
  CONFIRMED: CalendarCheck,
  ASSIGNED: UserCheck,
  INSPECTING: ScanSearch,
  ESTIMATE_REVIEW: ClipboardList,
  AWAITING_CUSTOMER: Hourglass,
  ESTIMATE_APPROVED: FileCheck,
  ESTIMATE_REJECTED: FileX,
  PARTS_PENDING: PackageSearch,
  PARTS_ORDERED: Truck,
  PARTS_READY: PackageCheck,
  IN_REPAIR: Wrench,
  QC_PENDING: ListChecks,
  QC_IN_PROGRESS: ClipboardCheck,
  READY_FOR_PICKUP: CarFront,
  COMPLETED: CircleCheckBig,
  CANCELLED: Ban,
} satisfies Record<BookingStatus, LucideIcon>

/** Badge variant per phase: hue = phase, so lists can be scanned by phase (spec 09 §3.3). */
const PHASE_VARIANTS = {
  INTAKE: 'intake',
  INSPECTION: 'inspection',
  ESTIMATE: 'estimate',
  PARTS: 'parts',
  REPAIR_QC: 'repair-qc',
  HANDOVER: 'handover',
  CLOSED: 'closed',
} as const satisfies Record<StatusPhase, string>

export interface StatusBadgeProps {
  status: BookingStatus
  /** `staff` labels in the POS, `customer` labels in the customer portal (UX rule R5). */
  audience: StatusAudience
  /** `sm` (24px) in lists and tables; `md` (28px, 14px label) beside a page title. */
  size?: 'sm' | 'md'
  className?: string
}

/**
 * Booking status chip (DESIGN.md "Status chips"): a soft pill in the phase's hue with a 1px
 * border, the status icon and the audience's label. Same hue and icon for every role.
 */
export function StatusBadge({ status, audience, size = 'sm', className }: StatusBadgeProps) {
  const Icon = STATUS_ICONS[status]
  // ESTIMATE_REJECTED keeps the estimate phase but uses the red override.
  const variant =
    status === 'ESTIMATE_REJECTED'
      ? 'estimate-rejected'
      : PHASE_VARIANTS[BOOKING_STATUS_META[status].phase]

  return (
    <Badge
      variant={variant}
      data-status={status}
      className={cn(
        size === 'md' &&
          'h-7 gap-1.5 px-3 text-sm has-data-[icon=inline-start]:pl-2.5 [&>svg]:size-4',
        className,
      )}
    >
      <Icon aria-hidden="true" data-icon="inline-start" />
      <span className="sr-only">Status: </span>
      {statusLabel(status, audience)}
    </Badge>
  )
}
