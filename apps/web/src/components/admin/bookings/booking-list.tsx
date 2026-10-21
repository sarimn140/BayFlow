import { ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { StatusBadge } from '@/components/status-badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatPKR } from '@/lib/format'
import type { MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { slotParts, vehicleLabel } from './slot'

const LINK_FOCUS =
  'rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

/** A number plate as a small mono tag (DESIGN.md: plates in `font-mono`, 8px corners). */
export function PlateTag({ plate, className }: { plate: string; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border border-border bg-secondary px-1.5 py-px font-mono text-xs font-semibold text-foreground',
        className,
      )}
    >
      {plate}
    </span>
  )
}

/** The estimate total, or a dash that says what it means to screen readers. */
export function EstimateAmount({ total }: { total: number }) {
  if (total) return <>{formatPKR(total)}</>
  return (
    <>
      <span aria-hidden="true" className="text-helper">
        —
      </span>
      <span className="sr-only">No estimate yet</span>
    </>
  )
}

/** Wide screens: every booking in every shop, one row each (spec 19 §5 A-06). */
export function BookingsTable({ bookings }: { bookings: ReadonlyArray<MockBooking> }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Booking</TableHead>
          <TableHead>Customer</TableHead>
          <TableHead>Vehicle</TableHead>
          <TableHead>Slot</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Estimate</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {bookings.map((b) => {
          const slot = slotParts(b)
          return (
            <TableRow key={b.id}>
              {/* The reference opens A-07; the shop under it opens A-03. Both are 24px tall
                  targets (WCAG 2.5.8), stacked without overlapping. */}
              <TableCell className="py-1.5">
                <Link
                  href={`/admin/bookings/${b.id}`}
                  className={cn(
                    'inline-flex min-h-6 items-center font-mono font-semibold text-brand-blue-ink hover:underline',
                    LINK_FOCUS,
                  )}
                >
                  {b.reference}
                </Link>
                <p>
                  <Link
                    href={`/admin/shops/${b.shopId}`}
                    className={cn(
                      'inline-flex min-h-6 items-center text-xs text-muted-foreground underline decoration-border-strong/50 underline-offset-2 hover:text-brand-blue-ink hover:decoration-current',
                      LINK_FOCUS,
                    )}
                  >
                    {b.shopName}
                  </Link>
                </p>
              </TableCell>
              <TableCell className="py-2.5">
                <p className="font-medium">{b.customerName}</p>
                <p className="text-xs text-helper">{b.customerEmail}</p>
              </TableCell>
              <TableCell className="py-2.5 whitespace-normal">
                <PlateTag plate={b.licensePlate} className="whitespace-nowrap" />
                <p className="mt-1 max-w-36 text-xs text-helper">{vehicleLabel(b)}</p>
              </TableCell>
              <TableCell className="py-2.5">
                <p>{slot.date}</p>
                <p className="text-xs text-helper">{slot.time}</p>
              </TableCell>
              <TableCell>
                <StatusBadge status={b.status} audience="staff" />
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                <EstimateAmount total={b.estimateTotal} />
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

/** Narrow screens: each booking is one tappable row that opens A-07. */
export function BookingsList({ bookings }: { bookings: ReadonlyArray<MockBooking> }) {
  return (
    <ul className="divide-y divide-border-faint">
      {bookings.map((b) => {
        const slot = slotParts(b)
        return (
          <li key={b.id}>
            <Link
              href={`/admin/bookings/${b.id}`}
              className="group flex items-start gap-3 px-5 py-4 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
            >
              {/* Phones: one column. Wider cards: the slot and the estimate move to the right. */}
              <div className="min-w-0 flex-1 space-y-1.5 @xl/bookings:flex @xl/bookings:items-start @xl/bookings:justify-between @xl/bookings:gap-6 @xl/bookings:space-y-0">
                <div className="min-w-0 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                    <span className="font-mono text-sm font-semibold text-brand-blue-ink">
                      {b.reference}
                    </span>
                    <StatusBadge status={b.status} audience="staff" />
                  </div>
                  <p className="truncate text-sm font-medium text-foreground">
                    {b.customerName} · {vehicleLabel(b)}
                  </p>
                  <p className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
                    <PlateTag plate={b.licensePlate} />
                    <span className="truncate">{b.shopName}</span>
                  </p>
                </div>
                <div className="flex items-baseline justify-between gap-3 @xl/bookings:shrink-0 @xl/bookings:flex-col @xl/bookings:items-end @xl/bookings:gap-1">
                  <p className="text-xs text-helper @xl/bookings:text-sm @xl/bookings:text-muted-foreground">
                    {slot.date} · {slot.time}
                  </p>
                  <p className="text-sm font-semibold text-foreground tabular-nums">
                    <EstimateAmount total={b.estimateTotal} />
                  </p>
                </div>
              </div>
              <ChevronRight
                className="mt-1 size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
