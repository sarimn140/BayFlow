import {
  Ban,
  BellRing,
  CalendarCheck,
  CarFront,
  CircleCheckBig,
  CircleX,
  ClipboardCheck,
  ClipboardList,
  FileCheck,
  FilePen,
  FileX,
  Inbox,
  ListChecks,
  PackageCheck,
  PackageSearch,
  PencilLine,
  ScanSearch,
  Send,
  Truck,
  Undo2,
  UserCheck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import type { TimelineTone } from '@/components/layout/timeline'
import {
  bookingHistory,
  type BookingHistoryStep,
  type HistoryActorRole,
} from '@/lib/mock-booking-history'
import type { MockBooking } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

import type { SaActivity, SaActorRole, SaBookingRecord, SaLoop } from './sa-records'

/**
 * SA-02's activity (spec 09 §4.4, staff audience): the booking's status history from the shared
 * mock (`bookingHistory`, so notifications and the admin timeline agree), plus the Service
 * Advisor's own events, the history kept at each estimate loop and the real decline or cancel.
 * Newest first.
 */

export interface ActivityEntry {
  id: string
  at: string
  title: string
  /** "Bilal · Service advisor". */
  actor: string
  /** A reason or note, shown under the entry. */
  note?: string
  icon: LucideIcon
  tone: TimelineTone
}

const ROLE_NAMES: Record<HistoryActorRole | SaActorRole, string> = {
  CUSTOMER: 'Customer',
  SERVICE_ADVISOR: 'Service advisor',
  OWNER: 'Owner',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts person',
  QC_INSPECTOR: 'QC inspector',
}

interface Names {
  technician?: string
  partsPerson?: string
}

const STEPS: Record<
  BookingStatus,
  { title: (names: Names) => string; icon: LucideIcon; tone: TimelineTone }
> = {
  PENDING: { title: () => 'Booking requested', icon: Inbox, tone: 'default' },
  CONFIRMED: { title: () => 'Booking confirmed', icon: CalendarCheck, tone: 'brand' },
  ASSIGNED: {
    title: ({ technician }) => (technician ? `Assigned to ${technician}` : 'Technician assigned'),
    icon: UserCheck,
    tone: 'brand',
  },
  INSPECTING: { title: () => 'Inspection started', icon: ScanSearch, tone: 'default' },
  ESTIMATE_REVIEW: {
    title: () => 'Estimate submitted for review',
    icon: ClipboardList,
    tone: 'default',
  },
  AWAITING_CUSTOMER: { title: () => 'Estimate sent to the customer', icon: Send, tone: 'brand' },
  ESTIMATE_APPROVED: { title: () => 'Estimate approved', icon: FileCheck, tone: 'success' },
  ESTIMATE_REJECTED: { title: () => 'Estimate declined', icon: FileX, tone: 'danger' },
  PARTS_PENDING: {
    title: ({ partsPerson }) =>
      partsPerson ? `Parts job assigned to ${partsPerson}` : 'Parts person assigned',
    icon: PackageSearch,
    tone: 'brand',
  },
  PARTS_ORDERED: { title: () => 'Missing parts ordered', icon: Truck, tone: 'default' },
  PARTS_READY: { title: () => 'Parts reserved', icon: PackageCheck, tone: 'default' },
  IN_REPAIR: { title: () => 'Parts allocated to the repair', icon: Wrench, tone: 'default' },
  QC_PENDING: { title: () => 'Sent to quality check', icon: ListChecks, tone: 'default' },
  QC_IN_PROGRESS: { title: () => 'Quality check started', icon: ClipboardCheck, tone: 'default' },
  READY_FOR_PICKUP: {
    title: () => 'Passed quality check, ready for pick-up',
    icon: CarFront,
    tone: 'success',
  },
  COMPLETED: { title: () => 'Booking completed', icon: CircleCheckBig, tone: 'success' },
  CANCELLED: { title: () => 'Booking cancelled', icon: Ban, tone: 'danger' },
}

function activityEntry(entry: SaActivity, booking: MockBooking, names: Names): ActivityEntry {
  const actor = `${entry.by} · ${ROLE_NAMES[entry.role]}`
  switch (entry.kind) {
    case 'estimate-edited':
      return {
        id: entry.id,
        at: entry.at,
        title: `Estimate edited, now v${entry.version ?? '?'}`,
        actor,
        icon: PencilLine,
        tone: 'brand',
      }
    case 'estimate-revised':
      return {
        id: entry.id,
        at: entry.at,
        title: `Estimate revised as draft v${entry.version ?? '?'}`,
        actor,
        icon: FilePen,
        tone: 'brand',
      }
    case 'returned-to-technician':
      return {
        id: entry.id,
        at: entry.at,
        title: `Returned to ${names.technician ?? 'the technician'} to re-inspect`,
        actor,
        note: entry.note,
        icon: Undo2,
        tone: 'warning',
      }
    case 'ready-notice':
      return {
        id: entry.id,
        at: entry.at,
        title: `Pick-up notice sent to ${booking.customerName}`,
        actor,
        icon: BellRing,
        tone: 'brand',
      }
  }
}

const time = (value: string) => {
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

/**
 * The status steps since the latest estimate loop, or all of them when there was none. The shared
 * mock only knows the happy path, so after a loop it keeps the statuses that follow the re-entry
 * status, spread between the loop and the booking's last update (`updatedAt`).
 */
export function historySince(
  booking: MockBooking,
  loops: ReadonlyArray<SaLoop>,
): BookingHistoryStep[] {
  const steps = bookingHistory(booking)
  const loop = loops.at(-1)
  if (!loop) return steps
  const index = steps.findIndex((step) => step.status === loop.reentry)
  // A path without the re-entry status is "Pending → Cancelled": keep the cancel.
  const after = index < 0 ? steps.slice(-1) : steps.slice(index + 1)
  const start = time(loop.at)
  const end = Math.max(start, time(booking.updatedAt))
  return after.map((step, position) => ({
    ...step,
    at: new Date(start + ((end - start) * (position + 1)) / after.length).toISOString(),
  }))
}

/**
 * The booking's status steps, oldest first: the history kept at each estimate loop, then the
 * steps since. A decline or cancel recorded here rebuilds the path up to the status it left (the
 * shared mock only knows "Pending → Cancelled"); `buildActivity` adds the cancel itself.
 */
export function statusSteps(booking: MockBooking, record: SaBookingRecord): BookingHistoryStep[] {
  const cancellation = booking.status === 'CANCELLED' ? record.cancellation : undefined
  const source: MockBooking = cancellation
    ? { ...booking, status: cancellation.fromStatus, updatedAt: cancellation.previousUpdatedAt }
    : booking
  const created = time(booking.createdAt)
  const loops = (record.loops ?? []).filter((loop) => time(loop.at) >= created)
  // Each loop's revise or return event stands for its re-entry status, so that step isn't repeated.
  return [...loops.flatMap((loop) => loop.steps), ...historySince(source, loops)]
}

/** When the booking last entered `status`, as the activity shows it. */
export function lastEnteredAt(
  steps: ReadonlyArray<BookingHistoryStep>,
  status: BookingStatus,
): string | undefined {
  return steps.findLast((step) => step.status === status)?.at
}

export function buildActivity(
  booking: MockBooking,
  record: SaBookingRecord,
  names: Names,
): ActivityEntry[] {
  const cancellation = booking.status === 'CANCELLED' ? record.cancellation : undefined
  const created = time(booking.createdAt)
  const activity = record.activity.filter((entry) => time(entry.at) >= created)
  const steps = statusSteps(booking, record)

  // Oldest first here; `seq` keeps that order between entries with the same time.
  const entries: ActivityEntry[] = []
  steps.forEach((step, index) => {
    const meta = STEPS[step.status]
    entries.push({
      id: `${step.status}-${index}`,
      at: step.at,
      title: meta.title(names),
      actor: `${step.actorName} · ${ROLE_NAMES[step.actorRole]}`,
      icon: meta.icon,
      tone: meta.tone,
    })
  })
  for (const entry of activity) entries.push(activityEntry(entry, booking, names))
  if (cancellation) {
    entries.push({
      id: 'cancellation',
      at: cancellation.at,
      title: cancellation.kind === 'decline' ? 'Booking declined' : 'Booking cancelled',
      actor: `${cancellation.by} · ${ROLE_NAMES[cancellation.role]}`,
      note: cancellation.reason,
      icon: cancellation.kind === 'decline' ? CircleX : Ban,
      tone: 'danger',
    })
  }
  return entries
    .map((entry, seq) => ({ entry, seq }))
    .sort((a, b) => time(b.entry.at) - time(a.entry.at) || b.seq - a.seq)
    .map(({ entry }) => entry)
}
