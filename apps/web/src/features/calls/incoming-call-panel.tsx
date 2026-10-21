'use client'

/**
 * `IncomingCallDialog` (spec 05 §9.3, D78): a **non-modal** stacked panel, top right on desktop and
 * a bottom sheet on phones. No overlay and no focus trap — it never blocks the page or takes focus,
 * so a keystroke meant for a form can't answer a call. New calls are announced in an `aria-live`
 * region; Accept and Decline are ordinary buttons. Up to 3 calls stack, newest on top.
 */
import { CarFront, Phone, PhoneIncoming, PhoneOff } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'

import { useCalls, type IncomingCall } from './call-provider'
import { initials } from './format'

export function IncomingCallPanel() {
  const { incoming, busy } = useCalls()
  const newest = incoming[0]

  return (
    <>
      <div aria-live="polite" className="sr-only">
        {newest ? `Incoming call from ${newest.call.caller.display_name}` : ''}
      </div>
      {incoming.length > 0 ? (
        <section
          aria-label="Incoming calls"
          className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col gap-3 p-4 sm:inset-x-auto sm:top-20 sm:right-4 sm:bottom-auto sm:w-96 sm:p-0"
        >
          {incoming.map((item) => (
            <IncomingCallCard key={item.call.id} item={item} disabled={busy} />
          ))}
        </section>
      ) : null}
    </>
  )
}

function useSecondsLeft(deadline: string): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [])
  return Math.max(0, (new Date(deadline).getTime() - now) / 1000)
}

function IncomingCallCard({ item, disabled }: { item: IncomingCall; disabled: boolean }) {
  const { accept, decline } = useCalls()
  const { call } = item
  const [pending, setPending] = useState<'accept' | 'decline' | null>(null)
  const total = Math.max(
    1,
    (new Date(call.ring_deadline).getTime() - new Date(call.started_at).getTime()) / 1000,
  )
  const left = useSecondsLeft(call.ring_deadline)
  const fromCustomer = call.direction === 'CUSTOMER_TO_SHOP'
  const caller = call.caller.display_name

  const run = async (action: 'accept' | 'decline') => {
    setPending(action)
    try {
      await (action === 'accept' ? accept(item) : decline(item))
    } finally {
      setPending(null)
    }
  }

  return (
    <article
      aria-label={`Call from ${caller}`}
      className="pointer-events-auto animate-in rounded-2xl border border-border bg-card p-4 shadow-dialog duration-200 fade-in slide-in-from-top-2"
    >
      <div className="flex items-start gap-3">
        <div className="relative shrink-0">
          <span
            aria-hidden="true"
            className="absolute inset-0 animate-ping rounded-full bg-brand-blue/20 motion-reduce:hidden"
          />
          <span className="relative flex size-11 items-center justify-center rounded-full bg-brand-blue text-sm font-semibold text-brand-blue-foreground">
            {initials(caller)}
          </span>
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-blue-ink">
            <PhoneIncoming aria-hidden="true" className="size-4" />
            Incoming call
          </p>
          <p className="truncate text-base font-semibold text-foreground">
            {fromCustomer ? caller : `${caller} · ${call.shop_name}`}
          </p>
          <p className="flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground">
            <span className="font-mono font-medium text-foreground">{call.booking_reference}</span>
            {call.vehicle_label ? (
              <>
                <CarFront aria-hidden="true" className="size-3.5 shrink-0 text-helper" />
                <span className="truncate">{call.vehicle_label}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>

      <div className="mt-3 space-y-1">
        <Progress value={(left / total) * 100} aria-label="Time left to answer" className="h-1.5" />
        <p className="text-xs text-helper tabular-nums">
          {fromCustomer
            ? `The AI Front Desk answers in ${Math.ceil(left)} s`
            : `Ringing · ${Math.ceil(left)} s`}
        </p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <Button variant="outline" onClick={() => void run('decline')} disabled={pending !== null}>
          {pending === 'decline' ? <Spinner /> : <PhoneOff aria-hidden="true" />}
          Decline
        </Button>
        <Button onClick={() => void run('accept')} disabled={pending !== null || disabled}>
          {pending === 'accept' ? <Spinner /> : <Phone aria-hidden="true" />}
          Accept
        </Button>
      </div>
      {disabled ? (
        <p className="mt-2 text-xs text-helper">Finish your current call to answer this one.</p>
      ) : null}
    </article>
  )
}
