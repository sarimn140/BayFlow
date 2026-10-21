import { addDays, formatDateKey } from '@/lib/booking-slots'
import { formatPKR, formatRelative } from '@/lib/format'
import { IN_PROGRESS_STATUSES, SA_ACTION_STATUSES } from '@/lib/kpis'
import type { MockBooking } from '@/lib/mock-data'
import { slotSortKey } from '@/lib/slot'
import { BOOKING_STATUSES, isBookingStatus, type BookingStatus } from '@/lib/status'

/**
 * SA-01 bookings queue (spec 10): the presets, filters, URL format, order and "next step" of the
 * Service Advisor's list. Pure functions, so the page and the tests share one definition.
 */

/** The three queue views (spec 10 SA-01 presets), in toolbar order. */
export const QUEUE_PRESETS = ['needs_action', 'in_progress', 'all'] as const
export type QueuePreset = (typeof QUEUE_PRESETS)[number]

export const PRESET_LABELS: Record<QueuePreset, string> = {
  needs_action: 'Needs action',
  in_progress: 'In progress',
  all: 'All',
}

/** Date presets on the slot day (spec 10 SA-01 "Today / Next 7 days / All"). */
export const DATE_RANGES = ['any', 'today', 'next_7_days'] as const
export type DateRange = (typeof DATE_RANGES)[number]

export const DATE_RANGE_LABELS: Record<DateRange, string> = {
  any: 'Any day',
  today: 'Today',
  next_7_days: 'Next 7 days',
}

export const PAGE_SIZE = 20

/** The API caps `q` at 100 characters (E-33). */
export const MAX_QUERY_LENGTH = 100

export interface QueueFilters {
  preset: QueuePreset
  /** One status picked from the status filter; it always comes with the `all` preset. */
  status: BookingStatus | null
  date: DateRange
  /** Reference, plate, customer or car, as typed. */
  query: string
  /** 1-based. */
  page: number
}

/** First visit: the Service Advisor's own queue (spec 10 SA-01). */
export const DEFAULT_FILTERS: QueueFilters = {
  preset: 'needs_action',
  status: null,
  date: 'any',
  query: '',
  page: 1,
}

/**
 * Whether the booking belongs to a preset. "Needs action" and "In progress" are the status
 * groups of the overview tiles and the API (`lib/kpis.ts`), so their counts agree everywhere.
 */
export function inPreset(status: BookingStatus, preset: QueuePreset): boolean {
  if (preset === 'needs_action') return SA_ACTION_STATUSES.has(status)
  if (preset === 'in_progress') return IN_PROGRESS_STATUSES.has(status)
  return true
}

/** Lower-case letters and digits only, so "lea 22" finds "LEA-22-4589". */
function compact(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '')
}

/** Search by reference, customer name, plate or car (make and model). */
export function matchesQuery(
  booking: Pick<
    MockBooking,
    'reference' | 'customerName' | 'licensePlate' | 'vehicleMake' | 'vehicleModel'
  >,
  query: string,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  const car = `${booking.vehicleMake} ${booking.vehicleModel}`
  const fields = [booking.reference, booking.customerName, booking.licensePlate, car]
  if (fields.some((field) => field.toLowerCase().includes(needle))) return true
  const compactNeedle = compact(needle)
  if (!compactNeedle) return false
  return [booking.reference, booking.licensePlate].some((field) =>
    compact(field).includes(compactNeedle),
  )
}

/** The slot day against a date preset; `todayKey` is the shop's "YYYY-MM-DD" today. */
export function matchesDate(
  booking: Pick<MockBooking, 'scheduledDate'>,
  range: DateRange,
  todayKey: string,
): boolean {
  if (range === 'today') return booking.scheduledDate === todayKey
  if (range === 'next_7_days') {
    return booking.scheduledDate >= todayKey && booking.scheduledDate <= addDays(todayKey, 6)
  }
  return true
}

/** Status, date and search filters, without the preset (used for "matches in other views"). */
export function matchesRefinements(
  booking: MockBooking,
  filters: Pick<QueueFilters, 'status' | 'date' | 'query'>,
  todayKey: string,
): boolean {
  if (filters.status && booking.status !== filters.status) return false
  return matchesDate(booking, filters.date, todayKey) && matchesQuery(booking, filters.query)
}

/**
 * The rows of a view, in the spec's default order: the slot, soonest first, for the two working
 * queues; the latest change first for "All" (spec 10 SA-01 "Default sort").
 */
