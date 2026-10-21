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
import type { ComponentProps } from 'react'

import { BOOKING_STATUS_META, type BookingStatus, type StatusPhase } from '@/lib/status'
import { cn } from '@/lib/utils'

/** `CardTitle`'s look on a real `<h2>`, so the page keeps its heading outline. */
export function CardHeading({ className, ...props }: ComponentProps<'h2'>) {
  return (
    <h2
      data-slot="card-title"
      className={cn('text-lg leading-7 font-semibold text-card-foreground', className)}
      {...props}
    />
  )
}

/** The status icons of `StatusBadge` (spec 09 §3.3), for the next-step tile. */
const STATUS_ICONS = {
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

/** Phase tints (DESIGN.md §2.2: the phase tokens may tint an icon tile of that phase). */
const PHASE_TILES = {
  INTAKE: 'bg-status-intake-bg text-status-intake-fg',
  INSPECTION: 'bg-status-inspection-bg text-status-inspection-fg',
  ESTIMATE: 'bg-status-estimate-bg text-status-estimate-fg',
  PARTS: 'bg-status-parts-bg text-status-parts-fg',
  REPAIR_QC: 'bg-status-repair-qc-bg text-status-repair-qc-fg',
  HANDOVER: 'bg-status-handover-bg text-status-handover-fg',
  CLOSED: 'bg-status-closed-bg text-status-closed-fg',
} satisfies Record<StatusPhase, string>

/** A 40px tile in the status's phase colour with its icon (decorative: the text says it all). */
export function StatusTile({ status, className }: { status: BookingStatus; className?: string }) {
  const Icon = STATUS_ICONS[status]
  const tint =
    status === 'ESTIMATE_REJECTED'
      ? 'bg-status-estimate-rejected-bg text-status-estimate-rejected-fg'
      : PHASE_TILES[BOOKING_STATUS_META[status].phase]
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-xl',
        tint,
        className,
      )}
    >
      <Icon className="size-5" />
    </span>
  )
}

/** Up to two initials for an avatar tile: "Tariq Jamil" → "TJ". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  const first = words[0]?.[0] ?? '?'
  const last = words.length > 1 ? (words.at(-1)?.[0] ?? '') : ''
  return `${first}${last}`.toUpperCase()
}
