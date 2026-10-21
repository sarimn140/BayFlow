import { formatDateKey } from '@/lib/booking-slots'
import { DEFAULT_SHOP_TZ, shopDateKey } from '@/lib/format'
import type { AdminShop, AdminUser, AuditEvent } from '@/lib/mock-admin'
import type { MockBooking } from '@/lib/mock-data'
import {
  BOOKING_STATUS_META,
  STATUS_PHASES,
  statusPhase,
  type BookingStatus,
  type StatusPhase,
} from '@/lib/status'

/**
 * A-01 Platform overview (spec 19 §5): the figures of the admin overview (E-61), worked out from
 * the mock store with the API's rules, so the console counts the way the live endpoint will.
 */

/** Shops are in Pakistan (D38), so the platform's days are Asia/Karachi days. */
export const PLATFORM_TZ = DEFAULT_SHOP_TZ

const DAY_MS = 24 * 60 * 60 * 1000

/** Days in the bookings chart. */
export const CHART_DAYS = 14

/** The phases an open booking can be in (Closed holds `CANCELLED` only). */
export const OPEN_PHASES: ReadonlyArray<StatusPhase> = STATUS_PHASES.filter((p) => p !== 'CLOSED')

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

/** "a, b and c". */
export function listOf(items: ReadonlyArray<string>): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/** Open = not finished: neither `COMPLETED` nor `CANCELLED` (the terminal statuses). */
export function isOpenBooking(status: BookingStatus): boolean {
  return !BOOKING_STATUS_META[status].terminal
}

export interface PhaseCount {
  phase: StatusPhase
  count: number
}

/** Bookings per phase, in workflow order (zeros included). */
export function countByPhase(
  bookings: ReadonlyArray<Pick<MockBooking, 'status'>>,
  phases: ReadonlyArray<StatusPhase> = STATUS_PHASES,
): PhaseCount[] {
  return phases.map((phase) => ({
    phase,
    count: bookings.filter((b) => statusPhase(b.status) === phase).length,
  }))
}

/** The platform day of an ISO timestamp, or `null` when the value is not a date. */
function dayOf(iso: string, timeZone: string): string | null {
  try {
    return shopDateKey(iso, timeZone)
  } catch {
    return null
  }
}

function countByDay(keys: ReadonlyArray<string | null>): Map<string, number> {
  const counts = new Map<string, number>()
  for (const key of keys) if (key) counts.set(key, (counts.get(key) ?? 0) + 1)
  return counts
}

export interface DayActivity {
  /** "2026-10-09" in the platform's zone. */
  day: string
  /** Bookings created that day, in every shop. */
  bookings: number
  /** Audit events recorded that day. */
  events: number
}

/** The last `days` platform days, oldest first, ending today. */
export function dailyActivity(
  bookings: ReadonlyArray<Pick<MockBooking, 'createdAt'>>,
  audit: ReadonlyArray<Pick<AuditEvent, 'occurredAt'>>,
  now: Date,
  days = CHART_DAYS,
  timeZone = PLATFORM_TZ,
): DayActivity[] {
  const bookingDays = countByDay(bookings.map((b) => dayOf(b.createdAt, timeZone)))
  const eventDays = countByDay(audit.map((e) => dayOf(e.occurredAt, timeZone)))
  return Array.from({ length: days }, (_, index) => {
    const day = shopDateKey(new Date(now.getTime() - (days - 1 - index) * DAY_MS), timeZone)
    return { day, bookings: bookingDays.get(day) ?? 0, events: eventDays.get(day) ?? 0 }
  })
}

export interface PlatformStats {
  shops: number
  activeShops: number
  /** Suspended shops, in directory order. */
  suspended: AdminShop[]
  accounts: number
  customers: number
  staff: number
  /** Active platform admins. */
  admins: number
  /** Today's slots in every shop, cancelled ones left out. */
  bookingsToday: number
  /** Bookings that are neither completed nor cancelled. */
  open: number
  openByPhase: PhaseCount[]
  /** `auth.login_failed` events in the last 24 hours. */
  failedSignIns: number
  /** The five shops with the most bookings. */
  busiest: AdminShop[]
}

