import { estimateDecisionOf, type EstimateDecision } from '@/components/customer/estimate-decision'
import { minutesInZone } from '@/lib/booking-slots'
import { DEFAULT_SHOP_TZ, shopDateKey } from '@/lib/format'
import type { MockBooking, MockShop } from '@/lib/mock-data'
import { slotSortKey } from '@/lib/slot'
import type { BookingStatus } from '@/lib/status'

/**
 * C-01 My bookings (spec 10): what each card shows and the order of the list, worked out from the
 * mock store with the API's rules (E-11 `CustomerBookingSummary`: `allowed_actions`,
 * `estimate_summary`), so the screen already behaves the way the live endpoint will.
 */

/** The decisions the customer takes on C-02 that the list points to (spec 10 C-01 Layout). */
export type CustomerAction = 'approve-estimate' | 'complete'

/**
 * The action `allowed_actions` lists for the booking's customer (spec 08): approve the estimate
 * while it waits for them, confirm the pick-up once the car is ready. None while the shop is
 * suspended (D96: the customer can only read the booking and cancel it).
 */
export function customerActionOf(
  status: BookingStatus,
  shopSuspended: boolean,
): CustomerAction | null {
  if (shopSuspended) return null
  if (status === 'AWAITING_CUSTOMER') return 'approve-estimate'
  if (status === 'READY_FOR_PICKUP') return 'complete'
  return null
}

/**
 * Now in the shop's timezone as "YYYY-MM-DD HH:MM", the format of `slotSortKey`, so a slot can be
 * compared with it. Null when the timezone is not one `Intl` knows.
 */
export function shopNowKey(nowIso: string, timeZone: string): string | null {
  try {
    const now = new Date(nowIso)
    const minutes = minutesInZone(now, timeZone)
    const hours = String(Math.floor(minutes / 60)).padStart(2, '0')
    return `${shopDateKey(now, timeZone)} ${hours}:${String(minutes % 60).padStart(2, '0')}`
  } catch {
    return null
  }
}

/** One card of the list: the booking plus what the card needs to know about it. */
export interface BookingListItem {
  booking: MockBooking
  /** The shop's current record, when it still exists. */
  shop: MockShop | undefined
  shopName: string
  /** D96: the shop is suspended, so the customer can only read the booking and cancel it. */
  shopSuspended: boolean
  action: CustomerAction | null
  estimate: EstimateDecision | null
  /** The slot has not started yet (shop time). */
  upcoming: boolean
}

export interface ListContext {
  shops: ReadonlyArray<MockShop>
  /** Suspended shops by shop id (`getShopSuspensions`). */
  suspensions: Readonly<Record<string, unknown>>
  /** `useNowMinute()`: null until the page has mounted. */
  nowIso: string | null
}

export function toListItems(
  bookings: ReadonlyArray<MockBooking>,
  { shops, suspensions, nowIso }: ListContext,
): BookingListItem[] {
  // "Now" once per shop timezone, not once per booking.
  const nowKeys = new Map<string, string | null>()
  const nowKeyIn = (timeZone: string) => {
    if (!nowKeys.has(timeZone)) nowKeys.set(timeZone, nowIso ? shopNowKey(nowIso, timeZone) : null)
    return nowKeys.get(timeZone) ?? null
  }
  return bookings.map((booking) => {
    const shop = shops.find((s) => s.id === booking.shopId || s.slug === booking.shopSlug)
    const shopSuspended = Boolean(suspensions[booking.shopId])
    const nowKey = nowKeyIn(shop?.timezone ?? DEFAULT_SHOP_TZ)
    return {
      booking,
      shop,
      shopName: shop?.name ?? booking.shopName,
      shopSuspended,
      action: customerActionOf(booking.status, shopSuspended),
      estimate: estimateDecisionOf(booking),
      upcoming: nowKey !== null && slotSortKey(booking) > nowKey,
    }
  })
}

/** The suspended shops (D96) the customer has active bookings at, each named once. */
export function suspendedShopNames(items: ReadonlyArray<BookingListItem>): string[] {
  return Array.from(new Set(items.filter((i) => i.shopSuspended).map((i) => i.shopName)))
}

/** "A", "A and B", "A, B and C". */
export function joinNames(names: ReadonlyArray<string>): string {
  if (names.length < 2) return names[0] ?? ''
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** Milliseconds of an ISO timestamp; 0 when it doesn't parse, so it sorts last. */
function timeOf(iso: string): number {
  const time = Date.parse(iso)
  return Number.isNaN(time) ? 0 : time
}

/**
 * Active tab order (spec 10 C-01): bookings waiting on the customer first, then upcoming slots,
 * soonest first, then the rest by their last update, newest first.
 */
export function compareActive(a: BookingListItem, b: BookingListItem): number {
  if (Boolean(a.action) !== Boolean(b.action)) return a.action ? -1 : 1
  if (a.upcoming !== b.upcoming) return a.upcoming ? -1 : 1
  if (a.upcoming) {
    const bySlot = slotSortKey(a.booking).localeCompare(slotSortKey(b.booking))
    if (bySlot !== 0) return bySlot
  }
  return timeOf(b.booking.updatedAt) - timeOf(a.booking.updatedAt)
}

/** Past tab order: the most recently closed booking first, then the latest slot. */
export function comparePast(a: BookingListItem, b: BookingListItem): number {
  return (
    timeOf(b.booking.updatedAt) - timeOf(a.booking.updatedAt) ||
    slotSortKey(b.booking).localeCompare(slotSortKey(a.booking))
  )
}
