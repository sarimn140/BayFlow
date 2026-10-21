/**
 * Display formatting for money and time (spec 09 §2.11, UX rule R4).
 *
 * - Money: PKR in whole rupees with exactly the D41 formatter. API money fields are decimal
 *   strings ("16100.00", glossary §9); never do arithmetic on them here.
 * - Time: timestamps arrive as UTC ISO strings and are always shown in the shop's timezone
 *   (D38), never the viewer's. Default shop timezone: Asia/Karachi (UTC+5, no DST).
 *
 * Format where the data is fetched (server for public pages, client elsewhere) to avoid
 * hydration mismatches between Node and browser ICU builds (spec 09 §2.4 rule 7).
 */

export const DEFAULT_SHOP_TZ = 'Asia/Karachi'

// D41: `Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })`. CLDR gives PKR
// 0 fraction digits, so "16100.00" renders "Rs 16,100" (U+00A0 after "Rs", rounding half-expand).
const PKR = new Intl.NumberFormat('en-PK', { style: 'currency', currency: 'PKR' })

/** Formats a PKR amount (API decimal string or number), e.g. "16100.00" → "Rs 16,100". */
export function formatPKR(amount: string | number): string {
  // Number('') is 0: an empty string must not silently render as "Rs 0".
  if (typeof amount === 'string' && amount.trim() === '') {
    throw new RangeError('formatPKR: empty amount')
  }
  const value = typeof amount === 'number' ? amount : Number(amount)
  if (!Number.isFinite(value)) {
    throw new RangeError(`formatPKR: not a finite amount: ${String(amount)}`)
  }
  return PKR.format(value)
}

type DateInput = string | Date

function toDate(input: DateInput): Date {
  const date = typeof input === 'string' ? new Date(input) : input
  if (Number.isNaN(date.getTime())) {
    throw new RangeError(`Invalid date: ${String(input)}`)
  }
  return date
}

// Intl.DateTimeFormat construction is relatively expensive; cache one formatter per (kind, tz).
const formatterCache = new Map<string, Intl.DateTimeFormat>()

function formatter(
  kind: 'date' | 'time' | 'key',
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
  locale = 'en-PK',
): Intl.DateTimeFormat {
  const cacheKey = `${kind}|${timeZone}`
  let cached = formatterCache.get(cacheKey)
  if (!cached) {
    cached = new Intl.DateTimeFormat(locale, { ...options, timeZone })
    formatterCache.set(cacheKey, cached)
  }
  return cached
}

/** "Fri, 16 Oct 2026" in the shop's timezone. */
export function formatDate(input: DateInput, timeZone: string = DEFAULT_SHOP_TZ): string {
  return formatter('date', timeZone, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(toDate(input))
}

/** "10:00 am" in the shop's timezone. */
export function formatTime(input: DateInput, timeZone: string = DEFAULT_SHOP_TZ): string {
  return formatter('time', timeZone, { hour: 'numeric', minute: '2-digit' }).format(toDate(input))
}

/** "Fri, 16 Oct 2026 · 10:00 am" in the shop's timezone. */
export function formatDateTime(input: DateInput, timeZone: string = DEFAULT_SHOP_TZ): string {
  return `${formatDate(input, timeZone)} · ${formatTime(input, timeZone)}`
}

/** A slot start, e.g. "Fri, 16 Oct 2026 · 10:00 am" (spec 09 §2.11 `formatSlot`). */
export const formatSlot = formatDateTime

/**
 * The shop-local calendar day as "YYYY-MM-DD" (used for `?date=` on availability).
 * Built from date parts rather than a locale pattern so CLDR changes cannot alter it.
 */
export function shopDateKey(input: DateInput, timeZone: string = DEFAULT_SHOP_TZ): string {
  const parts = formatter(
    'key',
    timeZone,
    { year: 'numeric', month: '2-digit', day: '2-digit' },
    'en-CA',
  ).formatToParts(toDate(input))
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

const RELATIVE = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

const RELATIVE_UNITS: ReadonlyArray<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 365 * 24 * 60 * 60],
  ['month', 30 * 24 * 60 * 60],
  ['week', 7 * 24 * 60 * 60],
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
  ['second', 1],
]

/**
 * "5 minutes ago" / "in 2 hours". Depends on "now", so render it only on the client after
 * mount (`<RelativeTime>`, spec 09 §2.4 rule 7). `now` is injectable for tests.
 */
export function formatRelative(input: DateInput, now: Date = new Date()): string {
  const seconds = Math.round((toDate(input).getTime() - now.getTime()) / 1000)
  for (const [unit, unitSeconds] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= unitSeconds || unit === 'second') {
      return RELATIVE.format(Math.round(seconds / unitSeconds), unit)
    }
  }
  return RELATIVE.format(0, 'second')
}
