import type { components } from '@/lib/api/schema'

/** API shapes of the calls module (spec 05 §8.3), from the generated schema only (glossary §13). */
export type CallRead = components['schemas']['CallRead']
/** Staff lists carry two extra fields (spec 05 §8.3) that the list schema doesn't declare. */
export type StaffCallRead = CallRead & { has_summary?: boolean; open_task_count?: number }
export type CallStartRead = components['schemas']['CallStartRead']
export type CallConnection = components['schemas']['CallConnection']
export type CallDetailRead = components['schemas']['CallDetailRead']
export type TaskRead = components['schemas']['TaskRead']
export type TaskKind = components['schemas']['TaskKind']
export type MeRead = components['schemas']['MeRead']

/** Who is acting: the booking's customer (`/me` routes) or staff of a shop (SA / Owner). */
export type CallAudience = { kind: 'customer' } | { kind: 'staff'; shopId: string }

/**
 * The client call states (spec 05 §9.1):
 * idle → preparing (microphone) → outgoing_ringing → connected → ended
 * idle → incoming_ringing → connecting → connected → ended
 * customers only: outgoing_ringing → ai_connecting → ai_active → ended
 */
export type CallPhase =
  | 'preparing'
  | 'outgoing_ringing'
  | 'connecting'
  | 'connected'
  | 'ai_connecting'
  | 'ai_active'
  | 'ended'
