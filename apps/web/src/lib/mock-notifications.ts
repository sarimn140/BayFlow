import { formatPKR } from '@/lib/format'
import { bookingHistory, passedStatuses } from '@/lib/mock-booking-history'
import {
  getStoredData,
  INITIAL_BOOKINGS,
  isBookingCustomer,
  normaliseEmail,
  setStoredData,
  type CurrentUserSession,
  type MockBooking,
  type MockTeamMember,
} from '@/lib/mock-data'

/**
 * In-app notifications (X-01) while the screens run on mock data. Each status a booking has passed
 * through stands in for the transition that fired it (glossary §6), the recipients follow the glossary
 * (D26: "SAs of the shop" falls back to the Owner when the shop has no Service Advisor), and each
 * notification links to the recipient's own screen (D67). Replaced by E-17…E-20.
 */

export type NotificationType =
  | 'BOOKING_CREATED'
  | 'BOOKING_CONFIRMED'
  | 'TECHNICIAN_ASSIGNED'
  | 'ESTIMATE_SUBMITTED'
  | 'ESTIMATE_SENT'
  | 'ESTIMATE_APPROVED'
  | 'ESTIMATE_REJECTED'
  | 'PARTS_NEEDED'
  | 'PARTS_READY'
  | 'QC_REQUESTED'
  | 'QC_FAILED'
  | 'QC_PASSED'
  | 'VEHICLE_READY'

export interface MockNotification {
  id: string
  type: NotificationType
  title: string
  body: string
  reference: string
  shopName: string
  /** Server-computed in the API (D67); here, the recipient's screen for the booking. */
  link: string
  createdAt: string
}

type Audience = 'SA' | 'TECHNICIAN' | 'PARTS' | 'QC' | 'CUSTOMER'

const vehicle = (b: MockBooking) => `${b.vehicleYear} ${b.vehicleMake} ${b.vehicleModel}`

/** What each status announces, to whom (glossary §6). */
const BY_STATUS: Partial<
  Record<
    MockBooking['status'],
    ReadonlyArray<{
      type: NotificationType
      to: Audience
      title: string
      body: (b: MockBooking) => string
    }>
  >
> = {
  PENDING: [
    {
      type: 'BOOKING_CREATED',
      to: 'SA',
      title: 'New booking request',
      body: (b) =>
        `${b.customerName} booked ${b.services.join(', ')} for ${b.scheduledDate} at ${b.scheduledTime}.`,
    },
  ],
  CONFIRMED: [
    {
      type: 'BOOKING_CONFIRMED',
      to: 'CUSTOMER',
      title: 'Booking confirmed',
      body: (b) =>
        `${b.shopName} confirmed your booking for ${b.scheduledDate} at ${b.scheduledTime}.`,
    },
  ],
  ASSIGNED: [
    {
      type: 'TECHNICIAN_ASSIGNED',
      to: 'TECHNICIAN',
      title: 'New job assigned to you',
      body: (b) => `${vehicle(b)} (${b.licensePlate}): ${b.services.join(', ')}.`,
    },
  ],
  ESTIMATE_REVIEW: [
    {
      type: 'ESTIMATE_SUBMITTED',
      to: 'SA',
      title: 'Estimate ready for review',
      body: (b) =>
        `${b.assignedTechnicianName ?? 'The technician'} submitted ${formatPKR(b.estimateTotal)} for ${b.licensePlate}.`,
    },
  ],
  AWAITING_CUSTOMER: [
    {
      type: 'ESTIMATE_SENT',
      to: 'CUSTOMER',
      title: 'Your estimate is ready',
      body: (b) =>
        `Review and approve ${formatPKR(b.estimateTotal)} for your ${b.vehicleMake} ${b.vehicleModel}.`,
    },
  ],
  ESTIMATE_APPROVED: [
    {
      type: 'ESTIMATE_APPROVED',
      to: 'SA',
      title: 'Estimate approved',
      body: (b) =>
        `${b.customerName} approved ${formatPKR(b.estimateTotal)} for ${b.licensePlate}.`,
    },
  ],
  ESTIMATE_REJECTED: [
    {
      type: 'ESTIMATE_REJECTED',
      to: 'SA',
      title: 'Estimate declined',
      body: (b) => `${b.customerName} declined the estimate for ${b.licensePlate}.`,
    },
  ],
  PARTS_PENDING: [
    {
      type: 'PARTS_NEEDED',
      to: 'PARTS',
      title: 'Parts needed',
      body: (b) =>
        `${b.licensePlate} (${b.vehicleMake} ${b.vehicleModel}) needs parts checked against stock.`,
    },
  ],
  PARTS_READY: [
    {
      type: 'PARTS_READY',
      to: 'TECHNICIAN',
      title: 'Parts ready',
      body: (b) => `Parts for ${b.licensePlate} are ready. You can start the repair.`,
    },
  ],
  QC_PENDING: [
    {
      type: 'QC_REQUESTED',
      to: 'QC',
      title: 'Ready for quality check',
      body: (b) =>
        `${vehicle(b)} (${b.licensePlate}) was repaired by ${b.assignedTechnicianName ?? 'the technician'}.`,
    },
  ],
  READY_FOR_PICKUP: [
    {
      type: 'QC_PASSED',
      to: 'SA',
      title: 'QC passed',
      body: (b) => `${b.licensePlate} passed QC. Let ${b.customerName} know it is ready.`,
    },
    {
      type: 'VEHICLE_READY',
      to: 'CUSTOMER',
      title: 'Your car is ready',
      body: (b) => `Your ${b.vehicleMake} ${b.vehicleModel} is ready for pick-up at ${b.shopName}.`,
    },
  ],
}

