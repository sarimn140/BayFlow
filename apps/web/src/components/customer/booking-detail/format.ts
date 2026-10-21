import { weekdayOf } from '@/lib/booking-slots'
import { formatDate, formatTime, shopDateKey } from '@/lib/format'
import type { MockShop } from '@/lib/mock-data'

const DATE_KEY = /^\d{4}-\d{2}-\d{2}$/

/** "9:00 am" from a stored slot time such as "09:00 am" (the wizard keeps a leading zero). */
function slotTime(time: string): string {
  return time.replace(/^0(?=\d)/, '')
}

/**
 * A booked slot as "Fri, 9 Oct 2026" and "11:00 am" (shop time). The date is a shop-local
 * calendar key, so it is formatted at noon UTC, where no timezone can move it to another day.
 */
export function bookingSlot(dateKey: string, time: string): { date: string; time: string } {
  return {
    date: DATE_KEY.test(dateKey) ? formatDate(`${dateKey}T12:00:00Z`, 'UTC') : dateKey,
    time: slotTime(time),
  }
}

const shortDay = new Map<string, Intl.DateTimeFormat>()

/** "Fri, 9 Oct · 11:15 am" in the shop's timezone: event times in the progress timeline. */
export function formatShortDateTime(iso: string, timeZone: string): string {
  let day = shortDay.get(timeZone)
  if (!day) {
    day = new Intl.DateTimeFormat('en-PK', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      timeZone,
    })
    shortDay.set(timeZone, day)
  }
  return `${day.format(new Date(iso))} · ${formatTime(iso, timeZone)}`
}

/** The shop's opening hours today (shop time), or null when its week has no row for today. */
export function todaysHours(
  shop: Pick<MockShop, 'timezone' | 'working_hours'>,
  nowIso: string,
): { closed: boolean; label: string } | null {
  const today = weekdayOf(shopDateKey(nowIso, shop.timezone))
  const row = shop.working_hours.find((wh) => wh.day === today)
  if (!row) return null
  if (row.is_closed) return { closed: true, label: 'Closed today' }
  return { closed: false, label: `Open today, ${row.hours.replace(/\s*-\s*/, ' – ')}` }
}

/** `tel:` link for a display number such as "+92 42 35789011". */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}
