import {
  ArrowRight,
  CalendarClock,
  ChevronRight,
  FileText,
  Play,
  ShieldAlert,
  UserRound,
  Wrench,
} from 'lucide-react'
import Link from 'next/link'

import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatPKR } from '@/lib/format'
import type { MockBooking } from '@/lib/mock-data'

import {
  attributeSelector,
  cardNextStep,
  countLabel,
  isQcReturned,
  parseQcIssue,
  slotLabel,
  STATUS_NOTE,
  vehicleLabel,
} from './job-model'
import { PlateTag } from './job-ui'

/**
 * Every card marks its main control with `data-job-action={booking.id}`, so focus can follow a job
 * that moves to another group after an inline action.
 */
export function jobActionSelector(bookingId: string): string {
  return attributeSelector('data-job-action', bookingId)
}

function EstimateLine({ booking }: { booking: MockBooking }) {
  const lines = booking.estimateItems.length
  if (booking.status === 'INSPECTING') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <FileText className="size-4 shrink-0 text-helper" aria-hidden="true" />
        {lines === 0 ? (
          'No estimate lines yet'
        ) : (
          <span>
            Estimate {countLabel(lines, 'line', 'lines')} ·{' '}
            <span className="font-medium text-foreground tabular-nums">
              {formatPKR(booking.estimateTotal)}
            </span>
          </span>
        )}
      </span>
    )
  }
  if (booking.estimateApproved && lines > 0) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <FileText className="size-4 shrink-0 text-helper" aria-hidden="true" />
        <span>
          Approved estimate ·{' '}
          <span className="font-medium text-foreground tabular-nums">
            {formatPKR(booking.estimateTotal)}
          </span>
        </span>
      </span>
    )
  }
  return null
}

export interface JobCardProps {
  booking: MockBooking
  /** The job's T-02 page. */
  href: string
  /** Show the assigned technician (the Owner's view, or someone else's job). */
  showTechnician: boolean
  /** The Owner's role view (D16): no inline actions. */
  readOnly: boolean
  onStartInspection: (booking: MockBooking) => void
  onStartRepair: (booking: MockBooking) => void
}

/**
 * A job that needs the technician (spec 10 T-01): reference, vehicle, plate, the customer's
 * concern and the next action, with 48px buttons for gloved hands.
 */
export function JobCard({
  booking,
  href,
  showTechnician,
  readOnly,
  onStartInspection,
  onStartRepair,
}: JobCardProps) {
  const next = cardNextStep(booking)
  const qcIssue = isQcReturned(booking) ? parseQcIssue(booking.qcNotes) : null
  const titleId = `job-${booking.id}-title`
  const inline = !readOnly && next && next.kind !== 'open'

  return (
    <article
      aria-labelledby={titleId}
      className="@container flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-xs"
    >
      <div className="flex flex-1 flex-col gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0 space-y-1">
            <p className="font-mono text-sm font-semibold text-brand-blue-ink">
              {booking.reference}
            </p>
            <h3 id={titleId} className="text-lg leading-7 font-semibold text-foreground">
              {vehicleLabel(booking)}
            </h3>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge status={booking.status} audience="staff" />
            {qcIssue ? (
              <Badge variant="destructive">
                <ShieldAlert aria-hidden="true" data-icon="inline-start" />
                QC failed
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          <PlateTag plate={booking.licensePlate} />
          <span className="inline-flex items-center gap-1.5">
            <CalendarClock className="size-4 shrink-0 text-helper" aria-hidden="true" />
            {slotLabel(booking)}
          </span>
          {showTechnician && booking.assignedTechnicianName ? (
            <span className="inline-flex items-center gap-1.5">
              <UserRound className="size-4 shrink-0 text-helper" aria-hidden="true" />
              <span>
                <span className="sr-only">Technician: </span>
                {booking.assignedTechnicianName}
              </span>
            </span>
          ) : null}
          <EstimateLine booking={booking} />
        </div>

        {qcIssue ? (
          <div className="rounded-xl border border-status-estimate-rejected-border bg-danger-subtle px-4 py-3">
            <p className="text-sm font-semibold text-danger-ink">Sent back by QC</p>
            <p className="mt-1 text-sm font-medium text-foreground">{qcIssue.title}</p>
            {qcIssue.detail ? (
              <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{qcIssue.detail}</p>
            ) : null}
          </div>
        ) : null}

        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 rounded-xl bg-layer px-4 py-3 text-sm">
          {booking.customerNotes ? (
            <>
              <dt className="text-muted-foreground">Concern</dt>
              <dd className="line-clamp-3 text-foreground">
                &ldquo;{booking.customerNotes}&rdquo;
              </dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Work</dt>
          <dd className="text-foreground">{booking.services.join(', ')}</dd>
        </dl>
      </div>

      {next ? (
        <div className="space-y-3 border-t border-border-faint bg-muted px-5 py-4 sm:px-6">
          <p className="text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">Next:</span> {next.hint}
          </p>
          <div className="flex flex-col gap-2 @sm:flex-row @sm:flex-wrap">
            {readOnly ? (
              <Button asChild size="lg" variant="outline" className="@sm:w-auto">
                <Link href={href}>View job</Link>
              </Button>
            ) : inline ? (
              <>
                <Button
                  size="lg"
                  data-job-action={booking.id}
                  onClick={() =>
                    next.kind === 'start-inspection'
                      ? onStartInspection(booking)
                      : onStartRepair(booking)
                  }
                >
                  {next.kind === 'start-inspection' ? (
                    <Play aria-hidden="true" data-icon="inline-start" />
                  ) : (
                    <Wrench aria-hidden="true" data-icon="inline-start" />
                  )}
                  {next.cta}
                </Button>
                <Button asChild size="lg" variant="outline">
                  <Link href={href}>Open job</Link>
                </Button>
              </>
            ) : (
              <Button asChild size="lg" data-job-action={booking.id}>
                <Link href={href}>
                  {next.cta}
                  <ArrowRight aria-hidden="true" data-icon="inline-end" />
                </Link>
              </Button>
            )}
          </div>
        </div>
      ) : null}
    </article>
  )
}

/**
 * A compact row for jobs that wait on someone else or are done: reference, status, vehicle,
 * plate and one line on what happens next; the whole row opens the job.
 */
export function JobRow({
  booking,
  href,
  showTechnician,
}: {
  booking: MockBooking
  href: string
  showTechnician: boolean
}) {
  const note = STATUS_NOTE[booking.status]
  return (
    <li>
      <Link
        href={href}
        className="group flex items-center gap-3 px-5 py-4 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:px-6"
      >
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <span className="font-mono text-sm font-semibold text-brand-blue-ink">
              {booking.reference}
            </span>
            <StatusBadge status={booking.status} audience="staff" />
          </div>
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <span className="text-sm font-medium text-foreground">{vehicleLabel(booking)}</span>
            <PlateTag plate={booking.licensePlate} />
          </div>
          {note || (showTechnician && booking.assignedTechnicianName) ? (
            <p className="text-sm text-muted-foreground">
              {note}
              {showTechnician && booking.assignedTechnicianName ? (
                <>
                  {note ? ' · ' : null}
                  <span className="sr-only">Technician: </span>
                  {booking.assignedTechnicianName}
                </>
              ) : null}
            </p>
          ) : null}
        </div>
        <ChevronRight
          className="size-5 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </Link>
    </li>
  )
}
