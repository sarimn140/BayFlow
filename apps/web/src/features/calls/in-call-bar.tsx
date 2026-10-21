'use client'

/**
 * The in-call bar (spec 05 §9.4): a floating card at the bottom of every page while a call is on.
 * It names the other party (or "AI Front Desk · <shop>"), shows the state and a timer, and holds
 * mute and hang-up. During the AI leg a voice visualizer shows listening / thinking / speaking.
 * `StartAudio` appears only when the browser blocks audio playback.
 */
import {
  BarVisualizer,
  StartAudio,
  useConnectionQualityIndicator,
  useLocalParticipant,
  useVoiceAssistant,
} from '@livekit/components-react'
import { ConnectionQuality } from 'livekit-client'
import { Bot, Mic, MicOff, Phone, PhoneOff, Signal, SignalLow, Volume2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'

import { useCalls, type ActiveCall } from './call-provider'
import { formatDuration, initials, secondsSince } from './format'

function useClock(running: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [running])
  return now
}

function stateLine(active: ActiveCall, now: number): string {
  const { call, phase } = active
  switch (phase) {
    case 'preparing':
      return 'Checking your microphone…'
    case 'outgoing_ringing':
      return call.direction === 'CUSTOMER_TO_SHOP' && call.rung_count === 0
        ? 'Ringing… no advisor is online right now'
        : 'Ringing…'
    case 'connecting':
      return 'Connecting…'
    case 'connected':
      return `Connected · ${formatDuration(secondsSince(call.answered_at, now))}`
    case 'ai_connecting':
      return 'Our advisors are busy — connecting you to the AI assistant…'
    case 'ai_active':
      return `AI assistant · ${formatDuration(secondsSince(call.ai?.answered_at, now))}`
    case 'ended':
      return active.endedNote ?? 'Call ended'
  }
}

export function InCallBar({ inRoom }: { inRoom: boolean }) {
  const { active, hangUp } = useCalls()
  const live = Boolean(active && active.phase !== 'ended')
  const now = useClock(live)
  const [hangingUp, setHangingUp] = useState(false)
  if (!active) return null

  const ai = active.phase === 'ai_connecting' || active.phase === 'ai_active'
  const ended = active.phase === 'ended'
  const title = ai ? `AI Front Desk · ${active.call.shop_name}` : active.counterpart

  return (
    <section
      aria-label="Current call"
      className="fixed inset-x-0 bottom-0 z-50 p-3 sm:bottom-4 sm:p-0"
    >
      <div
        className={cn(
          'mx-auto flex w-full max-w-2xl animate-in items-center gap-3 rounded-2xl border bg-card p-3 shadow-dialog duration-200 fade-in slide-in-from-bottom-2 sm:gap-4 sm:p-4',
          ended ? 'border-border' : 'border-brand-blue/30',
        )}
      >
        <div
          aria-hidden="true"
          className={cn(
            'flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
            ai
              ? 'bg-brand-blue-subtle text-brand-blue-ink'
              : ended
                ? 'bg-secondary text-muted-foreground'
                : 'bg-brand-blue text-brand-blue-foreground',
          )}
        >
          {ai ? <Bot className="size-5" /> : initials(active.counterpart)}
        </div>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground sm:text-base">{title}</p>
          <p
            className={cn(
              'truncate text-xs sm:text-sm',
              ended ? 'text-muted-foreground' : 'text-brand-blue-ink',
            )}
            aria-live="polite"
          >
            {stateLine(active, now)}
          </p>
          <p className="truncate font-mono text-xs text-helper">
            {active.call.booking_reference}
            {active.call.vehicle_label ? ` · ${active.call.vehicle_label}` : ''}
          </p>
        </div>

        {inRoom && !ended ? <RoomControls ai={active.phase === 'ai_active'} /> : null}

        {ended ? (
          <Phone aria-hidden="true" className="size-5 shrink-0 text-helper" />
        ) : (
          <Button
            variant="destructive"
            size="icon-lg"
            aria-label="Hang up"
            disabled={hangingUp}
            onClick={async () => {
              setHangingUp(true)
              try {
                await hangUp()
              } finally {
                setHangingUp(false)
              }
            }}
          >
            {hangingUp ? <Spinner /> : <PhoneOff aria-hidden="true" />}
          </Button>
        )}
      </div>
    </section>
  )
}

/** Controls that need the LiveKit room: mute, connection quality, the AI visualizer. */
function RoomControls({ ai }: { ai: boolean }) {
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant()
  const { quality } = useConnectionQualityIndicator({ participant: localParticipant })
  const poor = quality === ConnectionQuality.Poor || quality === ConnectionQuality.Lost

  return (
    <div className="flex shrink-0 items-center gap-2">
      {ai ? <AssistantVisualizer /> : null}
      <span
        className={cn(
          'hidden items-center sm:inline-flex',
          poor ? 'text-warning-ink' : 'text-helper',
        )}
        title={poor ? 'Weak connection' : 'Good connection'}
      >
        {poor ? (
          <SignalLow aria-hidden="true" className="size-4" />
        ) : (
          <Signal aria-hidden="true" className="size-4" />
        )}
        <span className="sr-only">{poor ? 'Weak connection' : 'Good connection'}</span>
      </span>
      <StartAudio
        label="Enable audio"
        className="inline-flex h-10 items-center gap-1.5 rounded-full border border-border-medium bg-card px-3 text-sm font-medium text-foreground"
      >
        <Volume2 aria-hidden="true" className="size-4" />
      </StartAudio>
      <Button
        variant="outline"
        size="icon-lg"
        aria-pressed={!isMicrophoneEnabled}
        aria-label={isMicrophoneEnabled ? 'Mute microphone' : 'Unmute microphone'}
        onClick={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
      >
        {isMicrophoneEnabled ? <Mic aria-hidden="true" /> : <MicOff aria-hidden="true" />}
      </Button>
    </div>
  )
}

const ASSISTANT_STATE: Record<string, string> = {
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  connecting: 'Connecting',
  initializing: 'Connecting',
}

function AssistantVisualizer() {
  const { state, audioTrack } = useVoiceAssistant()
  return (
    <div className="hidden items-center gap-2 sm:flex">
      <BarVisualizer
        state={state}
        trackRef={audioTrack}
        barCount={5}
        className="flex h-7 w-12 items-center justify-center gap-1 [&>span]:min-h-1.5 [&>span]:w-1.5 [&>span]:rounded-full [&>span]:bg-brand-blue/25 [&>span]:transition-colors [&>span[data-lk-highlighted=true]]:bg-brand-blue"
      />
      <span className="w-16 text-xs text-helper">{ASSISTANT_STATE[state] ?? ''}</span>
    </div>
  )
}
