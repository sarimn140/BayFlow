import { CalendarDays, ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { CardHeading } from '@/components/admin/overview/card-heading'
import { countByPhase, dayLabel, plural } from '@/components/admin/overview/overview-data'
import { PhaseBreakdown } from '@/components/admin/overview/phase-breakdown'
import { EmptyState } from '@/components/layout/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Card, CardDescription, CardHeader } from '@/components/ui/card'
import type { MockBooking } from '@/lib/mock-data'

/** How many of the shop's newest bookings A-03 lists. */
export const LATEST_BOOKINGS = 6

function BookingRow({ booking }: { booking: MockBooking }) {
  return (
    <li>
      <Link
        href={`/admin/bookings/${encodeURIComponent(booking.id)}`}
        className="group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6"
      >
        <span className="flex min-w-0 flex-1 flex-col gap-2 @lg/bookings:flex-row @lg/bookings:items-center @lg/bookings:gap-4">
          <span className="min-w-0 flex-1 space-y-1">
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-mono text-sm font-semibold text-brand-blue-ink">
                {booking.reference}
              </span>
              <StatusBadge status={booking.status} audience="staff" />
            </span>
            <span className="block truncate text-sm font-medium text-foreground">
              {booking.customerName} · {booking.vehicleYear} {booking.vehicleMake}{' '}
              {booking.vehicleModel} ·{' '}
              <span className="font-mono font-normal text-muted-foreground">
                {booking.licensePlate}
              </span>
            </span>
            <span className="block truncate text-xs text-helper">
              {booking.services.join(', ')}
            </span>
          </span>
          <span className="shrink-0 text-sm font-medium text-foreground tabular-nums @lg/bookings:text-right">
            {dayLabel(booking.scheduledDate)} · {booking.scheduledTime}
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </Link>
    </li>
  )
}

/**
 * A-03 booking counts by phase and the latest bookings (spec 19 §5) in one card: every status
 * counted per phase, then the newest bookings, each opening the read-only booking (A-07).
 */
export function ShopBookingsCard({ bookings }: { bookings: ReadonlyArray<MockBooking> }) {
  const latest = bookings.slice(0, LATEST_BOOKINGS)

  return (
    <Card className="@container/bookings gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Bookings</CardHeading>
        <CardDescription>
          {bookings.length === 0
            ? 'Counts by phase and the newest bookings'
            : `${plural(bookings.length, 'booking')} in total, every status included`}
        </CardDescription>
      </CardHeader>
      {bookings.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={CalendarDays}
          title="No bookings yet"
          description="Bookings at this shop appear here by phase as soon as customers book."
          className="p-6 sm:p-8"
        />
      ) : (
        <>
          <section aria-labelledby="shop-bookings-by-phase" className="px-5 py-5 sm:px-6">
            <h3
              id="shop-bookings-by-phase"
              className="mb-4 text-base font-semibold text-foreground"
            >
              By phase
            </h3>
            <PhaseBreakdown
              phases={countByPhase(bookings)}
              total={bookings.length}
              className="grid space-y-0 gap-x-8 gap-y-3.5 @xl/bookings:grid-cols-2"
            />
          </section>
          <section aria-labelledby="shop-bookings-latest" className="border-t border-border-faint">
            <h3
              id="shop-bookings-latest"
              className="px-5 pt-5 pb-2 text-base font-semibold text-foreground sm:px-6"
            >
              Latest
              {bookings.length > LATEST_BOOKINGS ? (
                <span className="font-normal text-muted-foreground">
                  {' '}
                  · the {LATEST_BOOKINGS} newest
                </span>
              ) : null}
            </h3>
            <ul className="divide-y divide-border-faint">
              {latest.map((booking) => (
                <BookingRow key={booking.id} booking={booking} />
              ))}
            </ul>
          </section>
        </>
      )}
    </Card>
  )
}
