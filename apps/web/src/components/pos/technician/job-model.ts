import {
  Ban,
  CarFront,
  CircleCheckBig,
  ClipboardCheck,
  ClipboardList,
  FileCheck,
  FileText,
  FileX,
  Hourglass,
  ListChecks,
  PackageSearch,
  ScanSearch,
  ShieldAlert,
  Truck,
  UserCheck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import type { SaActivity } from '@/components/pos/sa-booking/sa-records'
import { formatDateKey } from '@/lib/booking-slots'
import {
  normaliseEmail,
  type MockBooking,
  type MockEstimateItem,
  type MockTeamMember,
} from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/**
 * Technician screens (spec 10 T-01, T-02) on mock data: how a booking's status maps to the job
 * list's groups, the technician's next action and the copy that explains it. Display logic only;
 * the status changes themselves stay in the pages.
 */

/** T-01 groups, in the order the list shows them: the work that needs the technician first. */
export const JOB_GROUPS = [
  'qc-returned',
  'to-inspect',
  'inspecting',
  'repair',
  'waiting',
  'done',
] as const
export type JobGroup = (typeof JOB_GROUPS)[number]

/** Groups whose jobs need the technician now (the others are informational). */
export const ACTION_GROUPS: ReadonlyArray<JobGroup> = [
  'qc-returned',
  'to-inspect',
  'inspecting',
  'repair',
]

/** Icon-tile tones (phase tokens for the phase groups, DESIGN.md §2.2). */
export type JobTone = 'brand' | 'danger' | 'neutral' | 'success' | 'inspection' | 'repair'

export const JOB_GROUP_META: Record<
  JobGroup,
  { title: string; description: string; icon: LucideIcon; tone: JobTone }
> = {
  'qc-returned': {
    title: 'QC sent back',
    description: 'QC found something to fix. Fix it, then send the car back to QC.',
    icon: ShieldAlert,
    tone: 'danger',
  },
  'to-inspect': {
    title: 'To inspect',
    description: 'Assigned and waiting for the inspection to start.',
    icon: ScanSearch,
    tone: 'inspection',
  },
  inspecting: {
    title: 'Inspecting',
    description: 'Write the inspection notes and build the estimate, then submit it.',
    icon: FileText,
    tone: 'inspection',
  },
  repair: {
    title: 'Repair',
    description: 'Start when the parts are ready, then send the car to QC.',
    icon: Wrench,
    tone: 'repair',
  },
  waiting: {
    title: 'Waiting on others',
    description: 'With the service advisor, the customer, parts or QC. Nothing to do yet.',
    icon: Hourglass,
    tone: 'neutral',
  },
  done: {
    title: 'Done',
    description: 'Passed QC or collected by the customer.',
    icon: CircleCheckBig,
    tone: 'success',
  },
}

/**
 * D21: the signed-in technician's own active membership of the shop, found by e-mail in the
 * shop's team (a booking's `assignedTechnicianId` is that member's id). Undefined for anyone else.
 */
export function ownTechnicianMember(
  team: ReadonlyArray<MockTeamMember>,
  email: string,
): MockTeamMember | undefined {
  const me = normaliseEmail(email)
  if (me === '') return undefined
  return team.find(
    (member) =>
      member.role === 'TECHNICIAN' && member.is_active && normaliseEmail(member.email) === me,
  )
}

/** D21: a technician sees only the jobs assigned to them (`technician_user_id` = me). */
export function isOwnJob(
  booking: Pick<MockBooking, 'assignedTechnicianId'>,
  member: MockTeamMember | undefined,
): boolean {
  return member !== undefined && booking.assignedTechnicianId === member.id
}

/**
 * T11: the service advisor's latest return of a declined estimate to the technician, while the
 * job is back in inspection because of it; undefined otherwise (the note is history once the
 * technician submits again).
 */
export function currentReturn(
  status: BookingStatus,
  activity: ReadonlyArray<SaActivity>,
): SaActivity | undefined {
  if (status !== 'INSPECTING') return undefined
  return activity.findLast((entry) => entry.kind === 'returned-to-technician')
}

/** QC failed the job and sent it back for rework (mock: `qcPassed === false` while in repair). */
export function isQcReturned(booking: Pick<MockBooking, 'status' | 'qcPassed'>): boolean {
  return booking.status === 'IN_REPAIR' && booking.qcPassed === false
}

/** The T-01 group of a booking; `null` when it is not (or not yet) a technician's job. */
export function jobGroup(booking: Pick<MockBooking, 'status' | 'qcPassed'>): JobGroup | null {
  switch (booking.status) {
    case 'ASSIGNED':
      return 'to-inspect'
    case 'INSPECTING':
      return 'inspecting'
    case 'PARTS_READY':
      return 'repair'
    case 'IN_REPAIR':
      return isQcReturned(booking) ? 'qc-returned' : 'repair'
    case 'ESTIMATE_REVIEW':
    case 'AWAITING_CUSTOMER':
    case 'ESTIMATE_APPROVED':
    case 'ESTIMATE_REJECTED':
    case 'PARTS_PENDING':
    case 'PARTS_ORDERED':
    case 'QC_PENDING':
    case 'QC_IN_PROGRESS':
      return 'waiting'
    case 'READY_FOR_PICKUP':
    case 'COMPLETED':
      return 'done'
    default:
      return null
  }
}

/** Minutes after midnight of a mock slot time such as "02:00 pm" (0 when unreadable). */
function slotMinutes(time: string): number {
  const match = /^(\d{1,2}):(\d{2})\s*(am|pm)$/i.exec(time.trim())
  if (!match) return 0
  const hours = Number(match[1]) % 12
  const pm = match[3]!.toLowerCase() === 'pm'
  return (hours + (pm ? 12 : 0)) * 60 + Number(match[2])
}

function bySlot(a: MockBooking, b: MockBooking): number {
  return (
    a.scheduledDate.localeCompare(b.scheduledDate) ||
    slotMinutes(a.scheduledTime) - slotMinutes(b.scheduledTime)
  )
}

/** Bookings per group: earliest slot first, finished jobs newest first. */
export function groupJobs(bookings: ReadonlyArray<MockBooking>): Record<JobGroup, MockBooking[]> {
  const groups = Object.fromEntries(JOB_GROUPS.map((group) => [group, []])) as unknown as Record<
    JobGroup,
    MockBooking[]
  >
  for (const booking of bookings) {
    const group = jobGroup(booking)
    if (group) groups[group].push(booking)
  }
  for (const group of JOB_GROUPS) {
    groups[group].sort(group === 'done' ? (a, b) => b.updatedAt.localeCompare(a.updatedAt) : bySlot)
  }
  return groups
}

/** The technician action a status offers (the mock's stand-in for `allowed_actions`, D48). */
export type JobAction = 'start-inspection' | 'submit-estimate' | 'start-repair' | 'send-to-qc'

export function technicianAction(status: BookingStatus): JobAction | null {
  switch (status) {
    case 'ASSIGNED':
      return 'start-inspection'
    case 'INSPECTING':
      return 'submit-estimate'
    case 'PARTS_READY':
      return 'start-repair'
    case 'IN_REPAIR':
      return 'send-to-qc'
    default:
      return null
  }
}

/** What a job card offers next: an inline action (no input needed, spec 10 T-01) or opening it. */
export interface CardNextStep {
  hint: string
  cta: string
  kind: 'start-inspection' | 'start-repair' | 'open'
}

export function cardNextStep(booking: MockBooking): CardNextStep | null {
  if (isQcReturned(booking)) {
    return {
      hint: 'fix what QC found and send the car back to QC.',
      cta: 'Fix QC issue',
      kind: 'open',
    }
  }
  switch (booking.status) {
    case 'ASSIGNED':
      return {
        hint: 'start the inspection when the car is on the bay.',
        cta: 'Start inspection',
        kind: 'start-inspection',
      }
    case 'INSPECTING':
      return {
        hint: 'finish the notes and the estimate, then submit it.',
        cta: 'Continue inspection',
        kind: 'open',
      }
    case 'PARTS_READY':
      return {
        hint: 'the parts are ready, so the repair can start.',
        cta: 'Start repair',
        kind: 'start-repair',
      }
    case 'IN_REPAIR':
      return {
        hint: 'finish the repair and send the car to QC.',
        cta: 'Continue repair',
        kind: 'open',
      }
    default:
      return null
  }
}

/** One line on who or what a job is waiting for (T-01 "Waiting on others", "Done"). */
export const STATUS_NOTE: Partial<Record<BookingStatus, string>> = {
  ESTIMATE_REVIEW: 'The service advisor is reviewing the estimate',
  AWAITING_CUSTOMER: 'Waiting for the customer to approve the estimate',
  ESTIMATE_APPROVED: 'Approved. The service advisor is arranging the parts',
  ESTIMATE_REJECTED: 'The customer declined. The service advisor will follow up',
  PARTS_PENDING: 'Waiting for parts',
  PARTS_ORDERED: 'Parts are on order',
  QC_PENDING: 'Waiting for a QC inspector',
  QC_IN_PROGRESS: 'A QC inspector is checking the car',
  READY_FOR_PICKUP: 'Passed QC, waiting for the customer to collect it',
  COMPLETED: 'Collected by the customer',
}

/** T-02 "Next step" card: where the job stands and what the technician does about it. */
export interface NextStep {
  /** Small line above the title. */
  eyebrow: string
  title: string
  body: string
  icon: LucideIcon
  tone: JobTone
}

const WAITING = 'Waiting'

export function nextStep(booking: Pick<MockBooking, 'status' | 'qcPassed'>): NextStep {
  if (isQcReturned(booking)) {
    return {
      eyebrow: 'Rework',
      title: 'Fix what QC found',
      body: 'QC sent the car back. Fix the issue, then send it back to QC.',
      icon: ShieldAlert,
      tone: 'danger',
    }
  }
  switch (booking.status) {
    case 'PENDING':
    case 'CONFIRMED':
      return {
        eyebrow: WAITING,
        title: 'Not assigned yet',
        body: 'The service advisor hasn’t assigned this booking to a technician yet.',
        icon: UserCheck,
        tone: 'neutral',
      }
    case 'ASSIGNED':
      return {
        eyebrow: 'Next step',
        title: 'Start the inspection',
        body: 'When the car is on the bay, start the inspection. Then write your notes and build the estimate.',
        icon: ScanSearch,
        tone: 'brand',
      }
    case 'INSPECTING':
      return {
        eyebrow: 'Next step',
        title: 'Build and submit the estimate',
        body: 'Add the parts and labour the job needs and note what you found. Submit the estimate when it is complete.',
        icon: FileText,
        tone: 'brand',
      }
    case 'ESTIMATE_REVIEW':
      return {
        eyebrow: WAITING,
        title: 'With the service advisor',
        body: 'The service advisor is reviewing the estimate before it goes to the customer. Nothing to do for now.',
        icon: ClipboardList,
        tone: 'neutral',
      }
    case 'AWAITING_CUSTOMER':
      return {
        eyebrow: WAITING,
        title: 'Waiting for the customer',
        body: 'The customer is reviewing the estimate. The repair can start once it is approved and the parts are ready.',
        icon: Hourglass,
        tone: 'neutral',
      }
    case 'ESTIMATE_APPROVED':
      return {
        eyebrow: WAITING,
        title: 'Estimate approved',
        body: 'The customer approved the estimate. The service advisor is arranging the parts.',
        icon: FileCheck,
        tone: 'neutral',
      }
    case 'ESTIMATE_REJECTED':
      return {
        eyebrow: WAITING,
        title: 'Estimate declined',
        body: 'The customer declined the estimate. The service advisor will follow up with them.',
        icon: FileX,
        tone: 'neutral',
      }
    case 'PARTS_PENDING':
      return {
        eyebrow: WAITING,
        title: 'Waiting for parts',
        body: 'The parts person is checking stock for this job. The repair can start once the parts are ready.',
        icon: PackageSearch,
        tone: 'neutral',
      }
    case 'PARTS_ORDERED':
      return {
        eyebrow: WAITING,
        title: 'Parts on order',
        body: 'Some parts are on order. The repair can start once they arrive.',
        icon: Truck,
        tone: 'neutral',
      }
    case 'PARTS_READY':
      return {
        eyebrow: 'Next step',
        title: 'Start the repair',
        body: 'The parts are ready. Start the repair when you begin work on the car.',
        icon: Wrench,
        tone: 'brand',
      }
    case 'IN_REPAIR':
      return {
        eyebrow: 'Next step',
        title: 'Finish the repair',
        body: 'When the work is done, send the car to QC for the quality check.',
        icon: Wrench,
        tone: 'brand',
      }
    case 'QC_PENDING':
      return {
        eyebrow: WAITING,
        title: 'Waiting for QC',
        body: 'A QC inspector checks the car next. Nothing to do for now.',
        icon: ListChecks,
        tone: 'neutral',
      }
    case 'QC_IN_PROGRESS':
      return {
        eyebrow: WAITING,
        title: 'QC in progress',
        body: 'A QC inspector is checking the car now.',
        icon: ClipboardCheck,
        tone: 'neutral',
      }
    case 'READY_FOR_PICKUP':
      return {
        eyebrow: 'Done',
        title: 'Passed QC',
        body: 'The car passed the quality check and is ready for the customer to collect.',
        icon: CarFront,
        tone: 'success',
      }
    case 'COMPLETED':
      return {
        eyebrow: 'Done',
        title: 'Job complete',
        body: 'The customer has collected the car.',
        icon: CircleCheckBig,
        tone: 'success',
      }
    case 'CANCELLED':
      return {
        eyebrow: 'Closed',
        title: 'Booking cancelled',
        body: 'This booking was cancelled. There is nothing to do.',
        icon: Ban,
        tone: 'neutral',
      }
  }
}

/**
 * One line under the estimate's title on T-02. `lineCount`: the lines it shows; `readOnly`: the
 * Owner's role view, which watches the technician rather than acting.
 */
export function estimateNote(
  booking: Pick<MockBooking, 'status' | 'estimateApproved'>,
  lineCount: number,
  readOnly = false,
): string {
  switch (booking.status) {
    case 'PENDING':
    case 'CONFIRMED':
      return 'No estimate yet.'
    case 'ASSIGNED':
      return readOnly
        ? 'The technician builds it during the inspection.'
        : 'Start the inspection to build the estimate.'
    case 'INSPECTING':
      return readOnly
        ? 'The technician is building this estimate.'
        : 'Add the parts and labour this job needs. Each line is saved as you add it.'
  }
  if (lineCount === 0) return 'No estimate lines.'
  switch (booking.status) {
    case 'ESTIMATE_REVIEW':
      return 'Submitted. The service advisor is reviewing it.'
    case 'AWAITING_CUSTOMER':
      return 'Sent to the customer for approval.'
    case 'ESTIMATE_REJECTED':
      return 'The customer declined this estimate.'
    case 'CANCELLED':
      return 'The booking was cancelled.'
    default:
      return booking.estimateApproved ? 'Approved by the customer.' : 'The estimate for this job.'
  }
}

/** The QC issue in the mock's `qcNotes` ("QC Issue: {title} — {description}"). */
export function parseQcIssue(notes: string | undefined): { title: string; detail?: string } | null {
  const text = notes?.replace(/^QC Issue:\s*/i, '').trim()
  if (!text) return null
  const [title = '', ...rest] = text.split(' — ')
  const detail = rest.join(' — ').trim()
  return { title: title.trim(), ...(detail ? { detail } : {}) }
}

export interface EstimateTotals {
  parts: number
  labour: number
  total: number
  partLines: number
  labourLines: number
}

/** Parts and labour subtotals; `total` is the sum of the line totals, as the pages save it. */
export function estimateTotals(items: ReadonlyArray<MockEstimateItem>): EstimateTotals {
  const totals: EstimateTotals = { parts: 0, labour: 0, total: 0, partLines: 0, labourLines: 0 }
  for (const item of items) {
    if (item.type === 'PART') {
      totals.parts += item.total
      totals.partLines += 1
    } else {
      totals.labour += item.total
      totals.labourLines += 1
    }
    totals.total += item.total
  }
  return totals
}

/** "2022 Honda Civic Oriel". */
export function vehicleLabel(
  booking: Pick<MockBooking, 'vehicleYear' | 'vehicleMake' | 'vehicleModel'>,
): string {
  return `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
}

function slotDay(date: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? formatDateKey(date) : date
}

/** "Thu 9 Oct · 10:00 am" (the raw date when it isn't a YYYY-MM-DD key). */
export function slotLabel(booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>): string {
  return `${slotDay(booking.scheduledDate)} · ${booking.scheduledTime}`
}

/** "Thu 9 Oct at 10:00 am", for sentences. */
export function slotSentence(
  booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>,
): string {
  return `${slotDay(booking.scheduledDate)} at ${booking.scheduledTime}`
}

/** `[name="value"]`, with quotes and backslashes in the value escaped. */
export function attributeSelector(name: string, value: string): string {
  return `[${name}="${value.replace(/["\\]/g, '\\$&')}"]`
}

/** "1 line" / "3 lines". */
export function countLabel(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}
