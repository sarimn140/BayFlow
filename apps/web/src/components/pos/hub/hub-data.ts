import { slotLabel } from '@/lib/booking-slots'
import { DEFAULT_SHOP_TZ, shopDateKey } from '@/lib/format'
import { IN_PROGRESS_STATUSES, SA_ACTION_STATUSES, isLowStock } from '@/lib/kpis'
import { homePathFor } from '@/lib/mock-auth'
import type { MockBooking, MockPart, MockShop, MockTeamMember } from '@/lib/mock-data'

/**
 * The POS pages outside a shop (spec 10 S-02 hub, S-03 / O-05 create shop, O-07 summary), worked
 * out from the mock store with the API's rules so the screens already behave as they will once
 * `GET /api/v1/me`, `POST /api/v1/shops` and `GET /api/v1/me/owner-summary` are wired.
 */

export type ShopRole = MockTeamMember['role']

// --- Workspaces (S-02) ----------------------------------------------------------------------------

/** A shop the signed-in person works in, with their role there (a `/me` membership, D66). */
export interface Workspace {
  shop: MockShop
  role: ShopRole
}

/**
 * The person's active memberships, one per shop, by shop name (the order of `/me` and of the shop
 * switcher). Inactive memberships are left out, as `/me` leaves them out (D19).
 */
export function workspacesOf(
  email: string,
  team: ReadonlyArray<MockTeamMember>,
  shops: ReadonlyArray<MockShop>,
): Workspace[] {
  const byId = new Map(shops.map((shop) => [shop.id, shop]))
  const seen = new Set<string>()
  const workspaces: Workspace[] = []
  for (const member of team) {
    if (!member.is_active || member.email !== email) continue
    const shop = byId.get(member.shopId)
    if (!shop || seen.has(shop.id)) continue
    seen.add(shop.id)
    workspaces.push({ shop, role: member.role })
  }
  return workspaces.sort((a, b) => byName(a.shop, b.shop))
}

/** Where a workspace opens: the role's home in that shop (spec 10 S-04). */
export function workspaceHref(workspace: Workspace): string {
  return homePathFor({ role: workspace.role, shopId: workspace.shop.id })
}

/** Shop name, then id: the order of `/me`, the switcher and the owner summary. */
function byName(a: MockShop, b: MockShop): number {
  return a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
}

// --- Owner summary (O-07, E-32) -------------------------------------------------------------------

/** The shops `email` owns (active `OWNER` memberships): who may open O-07 and what it counts. */
export function ownedShopIds(email: string, team: ReadonlyArray<MockTeamMember>): Set<string> {
  return new Set(
    team.filter((m) => m.role === 'OWNER' && m.is_active && m.email === email).map((m) => m.shopId),
  )
}

export interface ShopSummaryRow {
  shop: MockShop
  /** Bookings on the shop's calendar today, not cancelled. */
  today: number
  /** Waiting on a Service Advisor (`lib/kpis` SA_ACTION_STATUSES). */
  needsAction: number
  /** With the technician, the customer, parts or QC. */
  inProgress: number
  ready: number
  /** Parts that are LOW or OUT (D45). */
  lowStock: number
}

export type SummaryMetric = Exclude<keyof ShopSummaryRow, 'shop'>

export const SUMMARY_METRICS: ReadonlyArray<SummaryMetric> = [
  'today',
  'needsAction',
  'inProgress',
  'ready',
  'lowStock',
]

export interface OwnerSummary {
  /** One row per owned shop that is not suspended, by shop name. */
  rows: ShopSummaryRow[]
  /** Owned shops left out because BayFlow suspended them (D99), by shop name. */
  suspended: MockShop[]
}

/**
 * E-32 `GET /api/v1/me/owner-summary`: one row per shop the person owns, by name. A suspended
 * shop is left out (D99): its staff views are closed (D96), so its figures are not shown. "Today"
 * is each shop's own calendar day at `now` (D38).
 */
