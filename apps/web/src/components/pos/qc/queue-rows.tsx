import {
  ChevronRight,
  ClipboardCheck,
  Clock,
  ListChecks,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  UserRound,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'

import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { inspectedAgo, isRetest, qcResultOf, sinceLabel, vehicleName, waitedFor } from './qc-data'
import { PlateTag } from './qc-ui'

/** The left part of a queue row: icon tile, reference, vehicle, plate, technician and services. */
function JobSummary({ booking, icon: Icon }: { booking: MockBooking; icon: LucideIcon }) {
  const technician = booking.assignedTechnicianName
  return (
    <div className="flex min-w-0 gap-3 @lg/queue:gap-4">
      <span
        aria-hidden="true"
        className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-status-repair-qc-bg text-status-repair-qc-fg"
      >
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-mono text-sm font-semibold text-brand-blue-ink">
            {booking.reference}
          </span>
          {isRetest(booking) ? (
            <Badge variant="warning">
              <RotateCcw aria-hidden="true" />
              Re-test
            </Badge>
          ) : null}
        </p>
        <h3 className="text-base leading-6 font-semibold text-foreground">
          {vehicleName(booking)}
        </h3>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          <PlateTag plate={booking.licensePlate} />
          {technician ? <span>Repaired by {technician}</span> : null}
        </p>
        {booking.services.length > 0 ? (
          <p className="line-clamp-2 text-sm text-helper">{booking.services.join(', ')}</p>
        ) : null}
      </div>
    </div>
  )
}

const ACTION_ROW =
  'mt-4 flex flex-col gap-3 @lg/queue:flex-row @lg/queue:items-center @lg/queue:justify-between @lg/queue:pl-14'

export interface WaitingRowProps {
  booking: MockBooking
  href: string
  now: Date
  /** The view's one primary action (the oldest waiting job when you have none in progress). */
  primary: boolean
  /** The Owner's read-only view (D16): no pick. */
  readOnly: boolean
  onPick: (booking: MockBooking) => void
}

/** QI-01 "Waiting" row: the car, how long it has waited, and Inspect / Pick job (48px). */
export function WaitingRow({ booking, href, now, primary, readOnly, onPick }: WaitingRowProps) {
  const waited = waitedFor(booking.updatedAt, now)
  const sr = <span className="sr-only"> {booking.reference}</span>
  return (
    <li className="px-5 py-4 sm:px-6">
      <JobSummary booking={booking} icon={ListChecks} />
      <div className={ACTION_ROW}>
        {waited ? (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Clock className="size-4 shrink-0 text-helper" aria-hidden="true" />
            <span>
              Waiting <span className="font-semibold text-foreground">{waited}</span>
            </span>
          </p>
        ) : (
          <span />
        )}
        {readOnly ? (
          <Button asChild variant="outline" size="lg" className="w-full @lg/queue:w-auto">
            <Link href={href}>View{sr}</Link>
          </Button>
        ) : (
          <div className="grid grid-cols-2 gap-2 @lg/queue:flex">
            <Button asChild variant="outline" size="lg">
              <Link href={href}>Inspect{sr}</Link>
            </Button>
            <Button
              size="lg"
              variant={primary ? 'default' : 'outline'}
              onClick={() => onPick(booking)}
            >
              Pick job{sr}
            </Button>
          </div>
        )}
      </div>
    </li>
  )
}

export interface InProgressRowProps {
  booking: MockBooking
  href: string
  now: Date
  timeZone: string
  /** You picked it (or nobody is recorded as the picker), so you can carry on. */
  canContinue: boolean
  /** You are the recorded picker. */
  mine: boolean
  inspectorName: string | null
  primary: boolean
  readOnly: boolean
  /** Lets the queue move focus here right after a pick. */
  continueId: string
}

/** QI-01 "In progress" row: who is inspecting since when; your own rows continue the checklist. */
export function InProgressRow({
  booking,
  href,
  now,
  timeZone,
  canContinue,
  mine,
  inspectorName,
  primary,
  readOnly,
  continueId,
}: InProgressRowProps) {
  const since = sinceLabel(booking.updatedAt, now, timeZone)
  const sr = <span className="sr-only"> {booking.reference}</span>
  const who = mine ? (
    <span className="font-semibold text-foreground">You&apos;re inspecting</span>
  ) : inspectorName ? (
    <>
      <span className="font-semibold text-foreground">{inspectorName}</span> is inspecting
    </>
  ) : (
    <span className="font-semibold text-foreground">Being inspected</span>
  )
  return (
    <li className="px-5 py-4 sm:px-6">
      <JobSummary booking={booking} icon={ClipboardCheck} />
      <div className={ACTION_ROW}>
        <p className="flex items-start gap-1.5 text-sm text-muted-foreground">
          <UserRound className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
          <span>
            {who}
            {since ? ` since ${since}` : null}
          </span>
        </p>
        {canContinue && !readOnly ? (
          <Button
            asChild
            size="lg"
            variant={primary ? 'default' : 'outline'}
            className="w-full @lg/queue:w-auto"
          >
            <Link id={continueId} href={href}>
              Continue inspection{sr}
            </Link>
          </Button>
        ) : (
          <Button asChild variant="outline" size="lg" className="w-full @lg/queue:w-auto">
            <Link href={href}>View{sr}</Link>
          </Button>
        )}
      </div>
    </li>
  )
}

/** QI-01 "Recently inspected" row: the whole row opens the job's QC result. */
export function InspectedRow({
  booking,
  href,
  now,
  inspectorName,
}: {
  booking: MockBooking
  href: string
  now: Date
  inspectorName: string | null
}) {
  const passed = qcResultOf(booking) === 'passed'
  const Icon = passed ? ShieldCheck : ShieldX
  const when = inspectedAgo(booking, now)
  const meta = [inspectorName ? `Inspected by ${inspectorName}` : null, when || null]
    .filter(Boolean)
    .join(' · ')
  return (
    <li>
      <Link
        href={href}
        className="group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6"
      >
        <span
          aria-hidden="true"
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-xl',
            passed ? 'bg-success-subtle text-success-ink' : 'bg-danger-subtle text-danger-ink',
          )}
        >
          <Icon className="size-5" />
        </span>
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-sm font-semibold text-brand-blue-ink">
              {booking.reference}
            </span>
            <Badge variant={passed ? 'success' : 'destructive'}>
              {passed ? 'Passed QC' : 'Failed QC'}
            </Badge>
            <StatusBadge status={booking.status} audience="staff" />
          </span>
          <span className="block text-sm font-medium text-foreground">
            {vehicleName(booking)} ·{' '}
            <span className="font-mono font-normal whitespace-nowrap text-muted-foreground">
              {booking.licensePlate}
            </span>
          </span>
          {meta ? <span className="block text-xs text-helper">{meta}</span> : null}
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </Link>
    </li>
  )
}
