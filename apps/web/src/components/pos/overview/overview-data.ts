import { formatDateKey } from '@/lib/booking-slots'
import { DEFAULT_SHOP_TZ, formatRelative, shopDateKey } from '@/lib/format'
import { IN_PROGRESS_STATUSES, SA_ACTION_STATUSES, isLowStock } from '@/lib/kpis'
import type {
  MockBooking,
  MockPart,
  MockPurchaseOrder,
  MockService,
  MockShop,
  MockTeamMember,
} from '@/lib/mock-data'
import { STATUS_PHASES, statusesInPhase, type BookingStatus, type StatusPhase } from '@/lib/status'

/**
 * O-01 Shop overview (spec 10): the figures of `GET /api/v1/shops/{shop_id}/overview` (E-31,
 * `OverviewRead`), worked out from the mock store with the API's rules so the screen already
 * counts the way the live endpoint will.
 */

export type MemberRole = MockTeamMember['role']

/** Glossary §2.1 order; E-31 lists the team by role, then name. */
export const ROLE_ORDER: ReadonlyArray<MemberRole> = [
  'OWNER',
  'SERVICE_ADVISOR',
  'TECHNICIAN',
  'PARTS_PERSON',
  'QC_INSPECTOR',
]

/** Roles that are assigned jobs (technician, parts person, QC picker), so `open_jobs` applies. */
export const ASSIGNABLE_ROLES: ReadonlySet<MemberRole> = new Set<MemberRole>([
  'TECHNICIAN',
  'PARTS_PERSON',
  'QC_INSPECTOR',
])

/** The API's `OPEN_JOB_EXCLUDED_STATUSES`: every other status is an open job. */
const NOT_OPEN_JOBS: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'READY_FOR_PICKUP',
  'COMPLETED',
  'CANCELLED',
])

/** `open_jobs`: bookings still open where the member is the technician, parts person or QC picker. */
export function openJobs(memberId: string, bookings: ReadonlyArray<MockBooking>): number {
  return bookings.filter(
    (b) =>
      !NOT_OPEN_JOBS.has(b.status) &&
      (b.assignedTechnicianId === memberId ||
        b.assignedPartsPersonId === memberId ||
        b.qcInspectorId === memberId),
  ).length
}

/** The team by role (glossary order), then by name. */
export function sortTeam(team: ReadonlyArray<MockTeamMember>): MockTeamMember[] {
  return [...team].sort(
    (a, b) =>
      ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.name.localeCompare(b.name),
  )
}

/** `OverviewSetup`: the four steps of the first-run checklist (UX rule R12). */
export interface SetupState {
  /** At least one active service. */
  hasServices: boolean
  /** At least one active member besides the owner. */
  hasTeam: boolean
  /** At least one part. */
  hasParts: boolean
  /** Shown in the public directory. */
  isListed: boolean
}

export function setupState(
  shop: Pick<MockShop, 'is_listed'>,
  services: ReadonlyArray<MockService>,
  team: ReadonlyArray<MockTeamMember>,
  parts: ReadonlyArray<MockPart>,
): SetupState {
  return {
    hasServices: services.some((s) => s.is_active),
    hasTeam: team.some((m) => m.role !== 'OWNER' && m.is_active),
    hasParts: parts.length > 0,
    isListed: shop.is_listed,
  }
}

/** A valid IANA zone for `Intl`, else the default shop zone (D38). */
export function safeTimeZone(timeZone: string | undefined): string {
  if (!timeZone) return DEFAULT_SHOP_TZ
  try {
    new Intl.DateTimeFormat('en', { timeZone })
    return timeZone
  } catch {
    return DEFAULT_SHOP_TZ
  }
}

/** The shop-local day of an ISO timestamp, or `null` when the value is not a date. */
function dayOf(iso: string, timeZone: string): string | null {
  try {
    return shopDateKey(iso, timeZone)
  } catch {
    return null
  }
}