/**
 * The issue title of a failed QC (D92: the `FAIL_QC` note, and so the technician's notification,
 * is the title only). The mock keeps the issue in `qcNotes` as "QC Issue: {title} — {description}";
 * notes in another shape are used whole. Null when there are none.
 */
export function qcIssueTitle(notes: string | undefined): string | null {
  const text = notes?.trim().replace(/^QC Issue:\s*/i, '')
  if (!text) return null
  return text.split(' — ')[0]!.trim() || null
}

/** A failed QC sends the job back to IN_REPAIR with `qcPassed: false`. */
const QC_FAILED = {
  type: 'QC_FAILED' as const,
  to: 'TECHNICIAN' as const,
  title: 'QC failed',
  body: (b: MockBooking) => {
    const issue = qcIssueTitle(b.qcNotes)?.replace(/[.\s]+$/, '')
    return `${b.licensePlate}: ${issue || 'see the inspection notes'}.`
  },
}

const LINK: Record<Audience, (b: MockBooking) => string> = {
  CUSTOMER: (b) => `/bookings/${b.id}`,
  SA: (b) => `/pos/shops/${b.shopId}/bookings/${b.id}`,
  TECHNICIAN: (b) => `/pos/shops/${b.shopId}/jobs/${b.id}`,
  PARTS: (b) => `/pos/shops/${b.shopId}/parts/${b.id}`,
  QC: (b) => `/pos/shops/${b.shopId}/qc/${b.id}`,
}

/** Whether `user` receives notifications meant for `audience` on booking `b`. */
function receives(
  user: CurrentUserSession,
  audience: Audience,
  b: MockBooking,
  team: ReadonlyArray<MockTeamMember>,
): boolean {
  if (audience === 'CUSTOMER') {
    // The booking's own customer only, by account (D21) — never someone with the same name.
    return user.role === 'CUSTOMER' && isBookingCustomer(b, user.email)
  }
  if (b.shopId !== user.shopId) return false
  // Staff hand-offs reach active members of the booking's own shop in that role only (D20),
  // whatever shop or role the session claims.
  const membership = team.find(
    (m) =>
      m.shopId === b.shopId &&
      m.is_active &&
      normaliseEmail(m.email) === normaliseEmail(user.email),
  )
  if (membership?.role !== user.role) return false
  switch (audience) {
    case 'SA': {
      if (user.role === 'SERVICE_ADVISOR') return true
      const shopHasSa = team.some(
        (m) => m.shopId === b.shopId && m.role === 'SERVICE_ADVISOR' && m.is_active,
      )
      return user.role === 'OWNER' && !shopHasSa
    }
    case 'TECHNICIAN':
      return user.role === 'TECHNICIAN' && b.assignedTechnicianName === user.name
    case 'PARTS':
      return user.role === 'PARTS_PERSON'
    case 'QC':
      return user.role === 'QC_INSPECTOR'
  }
}

