import type { MockBooking, MockShop } from '@/lib/mock-data'

/**
 * Opening days and free slots for the booking wizard while the screens run on mock data. Stands
 * in for E-09 (`GET /public/shops/{slug}/availability`) and follows its rules (spec 10 P-03 W3,
 * D37, D68): dates from the shop's today to today + 30, only weekdays with working hours, a slot
 * grid of `slot_duration_minutes` from opening time, no slot that has already started, and only
 * slots with a free place (`remaining` ≥ 1). Dates are shop-local "YYYY-MM-DD" keys.
 */

export const BOOKING_HORIZON_DAYS = 30

/** Glossary weekday 0 = Monday. */
export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const

export interface OpeningHours {
  /** Minutes after midnight, shop time. */
  open: number
  close: number
}

export interface FreeSlot {
  /** "10:00 am", the format mock bookings store in `scheduledTime`. */
  time: string
  /** Minutes after midnight, shop time. */
  start: number
  remaining: number
}

const HOURS = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/

function parseHours(hours: string): OpeningHours | null {
  const match = HOURS.exec(hours.trim())
  if (!match) return null
  const [, oh, om, ch, cm] = match.map(Number) as [number, number, number, number, number]
  const open = oh * 60 + om
  const close = ch * 60 + cm
  return close > open ? { open, close } : null
}

/** The weekday of a "YYYY-MM-DD" key (calendar arithmetic, no timezone involved). */
export function weekdayOf(dateKey: string): (typeof WEEKDAYS)[number] {
  const [y, m, d] = dateKey.split('-').map(Number) as [number, number, number]
  const sundayFirst = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  return WEEKDAYS[(sundayFirst + 6) % 7]!
}

export function addDays(dateKey: string, days: number): string {
  const [y, m, d] = dateKey.split('-').map(Number) as [number, number, number]
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

/** The shop's hours on that day, or null when it is closed. */
export function hoursOn(shop: Pick<MockShop, 'working_hours'>, dateKey: string) {
  const day = weekdayOf(dateKey)
  const row = shop.working_hours.find((wh) => wh.day === day)
  if (!row || row.is_closed) return null
  return parseHours(row.hours)
}

/** Minutes after midnight in the shop's timezone. */
export function minutesInZone(now: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(now)
  const part = (type: 'hour' | 'minute') =>
    Number(parts.find((candidate) => candidate.type === type)?.value ?? 0)
  return part('hour') * 60 + part('minute')
}

/** "10:00 am" for 600 minutes; hours keep a leading zero like the stored bookings. */
export function slotLabel(minutes: number): string {
  const h24 = Math.floor(minutes / 60)
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12
  const mm = String(minutes % 60).padStart(2, '0')
  return `${String(h12).padStart(2, '0')}:${mm} ${h24 < 12 ? 'am' : 'pm'}`
}

/** Every date in the booking window on which the shop is open. */
export function openDates(shop: Pick<MockShop, 'working_hours'>, todayKey: string): string[] {
  const dates: string[] = []
  for (let offset = 0; offset <= BOOKING_HORIZON_DAYS; offset += 1) {
    const key = addDays(todayKey, offset)
    if (hoursOn(shop, key)) dates.push(key)
  }
  return dates
}

export interface SlotContext {
  todayKey: string
  /** Minutes after midnight now, shop time. */
  nowMinutes: number
  bookings: ReadonlyArray<
    Pick<MockBooking, 'shopId' | 'scheduledDate' | 'scheduledTime' | 'status'>
  >
}

/** The free slots on a date: empty when the shop is closed or the date is outside the window. */
export function freeSlots(
  shop: Pick<MockShop, 'id' | 'working_hours' | 'slot_duration_minutes' | 'slot_capacity'>,
  dateKey: string,
  { todayKey, nowMinutes, bookings }: SlotContext,
): FreeSlot[] {
  if (dateKey < todayKey || dateKey > addDays(todayKey, BOOKING_HORIZON_DAYS)) return []
  const hours = hoursOn(shop, dateKey)
  if (!hours) return []
  const step = shop.slot_duration_minutes
  const taken = new Map<string, number>()
  for (const b of bookings) {
    if (b.shopId !== shop.id || b.scheduledDate !== dateKey || b.status === 'CANCELLED') continue
    taken.set(b.scheduledTime, (taken.get(b.scheduledTime) ?? 0) + 1)
  }
  const slots: FreeSlot[] = []
  for (let start = hours.open; start + step <= hours.close; start += step) {
    if (dateKey === todayKey && start <= nowMinutes) continue
    const time = slotLabel(start)
    const remaining = shop.slot_capacity - (taken.get(time) ?? 0)
    if (remaining > 0) slots.push({ time, start, remaining })
  }
  return slots
}

/** "Mon 12 Oct" (or "Mon 12 Oct 2026") for a date key, built from parts so ICU can't add commas. */
export function formatDateKey(dateKey: string, withYear = false): string {
  const [y, m, d] = dateKey.split('-').map(Number) as [number, number, number]
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).formatToParts(new Date(Date.UTC(y, m - 1, d, 12)))
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? ''
  const label = `${part('weekday')} ${part('day')} ${part('month')}`
  return withYear ? `${label} ${part('year')}` : label
}