/** KPI tiles and the hero line (`OverviewToday` plus the SA status groups of `lib/kpis`). */
export interface OverviewKpis {
  /** Waiting on a service advisor (pick-up calls included). */
  needsSaAction: number
  /** With technicians, the customer, parts or QC. */
  inProgress: number
  readyForPickup: number
  /** Completed today, in the shop's time zone. */
  completedToday: number
  completedTotal: number
  /** Not cancelled, slot today. */
  scheduledToday: number
}

export function overviewKpis(
  bookings: ReadonlyArray<MockBooking>,
  todayKey: string,
  timeZone: string,
): OverviewKpis {
  const completed = bookings.filter((b) => b.status === 'COMPLETED')
  return {
    needsSaAction: bookings.filter((b) => SA_ACTION_STATUSES.has(b.status)).length,
    inProgress: bookings.filter((b) => IN_PROGRESS_STATUSES.has(b.status)).length,
    readyForPickup: bookings.filter((b) => b.status === 'READY_FOR_PICKUP').length,
    completedToday: completed.filter((b) => dayOf(b.updatedAt, timeZone) === todayKey).length,
    completedTotal: completed.length,
    scheduledToday: bookings.filter((b) => b.scheduledDate === todayKey && b.status !== 'CANCELLED')
      .length,
  }
}

export interface PhaseCount {
  phase: StatusPhase
  total: number
  /** Every status of the phase in lifecycle order, zeros included. */
  statuses: { status: BookingStatus; count: number }[]
}

/** `status_counts` grouped into the seven phases (glossary §5 `StatusPhase`). */
export function countByPhase(bookings: ReadonlyArray<MockBooking>): PhaseCount[] {
  const counts = new Map<BookingStatus, number>()
  for (const b of bookings) counts.set(b.status, (counts.get(b.status) ?? 0) + 1)
  return STATUS_PHASES.map((phase) => {
    const statuses = statusesInPhase(phase).map((status) => ({
      status,
      count: counts.get(status) ?? 0,
    }))
    return { phase, total: statuses.reduce((sum, s) => sum + s.count, 0), statuses }
  })
}

export type SaActionStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'ESTIMATE_REVIEW'
  | 'ESTIMATE_APPROVED'
  | 'ESTIMATE_REJECTED'
  | 'READY_FOR_PICKUP'

/** The advisor's next move per status (spec 08 transitions T02, T04, T07, T10, T12, O3/T21). */
export const NEXT_STEP: Record<SaActionStatus, string> = {
  PENDING: 'Confirm or decline the booking',
  CONFIRMED: 'Assign a technician',
  ESTIMATE_REVIEW: 'Review and send the estimate',
  ESTIMATE_APPROVED: 'Assign a parts person',
  ESTIMATE_REJECTED: 'Follow up on the declined estimate',
  READY_FOR_PICKUP: 'Call the customer for pick-up',
}

export function isSaActionStatus(status: BookingStatus): status is SaActionStatus {
  return SA_ACTION_STATUSES.has(status)
}

function timeOf(iso: string): number {
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? 0 : ms
}

/** "Fri 9 Oct" for a slot day ("YYYY-MM-DD"); the stored value as is when it is not a date. */
export function dayLabel(dateKey: string): string {
  try {
    return formatDateKey(dateKey)
  } catch {
    return dateKey
  }
}

/** "Updated 2 hours ago"; empty when the stored timestamp is not a date. */
export function updatedAgo(iso: string, now: Date): string {
  try {
    return `Updated ${formatRelative(iso, now)}`
  } catch {
    return ''
  }
}

/** Bookings waiting on a service advisor, longest wait first. */
export function attentionQueue(bookings: ReadonlyArray<MockBooking>): MockBooking[] {
  return bookings
    .filter((b) => isSaActionStatus(b.status))
    .sort((a, b) => timeOf(a.updatedAt) - timeOf(b.updatedAt))
}

/** The last `limit` bookings that changed (E-33 `?sort=-updated_at&limit=5`). */
export function recentlyUpdated(bookings: ReadonlyArray<MockBooking>, limit = 5): MockBooking[] {
  return [...bookings].sort((a, b) => timeOf(b.updatedAt) - timeOf(a.updatedAt)).slice(0, limit)
}

