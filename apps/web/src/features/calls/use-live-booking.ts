'use client'

/**
 * The API's own ids for a booking shown on a (mock) screen: the booking id, and for staff the
 * shop id from `GET /api/v1/me` (matched by slug). See `live-booking.ts` for the bridge.
 */
import { useQuery } from '@tanstack/react-query'

import { ApiError } from '@/lib/api/errors'

import { findMyBookingId, findShopBookingId, getMe } from './api'
import { CALLING_ENABLED } from './config'
import { liveReference } from './live-booking'
import type { CallAudience } from './types'

export type LiveBooking =
  | { state: 'loading' }
  | { state: 'unavailable' } // no live twin, or not this person's booking in the API
  | { state: 'signed-out' } // the API session is missing (signed in with a mock-only password)
  | { state: 'ready'; bookingId: string; reference: string; audience: CallAudience }

export type LiveBookingTarget =
  | { audience: 'customer'; reference: string }
  | { audience: 'staff'; reference: string; shopSlug: string }

const STAFF_ROLES = new Set(['SERVICE_ADVISOR', 'OWNER'])

async function resolve(target: LiveBookingTarget): Promise<LiveBooking> {
  const reference = liveReference(target.reference)
  if (!reference) return { state: 'unavailable' }
  try {
    if (target.audience === 'customer') {
      const bookingId = await findMyBookingId(reference)
      return bookingId
        ? { state: 'ready', bookingId, reference, audience: { kind: 'customer' } }
        : { state: 'unavailable' }
    }
    const me = await getMe()
    if (!me) return { state: 'signed-out' }
    const membership = me.memberships.find(
      (m) => m.shop_slug === target.shopSlug && STAFF_ROLES.has(m.role),
    )
    if (!membership) return { state: 'unavailable' }
    const bookingId = await findShopBookingId(membership.shop_id, reference)
    return bookingId
      ? {
          state: 'ready',
          bookingId,
          reference,
          audience: { kind: 'staff', shopId: membership.shop_id },
        }
      : { state: 'unavailable' }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return { state: 'signed-out' }
    return { state: 'unavailable' }
  }
}

export function useLiveBooking(target: LiveBookingTarget): LiveBooking {
  const shopSlug = target.audience === 'staff' ? target.shopSlug : ''
  const query = useQuery({
    queryKey: ['calls', 'live-booking', target.audience, target.reference, shopSlug],
    queryFn: () => resolve(target),
    enabled: CALLING_ENABLED,
    staleTime: 60_000,
    retry: false,
  })
  return query.data ?? { state: 'loading' }
}

/** The API's shop id for a POS shop page (by the mock shop's slug), for SA / Owner. */
export function useLiveShopId(shopSlug: string | undefined) {
  return useQuery({
    queryKey: ['calls', 'live-shop', shopSlug],
    queryFn: async () => {
      const me = await getMe()
      if (!me) return { state: 'signed-out' as const }
      const membership = me.memberships.find(
        (m) => m.shop_slug === shopSlug && STAFF_ROLES.has(m.role),
      )
      return membership
        ? { state: 'ready' as const, shopId: membership.shop_id, timezone: 'Asia/Karachi' }
        : { state: 'unavailable' as const }
    },
    enabled: CALLING_ENABLED && Boolean(shopSlug),
    staleTime: 60_000,
    retry: false,
  })
}
