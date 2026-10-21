import { ArrowRight, CalendarDays, Car, Wrench, type LucideIcon } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { ActionNeededCallout } from '@/components/customer/booking-detail/booking-banners'
import { bookingSlot } from '@/components/customer/booking-detail/format'
import type { EstimateDecision } from '@/components/customer/estimate-decision'
import { StatusBadge } from '@/components/status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { formatPKR } from '@/lib/format'
import { shopPhoto } from '@/lib/shop-photos'
import type { BookingStatus } from '@/lib/status'
import { cn } from '@/lib/utils'

import type { BookingListItem } from './bookings-list-data'

/** One fact of the booking: a decorative icon, the label for screen readers, the value. */
function Fact({
  icon: Icon,
  label,
  children,
  className,
}: {
  icon: LucideIcon
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 items-start gap-2.5', className)}>
      <dt className="mt-0.5 shrink-0 text-brand-blue-ink">
        <Icon className="size-4" aria-hidden="true" />
        <span className="sr-only">{label}</span>
      </dt>
      <dd className="min-w-0 text-foreground">{children}</dd>
    </div>
  )
}

const ESTIMATE_LABEL = {
  pending: 'Estimate to approve',
  approved: 'Approved estimate',
  declined: 'Declined estimate',
} as const satisfies Record<EstimateDecision, string>

/** Before the inspection there is no price to show yet (D39). */
const BEFORE_ESTIMATE: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'PENDING',
  'CONFIRMED',
  'ASSIGNED',
  'INSPECTING',
])

/** The footer's money line: the estimate the customer can see, or where it stands. */
function EstimateSummary({
  estimate,
  status,
  total,
}: {
  estimate: EstimateDecision | null
  status: BookingStatus
  total: string
}) {
  const stage = estimate
    ? { label: ESTIMATE_LABEL[estimate], value: total }
    : status === 'ESTIMATE_REVIEW'
      ? { label: 'Estimate', value: 'Being prepared' }
      : BEFORE_ESTIMATE.has(status)
        ? { label: 'Estimate', value: 'After inspection' }
        : null
  if (!stage) return null
  return (
    <p className="flex min-w-0 flex-col">
      <span className="text-xs text-helper">{stage.label}</span>
      <span
        className={
          estimate
            ? 'text-base font-bold text-foreground tabular-nums'
            : 'text-sm font-medium text-muted-foreground'
        }
      >
        {stage.value}
      </span>
    </p>
  )
}

/** The callout's button: it opens the booking, where the decision is taken (spec 10 C-01). */
function CalloutLink({
  href,
  reference,
  children,
}: {
  href: string
  reference: string
  children: ReactNode
}) {
  return (
    // Above the card-wide link of "View booking".
    <Button asChild variant="outline" className="relative z-10">
      <Link href={href}>
        {children}
        <span className="sr-only"> for {reference}</span>
      </Link>
    </Button>
  )
}

/**
 * A booking in C-01 (spec 10): the action-needed callout when the customer must act, then the
 * shop, reference and status, the slot, the vehicle and the services, and the estimate with the
 * link to C-02. The whole card opens the booking; the callout's button sits above that link.
 */
export function BookingCard({ item }: { item: BookingListItem }) {
  const { booking, shopName, action, estimate } = item
  const href = `/bookings/${booking.id}`
  const photo = shopPhoto(item.shop?.slug ?? booking.shopSlug)
  const slot = bookingSlot(booking.scheduledDate, booking.scheduledTime)
  const total = formatPKR(booking.estimateTotal)

  return (
    <Card className="group/booking relative gap-0 py-0 transition-shadow duration-150 hover:shadow-md">
      <div className="flex flex-col gap-5 p-(--card-spacing)">
        {action === 'approve-estimate' ? (
          <ActionNeededCallout
            action={
              <CalloutLink href={href} reference={booking.reference}>
                Review estimate
              </CalloutLink>
            }
          >
            Your estimate is ready. Approve{' '}
            <span className="font-semibold whitespace-nowrap tabular-nums">{total}</span> to start
            the repair.
          </ActionNeededCallout>
        ) : null}

        {action === 'complete' ? (
          <ActionNeededCallout
            action={
              <CalloutLink href={href} reference={booking.reference}>
                View pick-up details
              </CalloutLink>
            }
          >
            Your car is ready to collect. Confirm once you&apos;ve picked it up.
          </ActionNeededCallout>
        ) : null}

        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-4 gap-y-3 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start">
          <div className="relative size-14 shrink-0 overflow-hidden rounded-xl bg-muted sm:size-16">
            <Image src={photo.src} alt="" fill sizes="64px" className="object-cover" />
          </div>
          {/* The heading names the shop and the booking, so each card's heading is unique. */}
          <h2 className="min-w-0 sm:self-center">
            <span className="block text-lg leading-snug font-semibold break-words text-foreground">
              {shopName}
            </span>
            <span className="mt-0.5 block font-mono text-sm font-semibold text-brand-blue-ink">
              {booking.reference}
            </span>
          </h2>
          {/* The longest customer label may wrap on narrow phones instead of overflowing. */}
          <StatusBadge
            status={booking.status}
            audience="customer"
            className="col-span-2 h-auto min-h-6 max-w-full justify-self-start py-0.5 text-left leading-tight whitespace-normal sm:col-span-1"
          />
        </div>

        <dl className="grid gap-x-6 gap-y-2.5 text-sm sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_minmax(0,3fr)]">
          <Fact icon={CalendarDays} label="Date and time">
            <span className="font-medium">
              {slot.date} · {slot.time}
            </span>
          </Fact>
          <Fact icon={Car} label="Vehicle">
            <span className="font-medium">
              {booking.vehicleYear} {booking.vehicleMake} {booking.vehicleModel}
            </span>{' '}
            <span className="ml-0.5 inline-block rounded-md border border-border bg-secondary px-1.5 font-mono text-xs leading-5 font-semibold whitespace-nowrap">
              {booking.licensePlate}
            </span>
          </Fact>
          <Fact icon={Wrench} label="Services" className="sm:col-span-2 lg:col-span-1">
            {booking.services.length > 0 ? (
              <span className="line-clamp-2">{booking.services.join(', ')}</span>
            ) : (
              <span className="text-muted-foreground">No services listed</span>
            )}
          </Fact>
        </dl>
      </div>

      <div className="flex items-center justify-between gap-4 border-t border-border-faint bg-muted px-(--card-spacing) py-3.5">
        <EstimateSummary estimate={estimate} status={booking.status} total={total} />
        {/*
          The card-wide link (`after:inset-0`). `active:scale-none`: any `scale` value, even 100%,
          would make the link the containing block of its overlay while pressed, shrinking the hit
          area to the button between press and release, so a tap on the card would not open it.
        */}
        <Button
          asChild
          variant="outline"
          className="ml-auto after:absolute after:inset-0 active:scale-none"
        >
          <Link href={href}>
            View booking
            <span className="sr-only"> {booking.reference}</span>
            <ArrowRight
              aria-hidden="true"
              data-icon="inline-end"
              className="transition-transform duration-150 group-hover/booking:translate-x-0.5 motion-reduce:transition-none"
            />
          </Link>
        </Button>
      </div>
    </Card>
  )
}
