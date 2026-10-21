import {
  CalendarCheck,
  CarFront,
  CheckCheck,
  ChevronRight,
  FileX,
  PackageCheck,
  PackageX,
  Send,
  UserPlus,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'

import { EmptyState } from '@/components/layout/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import type { MockBooking, MockPart } from '@/lib/mock-data'

import { CardHeading } from './card-heading'
import {
  NEXT_STEP,
  available,
  isSaActionStatus,
  plural,
  updatedAgo,
  type SaActionStatus,
} from './overview-data'

const STEP_ICONS: Record<SaActionStatus, LucideIcon> = {
  PENDING: CalendarCheck,
  CONFIRMED: UserPlus,
  ESTIMATE_REVIEW: Send,
  ESTIMATE_APPROVED: PackageCheck,
  ESTIMATE_REJECTED: FileX,
  READY_FOR_PICKUP: CarFront,
}

/** How many waiting bookings the card lists before "View queue" takes over. */
const VISIBLE = 5

/** Flush rows: the whole row is the link; the focus ring sits inside the card's clipped edge. */
const ROW_LINK =
  'group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6'

export interface AttentionCardProps {
  /** Bookings waiting on a service advisor, longest wait first. */
  queue: ReadonlyArray<MockBooking>
  /** LOW or OUT parts, OUT first. */
  restock: ReadonlyArray<MockPart>
  lowCount: number
  now: Date
  base: string
}

/**
 * "What needs attention now": every booking waiting on a service advisor with its next step
 * (spec 08), plus a restock reminder when parts are LOW or OUT (D45).
 */
export function AttentionCard({ queue, restock, lowCount, now, base }: AttentionCardProps) {
  const visible = queue.slice(0, VISIBLE)
  const total = queue.length + (lowCount > 0 ? 1 : 0)
  const anyOut = restock.some((p) => available(p) <= 0)

  return (
    <Card className="@container/attention gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>
          Needs attention
          {total > 0 ? (
            <Badge variant="attention" className="tabular-nums">
              {total}
              <span className="sr-only"> {total === 1 ? 'item' : 'items'}</span>
            </Badge>
          ) : null}
        </CardHeading>
        <CardDescription>
          {queue.length > 0
            ? `${plural(queue.length, 'booking')} waiting on a service advisor, longest wait first.`
            : 'Bookings that wait on a service advisor show up here.'}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href={`${base}/bookings?filter=needs_action`}>View queue</Link>
          </Button>
        </CardAction>
      </CardHeader>

      {total === 0 ? (
        <EmptyState
          variant="inline"
          className="p-6 sm:p-8"
          tone="success"
          icon={CheckCheck}
          title="You're all caught up"
          description="No booking is waiting on a service advisor and every part is above its reorder level."
        />
      ) : (
        <ul className="divide-y divide-border-faint">
          {visible.map((booking) => {
            const status = booking.status
            if (!isSaActionStatus(status)) return null
            const Icon = STEP_ICONS[status]
            const vehicle = `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
            const waiting = updatedAgo(booking.updatedAt, now)
            return (
              <li key={booking.id}>
                <Link
                  href={`${base}/bookings/${encodeURIComponent(booking.id)}`}
                  className={ROW_LINK}
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
                    <Icon className="size-5" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="block text-sm font-semibold text-foreground">
                      {NEXT_STEP[status]}
                    </span>
                    <span className="block truncate text-sm text-muted-foreground">
                      <span className="font-mono font-medium text-brand-blue-ink">
                        {booking.reference}
                      </span>
                      {' · '}
                      {booking.customerName} · {vehicle}
                    </span>
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 @lg/attention:hidden">
                      <StatusBadge status={status} audience="staff" />
                      <span className="text-xs text-helper">{waiting}</span>
                    </span>
                  </span>
                  <span className="hidden shrink-0 flex-col items-end gap-1.5 @lg/attention:flex">
                    <StatusBadge status={status} audience="staff" />
                    <span className="text-xs text-helper">{waiting}</span>
                  </span>
                  <ChevronRight
                    className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            )
          })}

          {queue.length > VISIBLE ? (
            <li>
              <Link href={`${base}/bookings?filter=needs_action`} className={ROW_LINK}>
                <span className="min-w-0 flex-1 text-sm font-medium text-brand-blue-ink">
                  {plural(queue.length - VISIBLE, 'more booking')} waiting — view the queue
                </span>
                <ChevronRight className="size-4 shrink-0 text-helper" aria-hidden="true" />
              </Link>
            </li>
          ) : null}

          {lowCount > 0 ? (
            <li>
              <Link href={`${base}/inventory`} className={ROW_LINK}>
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-warning-subtle text-warning-ink">
                  <PackageX className="size-5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="block text-sm font-semibold text-foreground">
                    Restock {plural(lowCount, 'part')}
                  </span>
                  <span className="block truncate text-sm text-muted-foreground">
                    {restock.map((p) => p.name).join(', ')}
                  </span>
                  <span className="flex @lg/attention:hidden">
                    <Badge variant={anyOut ? 'destructive' : 'warning'}>
                      {anyOut ? 'Out of stock' : 'Low stock'}
                    </Badge>
                  </span>
                </span>
                <span className="hidden shrink-0 @lg/attention:flex">
                  <Badge variant={anyOut ? 'destructive' : 'warning'}>
                    {anyOut ? 'Out of stock' : 'Low stock'}
                  </Badge>
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </Link>
            </li>
          ) : null}
        </ul>
      )}
    </Card>
  )
}
