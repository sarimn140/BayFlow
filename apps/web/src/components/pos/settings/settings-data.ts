import { WEEKDAYS, minutesInZone, slotLabel } from '@/lib/booking-slots'
import { DEFAULT_SHOP_TZ, shopDateKey } from '@/lib/format'
import type { MockBooking, MockShop } from '@/lib/mock-data'

/**
 * O-04 Shop settings (spec 10): the rules of `ShopUpdate` and `WorkingHoursWrite` (spec 03,
 * spec 09 §2.10) and the D37 slot grid, so the forms never accept what the API refuses.
 */

export type Weekday = (typeof WEEKDAYS)[number]

/* ------------------------------------------------------------------ Shop profile ----------- */

export const SHOP_NAME_MAX = 120
export const ADDRESS_MAX = 255
export const CITY_MAX = 80
/** The project `Phone` type: 7–20 digits, spaces or hyphens, with an optional leading `+`. */
export const PHONE_PATTERN = /^\+?[0-9 -]{7,20}$/

export interface ProfileDraft {
  name: string
  address: string
  city: string
  phone: string
}
export type ProfileField = keyof ProfileDraft
export type ProfileErrors = Partial<Record<ProfileField, string>>
export const PROFILE_FIELDS: ReadonlyArray<ProfileField> = ['name', 'address', 'city', 'phone']

export function profileFromShop(shop: MockShop): ProfileDraft {
  return { name: shop.name, address: shop.address, city: shop.city, phone: shop.phone }
}

export function normaliseProfile(draft: ProfileDraft): ProfileDraft {
  return {
    name: draft.name.trim(),
    address: draft.address.trim(),
    city: draft.city.trim(),
    phone: draft.phone.trim(),
  }
}

export function sameProfile(a: ProfileDraft, b: ProfileDraft): boolean {
  return PROFILE_FIELDS.every((field) => a[field] === b[field])
}

export function validateProfile(draft: ProfileDraft): ProfileErrors {
  const errors: ProfileErrors = {}
  const { name, address, city, phone } = normaliseProfile(draft)
  if (!name) errors.name = 'Enter the shop name.'
  else if (name.length > SHOP_NAME_MAX) errors.name = 'Use 120 characters or fewer.'
  if (!address) errors.address = 'Enter the street address.'
  else if (address.length > ADDRESS_MAX) errors.address = 'Use 255 characters or fewer.'
  if (!city) errors.city = 'Enter the city.'
  else if (city.length > CITY_MAX) errors.city = 'Use 80 characters or fewer.'
  if (!phone) errors.phone = 'Enter a phone number customers can call.'
  else if (!PHONE_PATTERN.test(phone))
    errors.phone = 'Use 7 to 20 digits, spaces or hyphens, with an optional leading +.'
  return errors
}

/* ------------------------------------------------------------------ Slots and capacity ----- */

/** Every multiple of 15 from 15 to 240 minutes (D37). */
export const SLOT_LENGTHS: ReadonlyArray<number> = Array.from(
  { length: 16 },
  (_, i) => (i + 1) * 15,
)
export const CAPACITY_MIN = 1
export const CAPACITY_MAX = 50

export interface SlotsDraft {
  duration: string
  capacity: string
}
export type SlotsField = keyof SlotsDraft
export type SlotsErrors = Partial<Record<SlotsField, string>>
export const SLOTS_FIELDS: ReadonlyArray<SlotsField> = ['duration', 'capacity']

export function slotsFromShop(shop: MockShop): SlotsDraft {
  return { duration: String(shop.slot_duration_minutes), capacity: String(shop.slot_capacity) }
}

export function sameSlots(a: SlotsDraft, b: SlotsDraft): boolean {
  return Number(a.duration) === Number(b.duration) && a.capacity.trim() === b.capacity.trim()
}

/** "15 minutes", "1 hour", "1 hour 30 minutes", "4 hours". */
export function slotLengthLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  const parts = [
    hours ? `${hours} ${hours === 1 ? 'hour' : 'hours'}` : '',
    rest ? `${rest} minutes` : '',
  ]
  return parts.filter(Boolean).join(' ')
}

/**
 * Field errors for the slots form. A new slot length must be a multiple of 15 from 15 to 240 and
 * keep the saved opening hours on its grid (422 `hours_not_on_grid`); the caller checks the
 * upcoming bookings first (409 `CONFLICT`). An unchanged length is never re-checked.
 */