/** Minutes after midnight of a slot label such as "02:00 pm" or "14:00"; unknown labels sort last. */
export function slotMinutes(label: string): number {
  const match = /^(\d{1,2}):(\d{2})\s*([ap]m)?$/i.exec(label.trim())
  if (!match) return Number.MAX_SAFE_INTEGER
  const hours = Number(match[1])
  const minutes = Number(match[2])
  const meridiem = match[3]?.toLowerCase()
  const hour24 = meridiem ? (hours % 12) + (meridiem === 'pm' ? 12 : 0) : hours
  return hour24 * 60 + minutes
}

/** Today's slots (not cancelled), earliest first. */
export function scheduledOn(bookings: ReadonlyArray<MockBooking>, dayKey: string): MockBooking[] {
  return bookings
    .filter((b) => b.scheduledDate === dayKey && b.status !== 'CANCELLED')
    .sort((a, b) => slotMinutes(a.scheduledTime) - slotMinutes(b.scheduledTime))
}

/** What is free to use: on hand minus reserved (D45). */
export function available(part: Pick<MockPart, 'on_hand' | 'reserved'>): number {
  return part.on_hand - part.reserved
}

/** `OverviewInventory` plus `low_stock` (up to 5 parts: OUT first, then by available, then SKU). */
export interface InventoryHealth {
  partsCount: number
  /** LOW or OUT. */
  lowCount: number
  /** Nothing available. */
  outCount: number
  stockValue: number
  /** ORDERED or PARTIALLY_RECEIVED. */
  openPurchaseOrders: number
  restock: MockPart[]
}

export function inventoryHealth(
  parts: ReadonlyArray<MockPart>,
  purchaseOrders: ReadonlyArray<MockPurchaseOrder>,
): InventoryHealth {
  const low = parts.filter(isLowStock)
  const isOut = (p: MockPart) => available(p) <= 0
  return {
    partsCount: parts.length,
    lowCount: low.length,
    outCount: low.filter(isOut).length,
    stockValue: parts.reduce((sum, p) => sum + p.on_hand * p.unit_price, 0),
    openPurchaseOrders: purchaseOrders.filter(
      (po) => po.status === 'ORDERED' || po.status === 'PARTIALLY_RECEIVED',
    ).length,
    restock: [...low]
      .sort(
        (a, b) =>
          Number(isOut(b)) - Number(isOut(a)) ||
          available(a) - available(b) ||
          a.sku.localeCompare(b.sku),
      )
      .slice(0, 5),
  }
}

/** "1 booking", "3 bookings". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

/** "a, b and c". */
export function listOf(items: ReadonlyArray<string>): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/** The hero's one-line state of the shop. */
export function overviewSummary(kpis: OverviewKpis, totalBookings: number): string {
  if (totalBookings === 0) return 'No bookings yet. They appear here as soon as customers book.'
  const clauses = [
    kpis.inProgress > 0 ? `${plural(kpis.inProgress, 'job')} in progress` : null,
    kpis.needsSaAction > 0
      ? `${plural(kpis.needsSaAction, 'booking')} waiting on a service advisor`
      : null,
    kpis.scheduledToday > 0
      ? `${plural(kpis.scheduledToday, 'booking')} on today's schedule`
      : null,
  ].filter((clause): clause is string => clause !== null)
  if (clauses.length === 0) return 'Nothing is waiting on your team right now.'
  return `${listOf(clauses)}.`
}

/** "Good morning" / "Good afternoon" / "Good evening" at the shop's local hour. */
export function greetingAt(nowIso: string, timeZone: string): string {
  const hourPart = new Intl.DateTimeFormat('en-GB', {
    hour: 'numeric',
    hourCycle: 'h23',
    timeZone,
  })
    .formatToParts(new Date(nowIso))
    .find((part) => part.type === 'hour')
  const hour = Number(hourPart?.value ?? 12)
  if (hour >= 5 && hour < 12) return 'Good morning'
  if (hour >= 12 && hour < 17) return 'Good afternoon'
  return 'Good evening'
}

/** "Saturday, 10 October" in the shop's time zone. */
export function longDate(nowIso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-PK', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone,
  }).format(new Date(nowIso))
}
