import { formatDate } from '@/lib/format'
import type { MockBooking } from '@/lib/mock-data'

const DATE_KEY = /^\d{4}-\d{2}-\d{2}$/

/**
 * A booking's slot as "Fri, 9 Oct 2026" and "11:00 am" (shop time). The date is a shop-local
 * calendar key, so it is formatted at noon UTC, where no timezone can move it to another day; the
 * stored time loses its leading zero ("09:00 am" → "9:00 am").
 */
export function slotParts(booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>): {
  date: string
  time: string
} {
  return {
    date: DATE_KEY.test(booking.scheduledDate)
      ? formatDate(`${booking.scheduledDate}T12:00:00Z`, 'UTC')
      : booking.scheduledDate,
    time: booking.scheduledTime.replace(/^0(?=\d)/, ''),
  }
}

/** "Fri, 9 Oct 2026 · 11:00 am". */
export function slotLabel(booking: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>): string {
  const { date, time } = slotParts(booking)
  return `${date} · ${time}`
}

/** "2021 Toyota Corolla Altis Grande". */
export function vehicleLabel(
  booking: Pick<MockBooking, 'vehicleYear' | 'vehicleMake' | 'vehicleModel'>,
): string {
  return `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
}
