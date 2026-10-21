import { formatDate, formatPKR, formatTime } from '@/lib/format'
import type { MockBooking } from '@/lib/mock-data'

import type { SaCancellation } from './sa-records'

/**
 * The words on SA-02's "Next step" card: whose turn it is and what happens next, for every status
 * (spec 10 SA-02, brief §5.1 step owners). Buttons come from `allowed_actions`, never from here.
 */

export interface NextStep {
  /** `act`: the SA has a forward action; `wait`: someone else has the job; `done`: closed. */
  kind: 'act' | 'wait' | 'done'
  /** "Next step", "Waiting on Imran" or "Closed". */
  label: string
  title: string
  description: string
}

export interface NextStepContext {
  technician?: string
  partsPerson?: string
  qcInspector?: string
  estimateVersion: number
  saDraftOpen: boolean
  readyNotified: boolean
  cancellation?: SaCancellation
  timeZone: string
}

/**
 * The booked slot in the same style as every other date on the page: "Fri, 9 Oct 2026 · 11:00 am"
 * (or "… at 11:00 am" in a sentence). The slot is a shop-local day, so it is formatted as a UTC
 * noon to keep the day; the raw values are shown if the date key can't be read.
 */
export function slotText(
  booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>,
  joiner: ' · ' | ' at ' = ' · ',
): string {
  const time = booking.scheduledTime.replace(/^0(\d)/, '$1')
  try {
    return `${formatDate(`${booking.scheduledDate}T12:00:00Z`, 'UTC')}${joiner}${time}`
  } catch {
    return `${booking.scheduledDate}${joiner}${time}`
  }
}

/** A timestamp in shop time ("Fri, 9 Oct 2026 · 10:00 am"), or the raw value if unreadable. */
export function dateTimeText(value: string, timeZone: string, joiner: ' · ' | ' at ' = ' · ') {
  try {
    return `${formatDate(value, timeZone)}${joiner}${formatTime(value, timeZone)}`
  } catch {
    return value
  }
}

function servicesText(services: ReadonlyArray<string>): string {
  if (services.length === 0) return 'a visit'
  if (services.length === 1) return services[0] ?? 'a visit'
  if (services.length === 2) return `${services[0]} and ${services[1]}`
  return `${services.length} services`
}

