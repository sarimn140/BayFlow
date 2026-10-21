/**
 * Every call endpoint the web uses, wrapped once (spec 09 §2.6). All go through the shared
 * same-origin client, so the httpOnly `bf_session` cookie travels with them (D8).
 */
import { api, unwrap } from '@/lib/api/client'

import type { CallAudience, CallRead, CallStartRead, MeRead, TaskKind } from './types'

/** `unwrap`, plus a guarantee the body is there (every call route answers with JSON). */
async function send<T>(call: Parameters<typeof unwrap<T>>[0]): Promise<NonNullable<T>> {
  const data = await unwrap(call)
  if (data == null) throw new Error('The server sent an empty response')
  return data
}

export async function getMe(): Promise<MeRead | null> {
  const result = await api.GET('/api/v1/me')
  return result.response.ok && result.data ? result.data : null
}

export async function getRealtimeTicket(): Promise<string> {
  const data = await send(api.GET('/api/v1/realtime/ticket'))
  return data.ticket
}

export function startCall(audience: CallAudience, bookingId: string): Promise<CallStartRead> {
  if (audience.kind === 'customer') {
    return send(
      api.POST('/api/v1/me/bookings/{booking_id}/calls', {
        params: { path: { booking_id: bookingId } },
      }),
    )
  }
  return send(
    api.POST('/api/v1/shops/{shop_id}/bookings/{booking_id}/calls', {
      params: { path: { shop_id: audience.shopId, booking_id: bookingId } },
    }),
  )
}

export function acceptCall(audience: CallAudience, callId: string): Promise<CallStartRead> {
  if (audience.kind === 'customer') {
    return send(
      api.POST('/api/v1/me/calls/{call_id}/accept', { params: { path: { call_id: callId } } }),
    )
  }
  return send(
    api.POST('/api/v1/shops/{shop_id}/calls/{call_id}/accept', {
      params: { path: { shop_id: audience.shopId, call_id: callId } },
    }),
  )
}

export function declineCall(audience: CallAudience, callId: string): Promise<CallRead> {
  if (audience.kind === 'customer') {
    return send(
      api.POST('/api/v1/me/calls/{call_id}/decline', { params: { path: { call_id: callId } } }),
    )
  }
  return send(
    api.POST('/api/v1/shops/{shop_id}/calls/{call_id}/decline', {
      params: { path: { shop_id: audience.shopId, call_id: callId } },
    }),
  )
}

export function endCall(audience: CallAudience, callId: string): Promise<CallRead> {
  if (audience.kind === 'customer') {
    return send(
      api.POST('/api/v1/me/calls/{call_id}/end', { params: { path: { call_id: callId } } }),
    )
  }
  return send(
    api.POST('/api/v1/shops/{shop_id}/calls/{call_id}/end', {
      params: { path: { shop_id: audience.shopId, call_id: callId } },
    }),
  )
}

export function listBookingCalls(audience: CallAudience, bookingId: string) {
  if (audience.kind === 'customer') {
    return send(
      api.GET('/api/v1/me/bookings/{booking_id}/calls', {
        params: { path: { booking_id: bookingId }, query: { limit: 20 } },
      }),
    )
  }
  return send(
    api.GET('/api/v1/shops/{shop_id}/bookings/{booking_id}/calls', {
      params: { path: { shop_id: audience.shopId, booking_id: bookingId }, query: { limit: 20 } },
    }),
  )
}

export function getCallDetail(shopId: string, callId: string) {
  return send(
    api.GET('/api/v1/shops/{shop_id}/calls/{call_id}', {
      params: { path: { shop_id: shopId, call_id: callId } },
    }),
  )
}

export function listTasks(shopId: string, status: 'OPEN' | 'DONE', kind?: TaskKind[]) {
  return send(
    api.GET('/api/v1/shops/{shop_id}/tasks', {
      params: { path: { shop_id: shopId }, query: { status, kind, limit: 50 } },
    }),
  )
}

export function markTaskDone(shopId: string, taskId: string, note?: string) {
  return send(
    api.POST('/api/v1/shops/{shop_id}/tasks/{task_id}/mark-done', {
      params: { path: { shop_id: shopId, task_id: taskId } },
      body: note ? { note } : {},
    }),
  )
}

export function listShopCalls(shopId: string) {
  return send(
    api.GET('/api/v1/shops/{shop_id}/calls', {
      params: { path: { shop_id: shopId }, query: { limit: 50 } },
    }),
  )
}

export async function findMyBookingId(reference: string): Promise<string | null> {
  const page = await send(api.GET('/api/v1/me/bookings', { params: { query: { limit: 100 } } }))
  return page.items.find((item) => item.reference === reference)?.id ?? null
}

export async function findShopBookingId(shopId: string, reference: string): Promise<string | null> {
  const page = await send(
    api.GET('/api/v1/shops/{shop_id}/bookings', {
      params: { path: { shop_id: shopId }, query: { q: reference, limit: 10 } },
    }),
  )
  return page.items.find((item) => item.reference === reference)?.id ?? null
}
