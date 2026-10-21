import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { formatDateKey } from '@/lib/booking-slots'
import type { MockBooking } from '@/lib/mock-data'
import { statusLabel, type BookingStatus } from '@/lib/status'
import { cn } from '@/lib/utils'

import { plural, vehicleLabel, type JobStage, type PartsSummary } from './parts-data'
import { CardHeading } from './parts-states'

export interface NextStep {
  /** "Next step", or "Status" when the parts person has nothing to do. */
  eyebrow: string
  title: string
  body: string
}

/** What the job needs from the parts person now (spec 10 PP-02 actions, spec 08 T13–T16). */
export function nextStepFor(
  stage: JobStage,
  summary: PartsSummary,
  technician: string,
  status: BookingStatus,
): NextStep {
  const shortParts = plural(summary.short.length, 'part')
  const oneShort = summary.short.length === 1
  const onePart = summary.requiredCount === 1
  switch (stage) {
    case 'check':
      if (!summary.allAvailable) {
        return {
          eyebrow: 'Next step',
          title: 'Order the missing parts',
          body: `${shortParts} ${oneShort ? 'is' : 'are'} short. Order ${oneShort ? 'it' : 'them'} from a supplier; the job waits in Parts ordered until the delivery arrives.`,
        }
      }
      return {
        eyebrow: 'Next step',
        title: 'Mark the parts ready',
        body:
          summary.requiredCount === 0
            ? 'There are no parts on the estimate. Mark parts ready, then allocate to release the job to repair.'
            : `${onePart ? 'The part is' : `All ${summary.requiredCount} parts are`} in stock. Mark ${onePart ? 'it' : 'them'} ready to set ${onePart ? 'it' : 'them'} aside for this job.`,
      }
    case 'ordered':
      if (!summary.allAvailable) {
        return {
          eyebrow: 'Next step',
          title: 'Receive the delivery',
          body: `Waiting for ${shortParts} from the supplier. When the delivery arrives, receive it on its purchase order, then mark the parts ready.`,
        }
      }
      return {
        eyebrow: 'Next step',
        title: 'Mark the parts ready',
        body: 'Stock now covers every part. Mark the parts ready to set them aside for this job.',
      }
    case 'ready':
      return {
        eyebrow: 'Next step',
        title: 'Allocate the parts',
        body:
          summary.requiredCount === 0
            ? `No parts to hand over. Allocate to release the job to ${technician} for repair.`
            : `The parts are ready. Hand them to ${technician} so the repair can start.`,
      }
    case 'allocated':
      return {
        eyebrow: 'Status',
        title: 'Parts handed over',
        // Starts the sentence, so "the technician" (no name yet) needs its capital.
        body: `${technician.charAt(0).toUpperCase()}${technician.slice(1)} has the parts. This job is now ${statusLabel(status, 'staff')} and has left the parts queue.`,
      }
    case 'cancelled':
      return {
        eyebrow: 'Status',
        title: 'Booking cancelled',
        body: 'There is nothing to prepare for this job.',
      }
    default:
      return {
        eyebrow: 'Status',
        title: 'Not ready for parts yet',
        body: 'The job reaches the parts queue once the customer approves the estimate and a service advisor assigns it.',
      }
  }
}

export interface NextStepCardProps {
  step: NextStep
  /** The view's one primary button. Below `md` it lives in the page's sticky action bar instead. */
  primary?: ReactNode
  /** An outline alternative, shown here at every width. */
  secondary?: ReactNode
}

/** The status and next action, first on phones (DESIGN.md §6.5); the buttons come from the page. */
export function NextStepCard({ step, primary, secondary }: NextStepCardProps) {
  return (
    <Card>
      <CardHeader>
        <p className="text-sm font-semibold text-brand-blue-ink">{step.eyebrow}</p>
        <CardHeading>{step.title}</CardHeading>
        <CardDescription className="text-base">{step.body}</CardDescription>
      </CardHeader>
      {primary || secondary ? (
        // Column flex items stretch, so each button spans the card.
        <CardContent className={cn('gap-2', !secondary && 'hidden md:flex')}>
          {primary ? <div className="hidden flex-col md:flex">{primary}</div> : null}
          {secondary ? <div className="flex flex-col">{secondary}</div> : null}
        </CardContent>
      ) : null}
    </Card>
  )
}

function slotLabel(booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>): string {
  let day = booking.scheduledDate
  try {
    day = formatDateKey(booking.scheduledDate)
  } catch {
    // Keep the stored value when it isn't a date.
  }
  return [day, booking.scheduledTime].filter(Boolean).join(' · ')
}

/** The job at a glance: vehicle, plate, technician, slot and the booked services. */
export function JobCard({ booking, className }: { booking: MockBooking; className?: string }) {
  const rows: { label: string; value: ReactNode }[] = [
    { label: 'Vehicle', value: vehicleLabel(booking) },
    { label: 'Plate', value: <span className="font-mono">{booking.licensePlate}</span> },
    { label: 'Technician', value: booking.assignedTechnicianName || 'Not assigned yet' },
    { label: 'Booked for', value: slotLabel(booking) },
  ]
  if (booking.services.length > 0) {
    rows.push({
      label: booking.services.length === 1 ? 'Service' : 'Services',
      value: (
        <ul className="space-y-1">
          {booking.services.map((service) => (
            <li key={service}>{service}</li>
          ))}
        </ul>
      ),
    })
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardHeading>Job details</CardHeading>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border-faint text-sm">
          {rows.map((row) => (
            <div key={row.label} className="flex items-start justify-between gap-4 py-2.5">
              <dt className="shrink-0 text-muted-foreground">{row.label}</dt>
              <dd className="min-w-0 text-right font-medium text-foreground">{row.value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