export function selectBookings(
  bookings: ReadonlyArray<MockBooking>,
  filters: QueueFilters,
  todayKey: string,
): MockBooking[] {
  const rows = bookings.filter(
    (booking) =>
      inPreset(booking.status, filters.preset) && matchesRefinements(booking, filters, todayKey),
  )
  if (filters.preset === 'all') {
    return rows.sort(
      (a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.reference.localeCompare(b.reference),
    )
  }
  return rows.sort(
    (a, b) =>
      slotSortKey(a).localeCompare(slotSortKey(b)) || a.reference.localeCompare(b.reference),
  )
}

export interface QueueCounts {
  presets: Record<QueuePreset, number>
  statuses: Record<BookingStatus, number>
}

/** Per preset and per status, over every booking of the shop (spec 10 SA-01, E-34). */
export function countBookings(bookings: ReadonlyArray<Pick<MockBooking, 'status'>>): QueueCounts {
  const statuses = Object.fromEntries(BOOKING_STATUSES.map((status) => [status, 0])) as Record<
    BookingStatus,
    number
  >
  for (const booking of bookings) {
    if (isBookingStatus(booking.status)) statuses[booking.status] += 1
  }
  const presets = Object.fromEntries(
    QUEUE_PRESETS.map((preset) => [
      preset,
      bookings.filter((booking) => inPreset(booking.status, preset)).length,
    ]),
  ) as Record<QueuePreset, number>
  return { presets, statuses }
}

export interface PageSlice<T> {
  rows: T[]
  page: number
  pageCount: number
  /** 1-based positions of the first and last row shown. */
  from: number
  to: number
}

export function paginate<T>(rows: ReadonlyArray<T>, page: number): PageSlice<T> {
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const current = Math.min(Math.max(1, page), pageCount)
  const start = (current - 1) * PAGE_SIZE
  const slice = rows.slice(start, start + PAGE_SIZE)
  return {
    rows: slice,
    page: current,
    pageCount,
    from: slice.length ? start + 1 : 0,
    to: start + slice.length,
  }
}

// ---------------------------------------------------------------------------------------------
// URL (spec 09 §4.7 "Filters live in the URL")
// ---------------------------------------------------------------------------------------------

interface ReadableParams {
  get(name: string): string | null
  getAll(name: string): string[]
}

const PRESET_ALIASES: Record<string, QueuePreset> = {
  needs_action: 'needs_action',
  needs_sa: 'needs_action',
  needs_sa_action: 'needs_action',
  in_progress: 'in_progress',
  all: 'all',
}

/** Shortcuts that other screens link with, e.g. the overview's "Ready for pick-up" tile. */
const STATUS_ALIASES: Record<string, BookingStatus> = {
  ready: 'READY_FOR_PICKUP',
  completed: 'COMPLETED',
  cancelled: 'CANCELLED',
}

const DATE_ALIASES: Record<string, DateRange> = {
  today: 'today',
  next_7_days: 'next_7_days',
  week: 'next_7_days',
}

function toStatus(value: string | null | undefined): BookingStatus | null {
  if (!value) return null
  const normalised = value.trim().replace(/-/g, '_')
  const upper = normalised.toUpperCase()
  if (isBookingStatus(upper)) return upper
  return STATUS_ALIASES[normalised.toLowerCase()] ?? null
}

/**
 * Reads `?filter=&status=&date=&q=&page=`. Accepts the links other screens use
 * (`filter=needs_action`, `filter=ready`, `filter=completed`, `status=PENDING`); a status always
 * shows under "All". Unknown values fall back to the defaults.
 */
export function parseQueueParams(params: ReadableParams): QueueFilters {
  const filter = (params.get('filter') ?? '').trim().toLowerCase().replace(/-/g, '_')
  const status =
    params
      .getAll('status')
      .map(toStatus)
      .find((value) => value !== null) ?? (PRESET_ALIASES[filter] ? null : toStatus(filter))
  const preset: QueuePreset = status ? 'all' : (PRESET_ALIASES[filter] ?? DEFAULT_FILTERS.preset)
  const dateParam = (params.get('date') ?? '').trim().toLowerCase().replace(/-/g, '_')
  const page = Number.parseInt(params.get('page') ?? '', 10)
  return {
    preset,
    status,
    date: DATE_ALIASES[dateParam] ?? DEFAULT_FILTERS.date,
    query: normaliseQuery(params.get('q') ?? ''),
    page: Number.isFinite(page) && page > 1 ? page : 1,
  }
}

/** The search as it goes into and comes out of the URL: trimmed, at most 100 characters. */
export function normaliseQuery(query: string): string {
  return query.trim().slice(0, MAX_QUERY_LENGTH).trim()
}

/** The canonical query string for a filter state ('' for the defaults). */
export function queueSearchString(filters: QueueFilters): string {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  else if (filters.preset !== DEFAULT_FILTERS.preset) params.set('filter', filters.preset)
  if (filters.date !== 'any') params.set('date', filters.date)
  const query = normaliseQuery(filters.query)
  if (query) params.set('q', query)
  if (filters.page > 1) params.set('page', String(filters.page))
  return params.toString()
}

// ---------------------------------------------------------------------------------------------
// Row content
// ---------------------------------------------------------------------------------------------

export type NextStep =
  { kind: 'action'; label: string } | { kind: 'waiting'; label: string } | { kind: 'none' }

/**
 * The Service Advisor's next move: the first forward action of the status (spec 09 §4.6 labels;
 * spec 10 SA-01 "Next step"). When the step belongs to someone else, who the advisor is waiting
 * on (spec 11 "owns the next step"); nothing once the booking is closed.
 */
const SA_ACTIONS: Partial<Record<BookingStatus, string>> = {
  PENDING: 'Confirm booking',
  CONFIRMED: 'Assign technician',
  ESTIMATE_REVIEW: 'Send estimate',
  ESTIMATE_APPROVED: 'Assign parts person',
  ESTIMATE_REJECTED: 'Revise estimate',
  READY_FOR_PICKUP: 'Notify customer',
}

const WAITING_ON: Partial<Record<BookingStatus, string>> = {
  ASSIGNED: 'Waiting on technician',
  INSPECTING: 'Waiting on technician',
  IN_REPAIR: 'Waiting on technician',
  AWAITING_CUSTOMER: 'Waiting on customer',
  PARTS_PENDING: 'Waiting on parts',
  PARTS_ORDERED: 'Waiting on parts',
  PARTS_READY: 'Waiting on parts',
  QC_PENDING: 'Waiting on QC',
  QC_IN_PROGRESS: 'Waiting on QC',
}

export function nextStepFor(status: BookingStatus): NextStep {
  const action = SA_ACTIONS[status]
  if (action) return { kind: 'action', label: action }
  const waiting = WAITING_ON[status]
  if (waiting) return { kind: 'waiting', label: waiting }
  return { kind: 'none' }
}

const DATE_KEY = /^\d{4}-\d{2}-\d{2}$/

/** "Today · 09:00 am", "Tomorrow · …", "Fri 9 Oct · …" (with the year when it isn't this year). */
export function slotLabel(
  booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>,
  todayKey: string,
): string {
  const { scheduledDate: date, scheduledTime: time } = booking
  if (!DATE_KEY.test(date)) return [date, time].filter(Boolean).join(' · ')
  let day: string
  if (date === todayKey) day = 'Today'
  else if (date === addDays(todayKey, 1)) day = 'Tomorrow'
  else if (date === addDays(todayKey, -1)) day = 'Yesterday'
  else day = formatDateKey(date, date.slice(0, 4) !== todayKey.slice(0, 4))
  return time ? `${day} · ${time}` : day
}

/** The slot as an HTML `datetime` value ("2026-10-09T10:00"), or undefined if unparsable. */
export function slotDateTime(
  booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>,
): string | undefined {
  const key = slotSortKey(booking)
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(key) ? key.replace(' ', 'T') : undefined
}

/** "Updated 2 hours ago"; null when the timestamp can't be read. */
export function updatedLabel(updatedAt: string, nowIso: string): string | null {
  try {
    return `Updated ${formatRelative(updatedAt, new Date(nowIso))}`
  } catch {
    return null
  }
}

/** The estimate's grand total once it has lines (bookings start without one). */
export function estimateLabel(
  booking: Pick<MockBooking, 'estimateItems' | 'estimateTotal'>,
): string | null {
  if (!booking.estimateItems?.length || !Number.isFinite(booking.estimateTotal)) return null
  return `Estimate ${formatPKR(booking.estimateTotal)}`
}

/** The first service, plus how many more ("Oil change", "+1 more"). */
export function servicesSummary(services: ReadonlyArray<string>): {
  first: string
  more: number
} {
  return { first: services[0] ?? 'No services listed', more: Math.max(0, services.length - 1) }
}