export function platformStats({
  users,
  tenants,
  bookings,
  audit,
  now,
  timeZone = PLATFORM_TZ,
}: {
  users: ReadonlyArray<AdminUser>
  tenants: ReadonlyArray<AdminShop>
  bookings: ReadonlyArray<MockBooking>
  audit: ReadonlyArray<AuditEvent>
  now: Date
  timeZone?: string
}): PlatformStats {
  const today = shopDateKey(now, timeZone)
  const open = bookings.filter((b) => isOpenBooking(b.status))
  const suspended = tenants.filter((t) => t.suspension)
  return {
    shops: tenants.length,
    activeShops: tenants.length - suspended.length,
    suspended,
    accounts: users.length,
    customers: users.filter((u) => u.kind === 'CUSTOMER').length,
    staff: users.filter((u) => u.kind === 'STAFF').length,
    admins: users.filter((u) => u.isPlatformAdmin && u.isActive).length,
    bookingsToday: bookings.filter((b) => b.scheduledDate === today && b.status !== 'CANCELLED')
      .length,
    open: open.length,
    openByPhase: countByPhase(open, OPEN_PHASES),
    failedSignIns: audit.filter(
      (e) => e.action === 'auth.login_failed' && now.getTime() - Date.parse(e.occurredAt) < DAY_MS,
    ).length,
    busiest: [...tenants].sort((a, b) => b.bookingsTotal - a.bookingsTotal).slice(0, 5),
  }
}

/** The hero's one line on the state of the platform. */
export function overviewSummary(stats: PlatformStats): string {
  const first = `${plural(stats.shops, 'shop')} and ${plural(stats.accounts, 'account')} on BayFlow, with ${plural(stats.open, 'open booking')}.`
  const attention = [
    stats.suspended.length > 0
      ? `${plural(stats.suspended.length, 'shop')} ${stats.suspended.length === 1 ? 'is' : 'are'} suspended`
      : null,
    stats.failedSignIns > 0
      ? `${plural(stats.failedSignIns, 'sign-in')} failed in the last 24 hours`
      : null,
  ].filter((clause): clause is string => clause !== null)
  if (attention.length === 0) {
    return `${first} No shop is suspended and no sign-in failed in the last 24 hours.`
  }
  const sentence = listOf(attention)
  return `${first} ${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`
}

/** "Good morning" / "Good afternoon" / "Good evening" at the platform's local hour. */
export function greetingAt(nowIso: string, timeZone = PLATFORM_TZ): string {
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

/** "Saturday, 10 October" in the platform's zone. */
export function longDate(nowIso: string, timeZone = PLATFORM_TZ): string {
  return new Intl.DateTimeFormat('en-PK', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone,
  }).format(new Date(nowIso))
}

/** The first word of a name, for the greeting ("Areeba Hashmi" → "Areeba"). */
export function firstName(name: string | null | undefined): string {
  return (name ?? '').trim().split(/\s+/)[0] || 'there'
}

/** "Fri 9 Oct" for a "YYYY-MM-DD" day; the key itself when it is not a date. */
export function dayLabel(dateKey: string): string {
  try {
    return formatDateKey(dateKey)
  } catch {
    return dateKey
  }
}

const SHORT_DAY = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

/** "9 Oct" for a "YYYY-MM-DD" day: the chart's axis labels. */
export function shortDayLabel(dateKey: string): string {
  const [y, m, d] = dateKey.split('-').map(Number) as [number, number, number]
  const date = new Date(Date.UTC(y, m - 1, d, 12))
  return Number.isNaN(date.getTime()) ? dateKey : SHORT_DAY.format(date)
}
