import type { MockBooking } from '@/lib/mock-data'

/**
 * A sortable key for a mock booking's slot: `scheduledDate` plus `scheduledTime` ("02:00 pm")
 * turned into 24-hour time, so 2 pm sorts after 10 am. The API sorts on `slot_start` itself.
 */
export function slotSortKey(b: Pick<MockBooking, 'scheduledDate' | 'scheduledTime'>): string {
  const match = /^(\d{1,2}):(\d{2})\s*([ap]m)$/i.exec(b.scheduledTime.trim())
  if (!match) return `${b.scheduledDate} ${b.scheduledTime}`
  const [, h, m, meridiem] = match
  const hours = (Number(h) % 12) + (meridiem!.toLowerCase() === 'pm' ? 12 : 0)
  return `${b.scheduledDate} ${String(hours).padStart(2, '0')}:${m}`
}
