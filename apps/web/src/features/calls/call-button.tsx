'use client'

/**
 * The call button on a booking page (spec 05 §9.2): "Call the shop" for the booking's customer,
 * "Call customer" for the SA and Owner. Disabled while another call is on. Without calling
 * configured it falls back to `fallbackHref` (the shop's phone) or renders nothing.
 */
import { Phone, PhoneCall } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import { useOptionalCalls } from './call-provider'
import { useLiveBooking, type LiveBookingTarget } from './use-live-booking'

export interface CallButtonProps {
  target: LiveBookingTarget
  /** Who answers, for the in-call bar: the shop's name, or the customer's. */
  counterpart: string
  label: string
  fallbackHref?: string
  variant?: 'outline' | 'default'
  className?: string
}

export function CallButton(props: CallButtonProps) {
  const calls = useOptionalCalls()
  const { fallbackHref, label, variant = 'outline', className } = props
  if (!calls?.enabled) {
    return fallbackHref ? (
      <Button asChild variant={variant} className={className}>
        <a href={fallbackHref}>
          <Phone aria-hidden="true" />
          {label}
        </a>
      </Button>
    ) : null
  }
  return <LiveCallButton {...props} calls={calls} />
}

function LiveCallButton({
  target,
  counterpart,
  label,
  variant = 'outline',
  className,
  calls,
}: CallButtonProps & { calls: NonNullable<ReturnType<typeof useOptionalCalls>> }) {
  const live = useLiveBooking(target)

  const reason =
    live.state === 'signed-out'
      ? 'Sign in again with your password to use in-app calling.'
      : live.state === 'unavailable'
        ? 'In-app calling works on bookings in the live system.'
        : calls.busy
          ? "You're already in a call."
          : null

  const button = (
    <Button
      variant={variant}
      className={className}
      disabled={live.state !== 'ready' || calls.busy}
      onClick={() => {
        if (live.state === 'ready') void calls.start(live.audience, live.bookingId, counterpart)
      }}
    >
      {live.state === 'loading' ? <Spinner /> : <PhoneCall aria-hidden="true" />}
      {label}
    </Button>
  )

  if (!reason) return button
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* A disabled button gets no pointer events; the wrapper carries the tooltip. */}
        <span tabIndex={0} className="inline-flex rounded-full">
          {button}
        </span>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}