export function validateSlots(
  draft: SlotsDraft,
  shop: Pick<MockShop, 'slot_duration_minutes' | 'working_hours'>,
): SlotsErrors {
  const errors: SlotsErrors = {}
  const duration = Number(draft.duration)
  if (duration !== shop.slot_duration_minutes) {
    if (!SLOT_LENGTHS.includes(duration)) errors.duration = 'Choose a slot length.'
    else if (!hoursFitGrid(shop.working_hours, duration))
      errors.duration = "Your working hours don't fit the new slot length — adjust them first."
  }

  const capacity = draft.capacity.trim()
  const value = /^\d+$/.test(capacity) ? Number(capacity) : NaN
  if (!capacity) errors.capacity = 'Enter how many cars you can take in one slot.'
  else if (!Number.isInteger(value) || value < CAPACITY_MIN || value > CAPACITY_MAX)
    errors.capacity = 'Enter a whole number from 1 to 50.'
  return errors
}

/** "Asia/Karachi (PKT, UTC+5)" for the default zone (D38); other zones as their IANA name. */
export function timeZoneLabel(timeZone: string): string {
  return timeZone === DEFAULT_SHOP_TZ ? `${DEFAULT_SHOP_TZ} (PKT, UTC+5)` : timeZone
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

const SLOT_TIME = /^(\d{1,2}):(\d{2})\s*(am|pm)$/i

/** Minutes after midnight of a stored slot time ("10:00 am" → 600), or `null`. */
export function slotTimeMinutes(label: string): number | null {
  const match = SLOT_TIME.exec(label.trim())
  if (!match) return null
  const hour = Number(match[1]) % 12
  const minute = Number(match[2])
  if (minute > 59) return null
  return (match[3]!.toLowerCase() === 'pm' ? hour + 12 : hour) * 60 + minute
}

/**
 * `has_future_bookings` (E-22, D37): bookings that are not cancelled and whose slot starts after
 * `now`, in the shop's time zone. While there are any, the slot length can't change.
 */
export function upcomingBookingCount(
  bookings: ReadonlyArray<Pick<MockBooking, 'status' | 'scheduledDate' | 'scheduledTime'>>,
  now: Date,
  timeZone: string,
): number {
  const today = shopDateKey(now, timeZone)
  const minutesNow = minutesInZone(now, timeZone)
  return bookings.filter((b) => {
    if (b.status === 'CANCELLED') return false
    if (b.scheduledDate > today) return true
    if (b.scheduledDate < today) return false
    const start = slotTimeMinutes(b.scheduledTime)
    return start !== null && start > minutesNow
  }).length
}

/* ------------------------------------------------------------------ Opening hours ---------- */

/** One weekday of the hours form: times are "HH:MM" (24 h) or "" when not chosen. */
export interface DayHours {
  day: Weekday
  open: boolean
  opens: string
  closes: string
}
export type HoursErrors = Partial<Record<Weekday, string>>

const STORED_HOURS = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/
const MINUTES_PER_DAY = 24 * 60

/** "09:00" → 540; `null` when it isn't a time. */
export function timeToMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value)
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 24 || minutes > 59) return null
  const total = hours * 60 + minutes
  return total <= MINUTES_PER_DAY ? total : null
}

