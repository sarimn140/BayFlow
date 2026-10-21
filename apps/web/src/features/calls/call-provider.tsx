'use client'

/**
 * `CallProvider` (spec 05 §9.1): mounted once in the customer and POS shells, so moving between
 * pages keeps a call alive. It holds the active call and the ringing calls, listens to
 * `call.incoming`, `call.updated` and `task.created` on the shared socket, joins the LiveKit room
 * once a token exists, and renders the incoming-call panel and the in-call bar.
 *
 * The API owns call state; this provider only follows it (responses and pushes) and asks the API
 * to change it. Renders nothing extra when calling is not configured.
 */
import { useQueryClient } from '@tanstack/react-query'
import { LiveKitRoom, RoomAudioRenderer, useRoomContext } from '@livekit/components-react'
import { RoomEvent } from 'livekit-client'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { toast } from 'sonner'

import { ApiError } from '@/lib/api/errors'

import { acceptCall, declineCall, endCall, startCall } from './api'
import { CALLING_ENABLED } from './config'
import { formatDuration } from './format'
import { InCallBar } from './in-call-bar'
import { IncomingCallPanel } from './incoming-call-panel'
import { useRealtime, type RealtimeMessage } from './realtime'
import { startRinging, stopRinging } from './ringtone'
import type {
  CallAudience,
  CallConnection,
  CallPhase,
  CallRead,
  CallStartRead,
  TaskRead,
} from './types'

export interface ActiveCall {
  call: CallRead
  audience: CallAudience
  phase: CallPhase
  connection: CallConnection | null
  /** Who the person is talking to, e.g. "Lahore Auto Care" or "Ayesha Khan". */
  counterpart: string
  /** The outcome shown when the call has ended. */
  endedNote?: string
}

export interface IncomingCall {
  call: CallRead
  audience: CallAudience
}

interface CallsContextValue {
  enabled: boolean
  active: ActiveCall | null
  incoming: IncomingCall[]
  busy: boolean
  start: (audience: CallAudience, bookingId: string, counterpart: string) => Promise<void>
  accept: (item: IncomingCall) => Promise<void>
  decline: (item: IncomingCall) => Promise<void>
  hangUp: () => Promise<void>
}

const CallsContext = createContext<CallsContextValue | null>(null)

export function useCalls(): CallsContextValue {
  const value = useContext(CallsContext)
  if (!value) throw new Error('useCalls must be used inside <CallProvider>')
  return value
}

/** `useCalls` for components that may also render outside the provider (e.g. in tests). */
export function useOptionalCalls(): CallsContextValue | null {
  return useContext(CallsContext)
}

const MAX_INCOMING = 3 // D78: the panel stacks up to 3 calls

/** Spec 05 §9.2 microphone check: ask once, then release the device. */
async function microphoneReady(): Promise<boolean> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((track) => track.stop())
    return true
  } catch {
    toast.error('Microphone access is blocked', {
      description: 'Allow the microphone for this site in your browser settings, then try again.',
    })
    return false
  }
}

function audienceOf(call: CallRead): CallAudience {
  return call.direction === 'CUSTOMER_TO_SHOP'
    ? { kind: 'staff', shopId: call.shop_id }
    : { kind: 'customer' }
}

/** The phase a pushed `CallRead` puts an active call in (spec 05 §9.1). */
function phaseFor(call: CallRead, current: CallPhase): CallPhase {
  if (call.status === 'RINGING') return current === 'connecting' ? 'connecting' : 'outgoing_ringing'
  if (call.status === 'CONNECTED') return 'connected'
  if (call.status === 'MISSED' && call.ai) {
    if (call.ai.status === 'CONNECTING') return 'ai_connecting'
    if (call.ai.status === 'ACTIVE') return 'ai_active'
  }
  return 'ended'
}

