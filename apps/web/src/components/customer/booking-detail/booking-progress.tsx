import {
  Ban,
  CalendarCheck,
  CarFront,
  Check,
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

import { Timeline, type TimelineItem, type TimelineTone } from '@/components/layout/timeline'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { bookingHistory } from '@/lib/mock-booking-history'
import type { MockBooking } from '@/lib/mock-data'
import { statusLabel, statusPhase, type BookingStatus, type StatusPhase } from '@/lib/status'

import { formatShortDateTime } from './format'

/** The same icon per status as `StatusBadge` (spec 09 §3.3), so a step and its chip match. */
const STATUS_ICON: Record<BookingStatus, LucideIcon> = {
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
  COMPLETED: Check,
  CANCELLED: Ban,
}

/**
 * The customer's journey (spec 09 §4.4): the happy-path phases, Intake → Inspection → Estimate →
 * Parts → Repair & QC → Pick-up. `doneAt` is the status that completes the step; its time is
 * the step's time once it is done.
 */
const MILESTONES: ReadonlyArray<{
  phase: Exclude<StatusPhase, 'CLOSED'>
  title: string
  done: string
  ahead: string
  icon: LucideIcon
  doneAt: BookingStatus
}> = [
  {
    phase: 'INTAKE',
    title: 'Booking confirmed',
    done: 'Booking confirmed',
    ahead: 'The shop confirms your slot.',
    icon: CalendarCheck,
    doneAt: 'CONFIRMED',
  },
  {
    phase: 'INSPECTION',
    title: 'Inspection',
    done: 'Inspection complete',
    ahead: 'A technician checks your car.',
    icon: ScanSearch,
    doneAt: 'ESTIMATE_REVIEW',
  },
  {
    phase: 'ESTIMATE',
    title: 'Estimate approval',
    done: 'Estimate approved',
    ahead: 'You approve the price before any work starts.',
    icon: FileCheck,
    doneAt: 'ESTIMATE_APPROVED',
  },
  {
    phase: 'PARTS',
    title: 'Parts',
    done: 'Parts ready',
    ahead: 'The shop gets the parts ready.',
    icon: PackageCheck,
    doneAt: 'PARTS_READY',
  },
  {
    phase: 'REPAIR_QC',
    title: 'Repair and quality check',
    done: 'Repaired and checked',
    ahead: 'Your car is repaired, then checked by an inspector.',
    icon: Wrench,
    doneAt: 'READY_FOR_PICKUP',
  },
  {
    phase: 'HANDOVER',
    title: 'Ready for pick-up',
    done: 'Collected',
    ahead: 'Collect your car from the shop.',
    icon: CarFront,
    doneAt: 'COMPLETED',
  },
]

/** What the current step means for the customer, and its tone. */
const NOW: Record<
  Exclude<BookingStatus, 'COMPLETED' | 'CANCELLED'>,
  { text: string; tone: TimelineTone; title?: string }
> = {
  PENDING: { text: 'The shop will confirm your slot shortly.', tone: 'brand' },
  CONFIRMED: { text: 'Bring your car in at your booked time.', tone: 'brand' },
  ASSIGNED: { text: 'A technician will inspect your car soon.', tone: 'brand' },
  INSPECTING: { text: 'A technician is checking your car.', tone: 'brand' },
  ESTIMATE_REVIEW: { text: "We'll let you know when your estimate is ready.", tone: 'brand' },
  AWAITING_CUSTOMER: {
    text: 'Review the estimate and approve it to start the repair.',
    tone: 'warning',
  },
  ESTIMATE_APPROVED: {
    text: 'Approved by you. The shop is getting the parts ready.',
    tone: 'success',
  },
  ESTIMATE_REJECTED: {
    title: 'Estimate declined',
    text: 'You declined it. The shop will follow up with options.',
    tone: 'danger',
  },
  PARTS_PENDING: { text: 'The shop is checking the parts your repair needs.', tone: 'brand' },
  PARTS_ORDERED: { text: 'Some parts are on their way to the shop.', tone: 'brand' },
  PARTS_READY: { text: 'All parts are in. Your repair starts soon.', tone: 'brand' },
  IN_REPAIR: { text: 'A technician is working on your car.', tone: 'brand' },
  QC_PENDING: { text: 'The repair is done. An inspector checks it next.', tone: 'brand' },
  QC_IN_PROGRESS: { text: 'An inspector is checking the work.', tone: 'brand' },
  READY_FOR_PICKUP: { text: 'Your car is ready. Collect it from the shop.', tone: 'success' },
}

const PHASES = MILESTONES.map((m) => m.phase as StatusPhase)

function When({ iso, timeZone }: { iso: string | undefined; timeZone: string }) {
  return iso ? <time dateTime={iso}>{formatShortDateTime(iso, timeZone)}</time> : null
}

/** The timeline entries: done steps with their time, the current step, then the steps ahead. */
function progressItems(booking: MockBooking, timeZone: string): TimelineItem[] {
  const history = bookingHistory(booking)
  const at = (status: BookingStatus) => history.find((step) => step.status === status)?.at
  const status = booking.status

  if (status === 'CANCELLED') {
    return [
      {
        id: 'received',
        title: (
          <>
            <span className="sr-only">Done: </span>Booking received
          </>
        ),
        time: <When iso={at('PENDING')} timeZone={timeZone} />,
        icon: Check,
        tone: 'success',
      },
      {
        id: 'cancelled',
        title: (
          <>
            <span className="sr-only">Current step: </span>Booking cancelled
          </>
        ),
        description: 'This booking is closed.',
        time: <When iso={at('CANCELLED')} timeZone={timeZone} />,
        icon: Ban,
        tone: 'danger',
      },
    ]
  }

  const current = status === 'COMPLETED' ? MILESTONES.length : PHASES.indexOf(statusPhase(status))
  return MILESTONES.map((step, index): TimelineItem => {
    if (index < current) {
      return {
        id: step.phase,
        title: (
          <>
            <span className="sr-only">Done: </span>
            {step.done}
          </>
        ),
        description: step.phase === 'ESTIMATE' ? 'Approved by you' : undefined,
        time: <When iso={at(step.doneAt)} timeZone={timeZone} />,
        icon: Check,
        tone: 'success',
      }
    }
    if (index === current && status !== 'COMPLETED') {
      const now = NOW[status]
      return {
        id: step.phase,
        title: (
          <>
            <span className="sr-only">Current step: </span>
            {now.title ?? statusLabel(status, 'customer')}
          </>
        ),
        description: now.text,
        time: <When iso={history[history.length - 1]?.at} timeZone={timeZone} />,
        icon: STATUS_ICON[status],
        tone: now.tone,
      }
    }
    return {
      id: step.phase,
      title: (
        <span className="font-medium text-muted-foreground">
          <span className="sr-only">Upcoming: </span>
          {step.title}
        </span>
      ),
      description: step.ahead,
      time: index === current + 1 ? 'Up next' : undefined,
      icon: step.icon,
      tone: 'default',
    }
  })
}

/** C-02 "Status timeline" (spec 09 §4.4, customer audience): the journey, oldest first. */
export function BookingProgress({ booking, timeZone }: { booking: MockBooking; timeZone: string }) {
  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg leading-7 font-semibold text-foreground">Progress</h2>
        <CardDescription>Updates appear here as the shop works on your car.</CardDescription>
      </CardHeader>
      <CardContent>
        <Timeline aria-label="Booking progress" items={progressItems(booking, timeZone)} />
      </CardContent>
    </Card>
  )
}
