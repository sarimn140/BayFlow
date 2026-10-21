import type { CallRead } from './types'

/** `m:ss` for call durations (spec 05 §3.8). */
export function formatDuration(seconds: number | null | undefined): string {
  const total = Math.max(0, Math.round(seconds ?? 0))
  const minutes = Math.floor(total / 60)
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

/** Seconds since an ISO instant, never negative. */
export function secondsSince(iso: string | null | undefined, now: number): number {
  if (!iso) return 0
  return Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
}

const MISSED: Record<string, string> = {
  NO_ANSWER: 'no answer',
  DECLINED: 'declined',
  CALLER_HUNG_UP: 'caller hung up',
}

/** The outcome line of a call log entry (spec 05 §3.8): "Missed (no answer) → AI Front Desk · 1:58". */
export function outcomeOf(call: CallRead): string {
  if (call.status === 'RINGING') return 'Ringing'
  if (call.status === 'CONNECTED') return 'In progress'
  if (call.status === 'ENDED') return `Connected · ${formatDuration(call.duration_seconds)}`
  const missed = `Missed (${MISSED[call.missed_reason ?? ''] ?? 'no answer'})`
  if (!call.ai) return missed
  if (call.ai.status === 'FAILED') return `${missed} → AI unavailable`
  if (call.ai.status === 'CONNECTING') return `${missed} → connecting the AI Front Desk`
  if (call.ai.status === 'ACTIVE') return `${missed} → AI Front Desk now`
  return `${missed} → AI Front Desk · ${formatDuration(call.ai.duration_seconds)}`
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '?'
}
