import { CalendarDays, ChevronRight, History } from 'lucide-react'
import Link from 'next/link'

import { EmptyState } from '@/components/layout/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { MockBooking } from '@/lib/mock-data'

import { CardHeading } from './card-heading'
import { dayLabel, plural, updatedAgo } from './overview-data'

export interface BookingsCardProps {
  /** The 5 most recently updated bookings. */
  recent: ReadonlyArray<MockBooking>
  /** Today's slots, earliest first. */
  today: ReadonlyArray<MockBooking>
  total: number
  active: number
  now: Date
  base: string
}

function BookingRow({ booking, now, base }: { booking: MockBooking; now: Date; base: string }) {
  const vehicle = `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
  return (
    <li>
      <Link
        href={`${base}/bookings/${encodeURIComponent(booking.id)}`}
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
              {booking.customerName} · {vehicle} ·{' '}
              <span className="font-mono font-normal text-muted-foreground">
                {booking.licensePlate}
              </span>
            </span>
            <span className="block truncate text-xs text-helper">
              {booking.services.join(', ')}
            </span>
          </span>
          <span className="flex shrink-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 @lg/bookings:flex-col @lg/bookings:items-end">
            <span className="text-sm font-medium text-foreground tabular-nums">
              {dayLabel(booking.scheduledDate)} · {booking.scheduledTime}
            </span>
            <span className="text-xs text-helper">{updatedAgo(booking.updatedAt, now)}</span>
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
 * Bookings at a glance: the last five that changed (spec 10 O-01 "Recent activity") and today's
 * schedule, each row opening the booking. "View all" opens the full list (SA-01).
 */
export function BookingsCard({ recent, today, total, active, now, base }: BookingsCardProps) {
  return (
    <Card className="@container/bookings gap-0 py-0">
      <Tabs defaultValue="recent" className="gap-0">
        <CardHeader className="border-b pt-(--card-spacing)">
          <CardHeading>Bookings</CardHeading>
          <CardDescription>
            {plural(total, 'booking')} in total · {active} active
          </CardDescription>
          <CardAction>
            <Button asChild variant="ghost" size="sm">
              <Link href={`${base}/bookings`}>
                View all<span className="sr-only"> {plural(total, 'booking')}</span>
              </Link>
            </Button>
          </CardAction>
          <TabsList aria-label="Bookings view" className="col-span-full mt-3">
            <TabsTrigger value="recent">
              <History aria-hidden="true" />
              Recent activity
            </TabsTrigger>
            <TabsTrigger value="today">
              <CalendarDays aria-hidden="true" />
              Today
              <Badge variant="outline" className="tabular-nums">
                {today.length}
              </Badge>
            </TabsTrigger>
          </TabsList>
        </CardHeader>

        <TabsContent
          value="recent"
          className="focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          {recent.length === 0 ? (
            <EmptyState
              variant="inline"
              className="p-6 sm:p-8"
              tone="neutral"
              icon={History}
              title="No bookings yet"
              description="Bookings from your public page and walk-ins appear here as they come in."
            />
          ) : (
            <ul className="divide-y divide-border-faint" aria-label="Recently updated bookings">
              {recent.map((booking) => (
                <BookingRow key={booking.id} booking={booking} now={now} base={base} />
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent
          value="today"
          className="focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          {today.length === 0 ? (
            <EmptyState
              variant="inline"
              className="p-6 sm:p-8"
              tone="neutral"
              icon={CalendarDays}
              title="Nothing on today's schedule"
              description="Bookings with a slot today are listed here, earliest first."
            />
          ) : (
            <ul className="divide-y divide-border-faint" aria-label="Today's bookings">
              {today.map((booking) => (
                <BookingRow key={booking.id} booking={booking} now={now} base={base} />
              ))}
            </ul>
          )}
        </TabsContent>
      </Tabs>
    </Card>
  )
}
