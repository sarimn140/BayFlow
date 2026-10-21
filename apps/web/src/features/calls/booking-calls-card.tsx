'use client'

/**
 * The booking's call log (spec 05 §9.5): newest first, with who, when (shop time), the outcome and
 * durations, and an "AI Front Desk" badge where the AI answered. Staff also get "View AI summary";
 * customers never see summaries, transcripts or tasks (D21).
 */
import { useQuery } from '@tanstack/react-query'
import { Bot, ChevronRight, PhoneIncoming, PhoneMissed, PhoneOutgoing } from 'lucide-react'
import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'

import { listBookingCalls } from './api'
import { useOptionalCalls } from './call-provider'
import { outcomeOf } from './format'
import type { CallRead, StaffCallRead } from './types'
import { useLiveBooking, type LiveBookingTarget } from './use-live-booking'

export interface BookingCallsCardProps {
  target: LiveBookingTarget
  /** Staff only: the POS shop page base, for "View AI summary" links. */
  summaryHrefBase?: string
}

function whoLine(call: CallRead, staff: boolean): string {
  const customerCalled = call.direction === 'CUSTOMER_TO_SHOP'
  if (!staff) {
    return customerCalled
      ? `You called ${call.shop_name}`
      : `${call.caller.display_name} called you`
  }
  const answered = call.answered_by ? ` · answered by ${call.answered_by.display_name}` : ''
  return customerCalled
    ? `${call.caller.display_name} called${answered}`
    : `${call.caller.display_name} called ${call.callee_label}`
}

function CallIcon({ call }: { call: CallRead }) {
  const missed = call.status === 'MISSED'
  const Icon = call.ai
    ? Bot
    : missed
      ? PhoneMissed
      : call.direction === 'CUSTOMER_TO_SHOP'
        ? PhoneIncoming
        : PhoneOutgoing
  return (
    <span
      aria-hidden="true"
      className={
        missed && !call.ai
          ? 'flex size-9 shrink-0 items-center justify-center rounded-xl bg-danger-subtle text-danger-ink'
          : 'flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink'
      }
    >
      <Icon className="size-4" />
    </span>
  )
}

export function BookingCallsCard(props: BookingCallsCardProps) {
  const calls = useOptionalCalls()
  return calls?.enabled ? <LiveBookingCalls {...props} /> : null
}

function LiveBookingCalls({ target, summaryHrefBase }: BookingCallsCardProps) {
  const live = useLiveBooking(target)
  const staff = target.audience === 'staff'
  const ready = live.state === 'ready'
  const query = useQuery({
    queryKey: ['calls', 'booking', ready ? live.bookingId : null],
    queryFn: () => (ready ? listBookingCalls(live.audience, live.bookingId) : null),
    enabled: ready,
    refetchInterval: 20_000,
  })

  if (live.state === 'unavailable' || live.state === 'signed-out') return null

  const items = query.data?.items ?? []

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <h2 className="text-lg leading-7 font-semibold text-foreground">Calls</h2>
        <CardDescription>
          {staff
            ? 'In-app calls about this booking, including those the AI Front Desk answered.'
            : 'Your in-app calls with the shop about this booking.'}
        </CardDescription>
      </CardHeader>
      {live.state === 'loading' || query.isPending ? (
        <CardContent className="space-y-3 py-(--card-spacing)">
          <Skeleton className="h-12 rounded-xl" />
          <Skeleton className="h-12 rounded-xl" />
        </CardContent>
      ) : items.length === 0 ? (
        <CardContent className="py-(--card-spacing)">
          <p className="text-sm text-muted-foreground">
            No calls yet.{' '}
            {staff ? 'Use “Call customer” to reach them in the app.' : 'Use “Call the shop” above.'}
          </p>
        </CardContent>
      ) : (
        <ul className="divide-y divide-border-faint">
          {items.map((call) => {
            const summary = (call as StaffCallRead).has_summary
            return (
              <li key={call.id} className="flex items-center gap-3 px-5 py-3.5 sm:px-6">
                <CallIcon call={call} />
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="truncate text-sm font-medium text-foreground">
                    {whoLine(call, staff)}
                  </p>
                  <p className="truncate text-xs text-helper">
                    <time dateTime={call.started_at}>{formatDateTime(call.started_at)}</time> ·{' '}
                    {outcomeOf(call)}
                  </p>
                </div>
                {call.ai ? (
                  <Badge variant="brand" className="hidden sm:inline-flex">
                    <Bot aria-hidden="true" />
                    AI Front Desk
                  </Badge>
                ) : null}
                {staff && summary && summaryHrefBase ? (
                  <Link
                    href={`${summaryHrefBase}/calls?call=${call.id}`}
                    className="inline-flex min-h-10 shrink-0 items-center gap-1 rounded-full px-2 text-sm font-medium text-brand-blue-ink outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                  >
                    View AI summary
                    <ChevronRight aria-hidden="true" className="size-4" />
                  </Link>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