/** 540 → "09:00". */
export function minutesToTime(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

/** The stored "09:00 - 18:00" as two "HH:MM" values ("" when the text isn't a time range). */
function parseStoredHours(hours: string): { opens: string; closes: string } {
  const match = STORED_HOURS.exec(hours.trim())
  if (!match) return { opens: '', closes: '' }
  const opens = timeToMinutes(`${match[1]}:${match[2]}`)
  const closes = timeToMinutes(`${match[3]}:${match[4]}`)
  return {
    opens: opens === null ? '' : minutesToTime(opens),
    closes: closes === null ? '' : minutesToTime(closes),
  }
}

/** Seven rows, Monday first (glossary weekday 0 = Monday); a missing day is closed. */
export function hoursFromShop(shop: Pick<MockShop, 'working_hours'>): DayHours[] {
  return WEEKDAYS.map((day) => {
    const row = shop.working_hours.find((wh) => wh.day === day)
    if (!row || row.is_closed) return { day, open: false, opens: '', closes: '' }
    return { day, open: true, ...parseStoredHours(row.hours) }
  })
}

/** The stored shape the booking wizard reads (`lib/booking-slots`): "09:00 - 18:00" or closed. */
export function hoursToShop(rows: ReadonlyArray<DayHours>): MockShop['working_hours'] {
  return rows.map((row) =>
    row.open
      ? { day: row.day, hours: `${row.opens} - ${row.closes}` }
      : { day: row.day, hours: 'Closed', is_closed: true },
  )
}

export function sameHours(a: ReadonlyArray<DayHours>, b: ReadonlyArray<DayHours>): boolean {
  return (
    a.length === b.length &&
    a.every((row, i) => {
      const other = b[i]
      if (!other || row.day !== other.day || row.open !== other.open) return false
      return !row.open || (row.opens === other.opens && row.closes === other.closes)
    })
  )
}

const onGrid = (minutes: number, slot: number) => minutes % slot === 0

/** Errors per open day: both times, on the slot grid (`not_on_grid`), close after open. */
export function validateHours(rows: ReadonlyArray<DayHours>, slotMinutes: number): HoursErrors {
  const errors: HoursErrors = {}
  for (const row of rows) {
    if (!row.open) continue
    const opens = timeToMinutes(row.opens)
    const closes = timeToMinutes(row.closes)
    if (opens === null || closes === null) errors[row.day] = 'Choose an opening and a closing time.'
    else if (!onGrid(opens, slotMinutes) || !onGrid(closes, slotMinutes))
      errors[row.day] = `Use times on your ${slotMinutes}-minute slot grid.`
    else if (closes <= opens) errors[row.day] = 'Closing time must be after opening time.'
  }
  return errors
}

/** Whether every open day's stored hours lie on the grid of `slotMinutes` (D37). */
export function hoursFitGrid(workingHours: MockShop['working_hours'], slotMinutes: number) {
  return (
    Object.keys(validateHours(hoursFromShop({ working_hours: workingHours }), slotMinutes))
      .length === 0
  )
}

export interface TimeOption {
  value: string
  label: string
}

/**
 * The grid times a select offers (D37: the grid starts at local midnight): opening times from
 * 00:00, closing times from one slot after it, both up to the last grid time before midnight. A
 * current value that is off the grid stays in the list, so the select shows it and validation
 * can flag it.
 */
export function timeOptions(
  slotMinutes: number,
  current: string,
  kind: 'opens' | 'closes' = 'opens',
): TimeOption[] {
  const minutes: number[] = []
  for (let m = kind === 'closes' ? slotMinutes : 0; m < MINUTES_PER_DAY; m += slotMinutes)
    minutes.push(m)
  const extra = timeToMinutes(current)
  if (extra !== null && !minutes.includes(extra)) minutes.push(extra)
  return minutes
    .sort((a, b) => a - b)
    .map((m) => ({ value: minutesToTime(m), label: slotLabel(m % MINUTES_PER_DAY) }))
}

/**
 * Times for a day that is being opened: Monday's when Monday is open and valid, else the first
 * open day's, else 09:00–18:00 moved onto the grid.
 */
export function defaultHours(
  rows: ReadonlyArray<DayHours>,
  slotMinutes: number,
): { opens: string; closes: string } {
  const valid = rows.find(
    (row) => row.open && Object.keys(validateHours([row], slotMinutes)).length === 0,
  )
  if (valid) return { opens: valid.opens, closes: valid.closes }
  const opens = Math.ceil((9 * 60) / slotMinutes) * slotMinutes
  let closes = Math.floor((18 * 60) / slotMinutes) * slotMinutes
  if (closes <= opens) closes = Math.min(opens + slotMinutes, MINUTES_PER_DAY - slotMinutes)
  return { opens: minutesToTime(opens), closes: minutesToTime(closes) }
}

/** "Copy Monday": every other open day takes Monday's times; closed days stay closed. */
export function copyMondayToOpenDays(rows: ReadonlyArray<DayHours>): DayHours[] {
  const monday = rows[0]
  if (!monday?.open) return [...rows]
  return rows.map((row, i) =>
    i > 0 && row.open ? { ...row, opens: monday.opens, closes: monday.closes } : row,
  )
}
