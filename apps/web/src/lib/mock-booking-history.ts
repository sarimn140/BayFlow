import { getTeamMembers, type MockBooking, type MockTeamMember } from '@/lib/mock-data'

/**
 * A mock booking's history while the screens run on mock data: the statuses it passed through to
 * reach its current one (spec 08's happy path; a rejected estimate branches off after the customer
 * saw it), each with the action that caused it, who did it and when. Notifications, the admin
 * timeline and the audit log all read it, so they agree. Replaced by `booking_events` (E-13).
 */

type Status = MockBooking['status']

export type HistoryActorRole =
  'CUSTOMER' | 'SERVICE_ADVISOR' | 'TECHNICIAN' | 'PARTS_PERSON' | 'QC_INSPECTOR'

export interface BookingHistoryStep {
  status: Status
  /** The `BookingAction` slug that led to `status`, e.g. `approve-estimate`. */
  action: string
  actorRole: HistoryActorRole
  actorName: string
  at: string
}

const HAPPY_PATH: ReadonlyArray<Status> = [
  'PENDING',
  'CONFIRMED',
  'ASSIGNED',
  'INSPECTING',
  'ESTIMATE_REVIEW',
  'AWAITING_CUSTOMER',
  'ESTIMATE_APPROVED',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
  'READY_FOR_PICKUP',
  'COMPLETED',
]

/** The action into each status and who performs it (spec 08 transition table). */
const INTO: Record<Status, { action: string; role: HistoryActorRole }> = {
  PENDING: { action: 'create', role: 'CUSTOMER' },
  CONFIRMED: { action: 'confirm', role: 'SERVICE_ADVISOR' },
  ASSIGNED: { action: 'assign-technician', role: 'SERVICE_ADVISOR' },
  INSPECTING: { action: 'start-inspection', role: 'TECHNICIAN' },
  ESTIMATE_REVIEW: { action: 'submit-estimate', role: 'TECHNICIAN' },
  AWAITING_CUSTOMER: { action: 'send-estimate', role: 'SERVICE_ADVISOR' },
  ESTIMATE_APPROVED: { action: 'approve-estimate', role: 'CUSTOMER' },
  ESTIMATE_REJECTED: { action: 'reject-estimate', role: 'CUSTOMER' },
  PARTS_PENDING: { action: 'assign-parts-person', role: 'SERVICE_ADVISOR' },
  PARTS_ORDERED: { action: 'order-parts', role: 'PARTS_PERSON' },
  PARTS_READY: { action: 'mark-parts-ready', role: 'PARTS_PERSON' },
  IN_REPAIR: { action: 'allocate-parts', role: 'PARTS_PERSON' },
  QC_PENDING: { action: 'send-to-qc', role: 'TECHNICIAN' },
  QC_IN_PROGRESS: { action: 'pick-qc', role: 'QC_INSPECTOR' },
  READY_FOR_PICKUP: { action: 'pass-qc', role: 'QC_INSPECTOR' },
  COMPLETED: { action: 'complete', role: 'SERVICE_ADVISOR' },
  CANCELLED: { action: 'cancel', role: 'SERVICE_ADVISOR' },
}

/** The statuses a booking passed through, in order (empty for one with an unknown history). */
export function passedStatuses(status: Status): ReadonlyArray<Status> {
  if (status === 'ESTIMATE_REJECTED') {
    return [...HAPPY_PATH.slice(0, HAPPY_PATH.indexOf('AWAITING_CUSTOMER') + 1), status]
  }
  if (status === 'CANCELLED') return ['PENDING', 'CANCELLED']
  const index = HAPPY_PATH.indexOf(status)
  return index < 0 ? [] : HAPPY_PATH.slice(0, index + 1)
}

const ROLE_LABEL: Record<Exclude<HistoryActorRole, 'CUSTOMER'>, string> = {
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
}

/**
 * Who acted in a staff role: the booking's assignee when it names one, else a member of the
 * booking's own shop with that role (an Owner acts for a shop without Service Advisors, D26).
 * Never someone from another shop.
 */
function staffName(
  b: MockBooking,
  role: Exclude<HistoryActorRole, 'CUSTOMER'>,
  memberId: string | undefined,
): string {
  const team = getTeamMembers(b.shopId)
  const byRole = (r: MockTeamMember['role']) => team.find((m) => m.role === r)
  const member =
    (memberId ? team.find((m) => m.id === memberId) : undefined) ??
    byRole(role) ??
    (role === 'SERVICE_ADVISOR' ? byRole('OWNER') : undefined)
  return member?.name ?? ROLE_LABEL[role]
}

function actorName(b: MockBooking, role: HistoryActorRole): string {
  switch (role) {
    case 'CUSTOMER':
      return b.customerName
    case 'SERVICE_ADVISOR':
      return staffName(b, role, undefined)
    case 'TECHNICIAN':
      return b.assignedTechnicianName ?? staffName(b, role, b.assignedTechnicianId)
    case 'PARTS_PERSON':
      return staffName(b, role, b.assignedPartsPersonId)
    case 'QC_INSPECTOR':
      return staffName(b, role, b.qcInspectorId)
  }
}

const historyByBooking = new WeakMap<MockBooking, BookingHistoryStep[]>()

/** The booking's steps, oldest first, spread between `createdAt` and `updatedAt`. Memoised. */
export function bookingHistory(b: MockBooking): BookingHistoryStep[] {
  const cached = historyByBooking.get(b)
  if (cached) return cached
  const statuses = passedStatuses(b.status)
  const start = Date.parse(b.createdAt)
  const span = Math.max(0, Date.parse(b.updatedAt) - start)
  const steps = statuses.map((status, index) => {
    const { action, role } = INTO[status]
    return {
      status,
      action,
      actorRole: role,
      actorName: actorName(b, role),
      // The first step is the creation itself; the last lands on `updatedAt`.
      at: new Date(
        statuses.length === 1 ? start : start + (span * index) / (statuses.length - 1),
      ).toISOString(),
    }
  })
  historyByBooking.set(b, steps)
  return steps
}