export function describeNextStep(booking: MockBooking, context: NextStepContext): NextStep {
  const customer = booking.customerName
  const vehicle = `${booking.vehicleMake} ${booking.vehicleModel}`
  const tech = context.technician
  const parts = context.partsPerson
  const total = formatPKR(booking.estimateTotal)
  const version = `v${context.estimateVersion}`
  const partLines = booking.estimateItems.filter((item) => item.type === 'PART').length

  switch (booking.status) {
    case 'PENDING':
      return {
        kind: 'act',
        label: 'Next step',
        title: 'Confirm the booking',
        description: `${customer} asked for ${servicesText(booking.services)} on ${slotText(booking, ' at ')}. Confirm it to put it on the schedule, or decline it with a reason.`,
      }
    case 'CONFIRMED':
      return {
        kind: 'act',
        label: 'Next step',
        title: 'Assign a technician',
        description: `Choose who inspects the ${vehicle}. The job shows up in their queue straight away.`,
      }
    case 'ASSIGNED':
      return {
        kind: 'wait',
        label: `Waiting on ${tech ?? 'the technician'}`,
        title: 'Inspection not started',
        description: `${tech ?? 'The technician'} has the job in their queue. The estimate comes to you for review once it's submitted.`,
      }
    case 'INSPECTING':
      return {
        kind: 'wait',
        label: `Waiting on ${tech ?? 'the technician'}`,
        title: 'Inspection in progress',
        description: `${tech ?? 'The technician'} is inspecting the car and writing the estimate. It comes to you for review next.`,
      }
    case 'ESTIMATE_REVIEW':
      return {
        kind: 'act',
        label: 'Next step',
        title: 'Review and send the estimate',
        description:
          booking.estimateItems.length === 0
            ? `The estimate has no lines yet. Add parts and labour, then send it to ${customer}.`
            : context.saDraftOpen
              ? `Your draft ${version} comes to ${total}. Send it to ${customer} when it's ready.`
              : `${tech ?? 'The technician'} submitted ${version} for ${total}. Check the lines, edit them if needed, then send it to ${customer}.`,
      }
    case 'AWAITING_CUSTOMER':
      return {
        kind: 'wait',
        label: `Waiting on ${customer}`,
        title: 'Estimate sent for approval',
        description: `${customer} can approve or decline ${version} (${total}) from their bookings. You'll be notified when they decide.`,
      }
    case 'ESTIMATE_APPROVED':
      return {
        kind: 'act',
        label: 'Next step',
        title: 'Assign a parts person',
        description:
          partLines > 0
            ? `${customer} approved ${total}. The parts person checks stock for the ${partLines === 1 ? 'part' : `${partLines} parts`} and orders anything missing.`
            : `${customer} approved ${total}. There are no parts on this estimate, so the parts person can release it straight to repair.`,
      }
    case 'ESTIMATE_REJECTED':
      return {
        kind: 'act',
        label: 'Next step',
        title: 'Estimate declined',
        description: `${customer} declined ${version}. Revise it yourself, or return it to ${tech ?? 'the technician'} to re-inspect. If they no longer want the work, cancel the booking.`,
      }
    case 'PARTS_PENDING':
      return {
        kind: 'wait',
        label: `Waiting on ${parts ?? 'the parts person'}`,
        title: 'Checking parts',
        description: `${parts ?? 'The parts person'} is checking stock for this job and will order anything that's missing.`,
      }
    case 'PARTS_ORDERED':
      return {
        kind: 'wait',
        label: 'Waiting on parts',
        title: 'Parts on order',
        description: `${parts ?? 'The parts person'} ordered the missing parts. The job moves on as soon as they arrive.`,
      }
    case 'PARTS_READY':
      return {
        kind: 'wait',
        label: `Waiting on ${parts ?? 'the parts person'}`,
        title: 'Parts ready',
        description: `Every part is reserved. ${parts ?? 'The parts person'} hands them to ${tech ?? 'the technician'} to start the repair.`,
      }
    case 'IN_REPAIR':
      return {
        kind: 'wait',
        label: `Waiting on ${tech ?? 'the technician'}`,
        title: 'Repair in progress',
        description: `${tech ?? 'The technician'} is repairing the car. Quality check is next; the booking can no longer be cancelled.`,
      }
    case 'QC_PENDING':
      return {
        kind: 'wait',
        label: 'Waiting on QC',
        title: 'Waiting for quality check',
        description: 'The next free QC inspector picks the job up and checks the repair.',
      }
    case 'QC_IN_PROGRESS':
      return {
        kind: 'wait',
        label: `Waiting on ${context.qcInspector ?? 'QC'}`,
        title: 'Quality check in progress',
        description: `${context.qcInspector ?? 'A QC inspector'} is checking the repair. If it passes, the car is ready for pick-up and comes back to you.`,
      }
    case 'READY_FOR_PICKUP':
      return context.readyNotified
        ? {
            kind: 'act',
            label: 'Next step',
            title: 'Complete the booking',
            description: `${customer} has been told the car is ready. Complete the booking when they collect it.`,
          }
        : {
            kind: 'act',
            label: 'Next step',
            title: 'Tell the customer',
            description: `The repair passed quality check. Let ${customer} know the car is ready, then complete the booking when they collect it.`,
          }
    case 'COMPLETED':
      return {
        kind: 'done',
        label: 'Closed',
        title: 'Booking completed',
        description: `${customer} collected the ${vehicle}. Nothing else to do.`,
      }
    case 'CANCELLED': {
      const record = context.cancellation
      if (!record) {
        return {
          kind: 'done',
          label: 'Closed',
          title: 'Booking cancelled',
          description: 'This booking was cancelled. Nothing else to do.',
        }
      }
      const verb = record.kind === 'decline' ? 'declined' : 'cancelled'
      return {
        kind: 'done',
        label: 'Closed',
        title: record.kind === 'decline' ? 'Booking declined' : 'Booking cancelled',
        description: `${record.by} ${verb} it on ${dateTimeText(record.at, context.timeZone, ' at ')}.`,
      }
    }
  }
}