export function ownerSummary({
  shops,
  ownedIds,
  bookings,
  parts,
  suspendedIds,
  now,
}: {
  shops: ReadonlyArray<MockShop>
  ownedIds: ReadonlySet<string>
  bookings: ReadonlyArray<MockBooking>
  parts: ReadonlyArray<MockPart>
  suspendedIds: ReadonlySet<string>
  now: Date
}): OwnerSummary {
  const owned = shops.filter((shop) => ownedIds.has(shop.id)).sort(byName)

  const rows = owned
    .filter((shop) => !suspendedIds.has(shop.id))
    .map((shop) => {
      const today = shopDateKey(now, safeTimeZone(shop.timezone))
      const own = bookings.filter((b) => b.shopId === shop.id)
      return {
        shop,
        today: own.filter((b) => b.scheduledDate === today && b.status !== 'CANCELLED').length,
        needsAction: own.filter((b) => SA_ACTION_STATUSES.has(b.status)).length,
        inProgress: own.filter((b) => IN_PROGRESS_STATUSES.has(b.status)).length,
        ready: own.filter((b) => b.status === 'READY_FOR_PICKUP').length,
        lowStock: parts.filter((p) => p.shopId === shop.id && isLowStock(p)).length,
      }
    })

  return { rows, suspended: owned.filter((shop) => suspendedIds.has(shop.id)) }
}

/** Every metric added up over the rows (the "All shops" line). */
export function summaryTotals(rows: ReadonlyArray<ShopSummaryRow>): Record<SummaryMetric, number> {
  const totals = { today: 0, needsAction: 0, inProgress: 0, ready: 0, lowStock: 0 }
  for (const row of rows) {
    for (const metric of SUMMARY_METRICS) totals[metric] += row[metric]
  }
  return totals
}

/** A time zone `Intl` accepts; the shop default otherwise (a bad value must not break the page). */
export function safeTimeZone(timeZone: string | undefined): string {
  if (!timeZone) return DEFAULT_SHOP_TZ
  try {
    new Intl.DateTimeFormat('en', { timeZone })
    return timeZone
  } catch {
    return DEFAULT_SHOP_TZ
  }
}

// --- Create shop (S-03) ---------------------------------------------------------------------------

/** The opening hours a new shop starts with (S-03 default: Mon–Sat 09:00–18:00, Sunday closed). */
export const DEFAULT_WORKING_HOURS: MockShop['working_hours'] = [
  { day: 'Monday', hours: '09:00 - 18:00' },
  { day: 'Tuesday', hours: '09:00 - 18:00' },
  { day: 'Wednesday', hours: '09:00 - 18:00' },
  { day: 'Thursday', hours: '09:00 - 18:00' },
  { day: 'Friday', hours: '09:00 - 18:00' },
  { day: 'Saturday', hours: '09:00 - 18:00' },
  { day: 'Sunday', hours: 'Closed', is_closed: true },
]

/** The default open day, in minutes after midnight (09:00 to 18:00). */
export const DEFAULT_OPEN_MINUTES = 9 * 60
export const DEFAULT_CLOSE_MINUTES = 18 * 60

export interface HoursLine {
  /** "Monday to Saturday", "Sunday". */
  days: string
  /** "09:00 am – 06:00 pm" (the shop profile's format), or `null` when closed. */
  hours: string | null
}

const HOURS = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/

function hoursLabel(hours: string): string {
  const match = HOURS.exec(hours.trim())
  if (!match) return hours
  const [, oh, om, ch, cm] = match.map(Number) as [number, number, number, number, number]
  return `${slotLabel(oh * 60 + om)} – ${slotLabel(ch * 60 + cm)}`
}

/** The week in a few lines: consecutive days with the same hours share one. */
export function weeklyHours(rows: MockShop['working_hours']): HoursLine[] {
  const runs: { days: string[]; hours: string | null }[] = []
  for (const row of rows) {
    const hours = row.is_closed ? null : hoursLabel(row.hours)
    const last = runs[runs.length - 1]
    if (last && last.hours === hours) last.days.push(row.day)
    else runs.push({ days: [row.day], hours })
  }
  return runs.map(({ days, hours }) => ({
    days:
      days.length === 1
        ? days[0]!
        : days.length === 2
          ? `${days[0]} and ${days[1]}`
          : `${days[0]} to ${days[days.length - 1]}`,
    hours,
  }))
}

/** D37: every multiple of 15 from 15 to 240 minutes. */
export const SLOT_DURATIONS: ReadonlyArray<number> = Array.from(
  { length: 16 },
  (_, index) => (index + 1) * 15,
)

export const SLOT_CAPACITY_MIN = 1
export const SLOT_CAPACITY_MAX = 50

/** "45 minutes", "1 hour", "1 hour 15 minutes", "4 hours". */
export function durationLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  const parts: string[] = []
  if (hours > 0) parts.push(hours === 1 ? '1 hour' : `${hours} hours`)
  if (rest > 0 || hours === 0) parts.push(rest === 1 ? '1 minute' : `${rest} minutes`)
  return parts.join(' ')
}

/**
 * Slots in an open day: the booking grid starts at opening time and a slot must end by closing
 * time (the wizard's `freeSlots`, `lib/booking-slots`).
 */