/** The user's notifications, newest first (E-17's order). */
export function deriveNotifications(
  user: CurrentUserSession,
  bookings: ReadonlyArray<MockBooking>,
  team: ReadonlyArray<MockTeamMember>,
): MockNotification[] {
  const items: MockNotification[] = []
  for (const b of bookings) {
    const fired = bookingHistory(b).flatMap((step) =>
      (BY_STATUS[step.status] ?? []).map((rule) => ({ rule, at: step.at })),
    )
    if (b.status === 'IN_REPAIR' && b.qcPassed === false) {
      fired.push({ rule: QC_FAILED, at: b.updatedAt })
    }
    for (const { rule, at } of fired) {
      if (!receives(user, rule.to, b, team)) continue
      items.push({
        id: `${rule.type}:${b.id}`,
        type: rule.type,
        title: rule.title,
        body: rule.body(b),
        reference: b.reference,
        shopName: b.shopName,
        link: LINK[rule.to](b),
        createdAt: at,
      })
    }
  }
  return items.sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

const READ_KEY = 'notifications-read'

/** Whose move each status waits on: spec 11's "owns the next step". */
const NEXT_STEP_OWNER: Partial<Record<MockBooking['status'], Audience>> = {
  PENDING: 'SA',
  CONFIRMED: 'SA',
  ESTIMATE_REVIEW: 'SA',
  ESTIMATE_APPROVED: 'SA',
  ESTIMATE_REJECTED: 'SA',
  READY_FOR_PICKUP: 'SA',
  ASSIGNED: 'TECHNICIAN',
  INSPECTING: 'TECHNICIAN',
  IN_REPAIR: 'TECHNICIAN',
  AWAITING_CUSTOMER: 'CUSTOMER',
  PARTS_PENDING: 'PARTS',
  PARTS_ORDERED: 'PARTS',
  PARTS_READY: 'PARTS',
  QC_PENDING: 'QC',
  QC_IN_PROGRESS: 'QC',
}

let seedRead: string[] | null = null

/**
 * Spec 11 "Notifications after seeding": the seed leaves its sample bookings' notifications read,
 * except the latest one per recipient and booking when that recipient owns the booking's next step.
 * So each demo account starts with what waits on them only (Ayesha: her estimate; Bilal: the new
 * booking and the passed QC), and every browser starts from this read state.
 */
function seedReadIds(): string[] {
  if (seedRead) return seedRead
  const read: string[] = []
  for (const b of INITIAL_BOOKINGS) {
    const fired = passedStatuses(b.status).flatMap((status) => BY_STATUS[status] ?? [])
    // QC_FAILED is not a status rule, so it is never in this list: a QC failure stays unread.
    const latest = [...fired].reverse().find((rule) => rule.to === NEXT_STEP_OWNER[b.status])
    for (const rule of fired) if (rule !== latest) read.push(`${rule.type}:${b.id}`)
  }
  seedRead = read
  return seedRead
}

/** IDs the user has read (stable array until it changes, as `useMockStore` requires). */
export function getReadNotificationIds(): string[] {
  return getStoredData<string[]>(READ_KEY, seedReadIds())
}

/** E-19 / E-20: marks the given notifications read. */
export function markNotificationsRead(ids: ReadonlyArray<string>): void {
  const read = new Set(getReadNotificationIds())
  const before = read.size
  for (const id of ids) read.add(id)
  if (read.size !== before) setStoredData(READ_KEY, [...read])
}