function endedNoteFor(call: CallRead, audience: CallAudience): string {
  if (call.status === 'ENDED') return `Call ended · ${formatDuration(call.duration_seconds)}`
  if (call.ai?.status === 'FAILED') {
    return 'Our assistant is unavailable right now — the shop will call you back.'
  }
  if (call.ai?.status === 'ENDED') {
    return `Call with the AI Front Desk ended · ${formatDuration(call.ai.duration_seconds)}`
  }
  if (call.missed_reason === 'CALLER_HUNG_UP') return 'Call cancelled'
  return audience.kind === 'customer'
    ? 'No one could answer — the shop has been notified.'
    : `${call.callee_label} didn't answer — they'll see a missed call.`
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (String(error.rawCode ?? error.code)) {
      case 'CALL_BUSY':
        return 'There is already a call for this booking, or someone is on another call.'
      case 'RATE_LIMITED':
        return 'Too many calls — try again in a few minutes.'
      case 'CALLING_DISABLED':
        return 'Calling is unavailable right now.'
      case 'CALL_ALREADY_ANSWERED':
        return 'Someone else already answered this call.'
      case 'CALL_NOT_ACTIVE':
        return 'This call is no longer ringing.'
      case 'UNAUTHENTICATED':
        return 'Sign in again with your password to use calling.'
      default:
        return error.message
    }
  }
  return 'Something went wrong. Please try again.'
}