export function slotsPerDay(
  durationMinutes: number,
  open = DEFAULT_OPEN_MINUTES,
  close = DEFAULT_CLOSE_MINUTES,
): number {
  if (!Number.isFinite(durationMinutes) || durationMinutes <= 0 || close <= open) return 0
  return Math.floor((close - open) / durationMinutes)
}

export interface ShopDraft {
  name: string
  address: string
  city: string
  phone: string
  slotDuration: string
  slotCapacity: string
}

export type ShopField = keyof ShopDraft
export type ShopErrors = Partial<Record<ShopField, string>>

/** The order errors are reported and focused in: the order of the form. */
export const SHOP_FIELDS: ReadonlyArray<ShopField> = [
  'name',
  'address',
  'city',
  'phone',
  'slotDuration',
  'slotCapacity',
]

export const SHOP_LIMITS = { name: 120, address: 255, city: 80, phoneMin: 7, phoneMax: 20 } as const

/**
 * The project `Phone` type (spec 03 §1.5): 7–20 characters of digits, spaces and hyphens with an
 * optional leading `+`, holding 7 to 15 digits (E.164).
 */
export function isValidPhone(raw: string): boolean {
  const phone = raw.trim()
  if (phone.length < SHOP_LIMITS.phoneMin || phone.length > SHOP_LIMITS.phoneMax) return false
  if (!/^\+?[0-9 -]+$/.test(phone)) return false
  return /^\d{7,15}$/.test(phone.replace(/[ -]/g, '').replace(/^\+/, ''))
}

/** Whole number of cars per slot, 1–50 (`ShopCreate.slot_capacity`), or `null`. */
export function parseCapacity(raw: string): number | null {
  const value = raw.trim()
  if (!/^\d+$/.test(value)) return null
  const capacity = Number(value)
  return capacity >= SLOT_CAPACITY_MIN && capacity <= SLOT_CAPACITY_MAX ? capacity : null
}

/** S-03 field rules, which are `ShopCreate`'s (spec 03 §4, spec 09 §2.10). Text is trimmed first. */
export function validateShop(draft: ShopDraft): ShopErrors {
  const errors: ShopErrors = {}
  const name = draft.name.trim()
  if (!name) errors.name = 'Enter the name of your shop.'
  else if (name.length > SHOP_LIMITS.name) errors.name = 'Use 120 characters or fewer.'

  const address = draft.address.trim()
  if (!address) errors.address = 'Enter the street address.'
  else if (address.length > SHOP_LIMITS.address) errors.address = 'Use 255 characters or fewer.'

  const city = draft.city.trim()
  if (!city) errors.city = 'Enter the city.'
  else if (city.length > SHOP_LIMITS.city) errors.city = 'Use 80 characters or fewer.'

  if (!draft.phone.trim()) errors.phone = 'Enter a phone number customers can call.'
  else if (!isValidPhone(draft.phone))
    errors.phone = 'Use 7 to 15 digits; spaces, hyphens and a leading + are allowed.'

  if (!SLOT_DURATIONS.includes(Number(draft.slotDuration)))
    errors.slotDuration = 'Choose a slot length.'

  if (parseCapacity(draft.slotCapacity) === null)
    errors.slotCapacity = `Enter a whole number from ${SLOT_CAPACITY_MIN} to ${SLOT_CAPACITY_MAX}.`
  return errors
}

/**
 * Spec 03 §4.9: a slug that is already taken gets a `-2`, `-3` … suffix, never an error. A new
 * shop must never take the id of an existing one (that would replace it).
 */
export function availableSlug(
  slug: string,
  shops: ReadonlyArray<Pick<MockShop, 'id' | 'slug'>>,
): string {
  const taken = new Set(shops.flatMap((shop) => [shop.id, shop.slug]))
  const free = (candidate: string) => !taken.has(candidate) && !taken.has(`shop-${candidate}`)
  if (free(slug)) return slug
  let suffix = 2
  while (!free(`${slug}-${suffix}`)) suffix += 1
  return `${slug}-${suffix}`
}

/**
 * The new shop's slug: its name in lower-case kebab case (a timestamp when the name has no letters
 * or digits), with a suffix when that slug is taken. The shop's id is `shop-<slug>`.
 */
export function newShopSlug(
  name: string,
  shops: ReadonlyArray<Pick<MockShop, 'id' | 'slug'>>,
): string {
  const slug =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || `shop-${Date.now()}`
  return availableSlug(slug, shops)
}

/** "1 shop", "2 shops". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

/** "a", "a and b", "a, b and c". */
export function listOf(items: ReadonlyArray<string>): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}