export function CallProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [active, setActive] = useState<ActiveCall | null>(null)
  const [incoming, setIncoming] = useState<IncomingCall[]>([])
  const activeRef = useRef(active)
  useEffect(() => {
    activeRef.current = active
  })

  const refreshCalls = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['calls'] })
  }, [queryClient])

  /** Follow a pushed or returned call; ends the active call when the API says it is over. */
  const follow = useCallback(
    (call: CallRead) => {
      setActive((current) => {
        if (!current || current.call.id !== call.id || current.phase === 'ended') return current
        const phase = phaseFor(call, current.phase)
        return {
          ...current,
          call,
          phase,
          endedNote: phase === 'ended' ? endedNoteFor(call, current.audience) : undefined,
        }
      })
      setIncoming((list) => {
        const ringing = list.find((item) => item.call.id === call.id)
        if (!ringing || call.status === 'RINGING') return list
        if (activeRef.current?.call.id !== call.id) {
          toast(call.answered_by ? `Answered by ${call.answered_by.display_name}` : 'Missed call', {
            description: `${call.caller.display_name} · ${call.booking_reference}`,
          })
        }
        return list.filter((item) => item.call.id !== call.id)
      })
      refreshCalls()
    },
    [refreshCalls],
  )

  const onMessage = useCallback(
    (message: RealtimeMessage) => {
      if (message.type === 'call.incoming') {
        const call = message.data as CallRead
        if (activeRef.current?.call.id === call.id) return
        setIncoming((list) =>
          list.some((item) => item.call.id === call.id)
            ? list
            : [{ call, audience: audienceOf(call) }, ...list],
        )
      } else if (message.type === 'call.updated') {
        follow(message.data as CallRead)
      } else if (message.type === 'task.created') {
        const task = message.data as TaskRead
        toast(task.is_urgent ? 'Urgent AI task' : 'New AI task', {
          description: task.title,
        })
        void queryClient.invalidateQueries({ queryKey: ['calls', 'tasks'] })
      }
    },
    [follow, queryClient],
  )

  useRealtime(CALLING_ENABLED, onMessage)

  // Ring while a call waits for this person (and no call is in progress).
  const ringing = incoming.length > 0 && !active
  useEffect(() => {
    if (ringing) startRinging()
    else stopRinging()
    return stopRinging
  }, [ringing])

  // A ringing call that passes its deadline leaves the panel even if a push was missed.
  useEffect(() => {
    if (incoming.length === 0) return
    const timer = setInterval(() => {
      const now = Date.now()
      setIncoming((list) =>
        list.filter((item) => new Date(item.call.ring_deadline).getTime() + 2000 > now),
      )
    }, 1000)
    return () => clearInterval(timer)
  }, [incoming.length])

  // Leaving the page hangs up (there is no rejoin, §3.6): warn first.
  const inCall = Boolean(active && active.phase !== 'ended')
  useEffect(() => {
    if (!inCall) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [inCall])

  // An ended call stays on screen briefly with its outcome, then the bar goes away.
  useEffect(() => {
    if (active?.phase !== 'ended') return
    const timer = setTimeout(() => setActive(null), 6000)
    return () => clearTimeout(timer)
  }, [active?.phase])

  const begin = useCallback(
    (result: CallStartRead, audience: CallAudience, counterpart: string, phase: CallPhase) => {
      setActive({
        call: result.call,
        audience,
        phase: phaseFor(result.call, phase),
        connection: result.connection,
        counterpart,
      })
      refreshCalls()
    },
    [refreshCalls],
  )

  const start = useCallback(
    async (audience: CallAudience, bookingId: string, counterpart: string) => {
      if (activeRef.current && activeRef.current.phase !== 'ended') return
      setActive(null)
      if (!(await microphoneReady())) return
      try {
        const result = await startCall(audience, bookingId)
        begin(result, audience, counterpart, 'outgoing_ringing')
        if (result.call.rung_count === 0 && audience.kind === 'staff') {
          toast(`${counterpart} isn't in the app right now`, {
            description: "They'll see a missed call if they don't pick up.",
          })
        }
      } catch (error) {
        toast.error(errorMessage(error))
      }
    },
    [begin],
  )

  const accept = useCallback(
    async (item: IncomingCall) => {
      if (!(await microphoneReady())) return
      try {
        const result = await acceptCall(item.audience, item.call.id)
        setIncoming((list) => list.filter((entry) => entry.call.id !== item.call.id))
        begin(result, item.audience, item.call.caller.display_name, 'connecting')
      } catch (error) {
        setIncoming((list) => list.filter((entry) => entry.call.id !== item.call.id))
        toast.error(errorMessage(error))
      }
    },
    [begin],
  )

  const decline = useCallback(async (item: IncomingCall) => {
    setIncoming((list) => list.filter((entry) => entry.call.id !== item.call.id))
    try {
      await declineCall(item.audience, item.call.id)
    } catch (error) {
      if (!(
        error instanceof ApiError && String(error.rawCode ?? error.code) === 'CALL_NOT_ACTIVE'
      )) {
        toast.error(errorMessage(error))
      }
    }
  }, [])

  const hangUp = useCallback(async () => {
    const current = activeRef.current
    if (!current || current.phase === 'ended') return
    try {
      follow(await endCall(current.audience, current.call.id))
    } catch {
      // the API may have ended it already (idempotent); fall through to the local end
    }
    setActive((now) =>
      now && now.call.id === current.call.id && now.phase !== 'ended'
        ? { ...now, phase: 'ended', endedNote: now.endedNote ?? 'Call ended' }
        : now,
    )
  }, [follow])

  const value = useMemo<CallsContextValue>(
    () => ({
      enabled: CALLING_ENABLED,
      active,
      incoming: incoming.slice(0, MAX_INCOMING),
      busy: Boolean(active && active.phase !== 'ended'),
      start,
      accept,
      decline,
      hangUp,
    }),
    [active, incoming, start, accept, decline, hangUp],
  )

  const connection = active && active.phase !== 'ended' ? active.connection : null

  return (
    <CallsContext.Provider value={value}>
      {children}
      {CALLING_ENABLED ? (
        <>
          <IncomingCallPanel />
          {connection ? (
            <LiveKitRoom
              serverUrl={connection.url}
              token={connection.token}
              connect
              audio
              video={false}
              onError={() => toast.error('The call connection failed.')}
            >
              <RoomAudioRenderer />
              <RemoteLeaveWatcher onLeave={() => void hangUp()} />
              <InCallBar inRoom />
            </LiveKitRoom>
          ) : (
            <InCallBar inRoom={false} />
          )}
        </>
      ) : null}
    </CallsContext.Provider>
  )
}

/**
 * Spec 05 §3.6: when the other person disconnects, this side ends the call (covers a closed tab).
 * During the AI leg the API ends the leg itself; the room's deletion disconnects us.
 */
function RemoteLeaveWatcher({ onLeave }: { onLeave: () => void }) {
  const room = useRoomContext()
  const { active } = useCalls()
  const phase = active?.phase
  useEffect(() => {
    const left = () => {
      if (phase === 'connected') onLeave()
    }
    const disconnected = () => {
      if (phase === 'connected' || phase === 'ai_active') onLeave()
    }
    room.on(RoomEvent.ParticipantDisconnected, left)
    room.on(RoomEvent.Disconnected, disconnected)
    return () => {
      room.off(RoomEvent.ParticipantDisconnected, left)
      room.off(RoomEvent.Disconnected, disconnected)
    }
  }, [room, phase, onLeave])
  return null
}
