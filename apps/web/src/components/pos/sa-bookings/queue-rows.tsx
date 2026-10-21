'use client'

import { CircleAlert, Clock, Wrench } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import type { MouseEvent } from 'react'

import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import type { NextStep } from './queue-model'

export interface Assignee {
  name: string
  /** D19: a deactivated member keeps their jobs until someone reassigns them. */
  inactive: boolean
}

/** One booking, with everything the row shows already worked out. */
export interface QueueRow {
  booking: MockBooking
  href: string
  slot: string
  slotDateTime?: string
  updated: string | null
  estimate: string | null
  firstService: string
  moreServices: number
  technician: Assignee | null
  partsPerson: Assignee | null
  nextStep: NextStep
}

/** A number plate: mono, on a small white tag (DESIGN.md "plate/SKU tags"). */
function Plate({ plate }: { plate: string }) {
  return (
    <span className="inline-flex h-5 shrink-0 items-center rounded-md border border-border-medium bg-card px-1.5 font-mono text-xs font-medium text-foreground">
      {plate}
    </span>
  )
}

function vehicleName(booking: MockBooking): string {
  return [booking.vehicleYear, booking.vehicleMake, booking.vehicleModel].filter(Boolean).join(' ')
}

/** "Action needed" chip (spec 09 §3.4) for the advisor's move; quiet text for everyone else's. */
function NextStepLabel({ step }: { step: NextStep }) {
  if (step.kind === 'action') {
    return (
      <Badge variant="attention">
        <CircleAlert aria-hidden="true" data-icon="inline-start" />
        <span className="sr-only">Your next step:</span> {step.label}
      </Badge>
    )
  }
  if (step.kind === 'waiting') return <span className="text-sm text-helper">{step.label}</span>
  return (
    <span className="text-sm text-helper">
      <span aria-hidden="true">—</span>
      <span className="sr-only">Closed, nothing to do</span>
    </span>
  )
}

function InactiveBadge() {
  return (
    <Badge variant="warning" title="Deactivated: reassign from the booking">
      Inactive
    </Badge>
  )
}

function Assigned({ row }: { row: QueueRow }) {
  if (!row.technician && !row.partsPerson) {
    return <span className="text-sm text-helper">Unassigned</span>
  }
  return (
    <div className="space-y-0.5">
      {row.technician ? (
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="sr-only">Technician:</span>{' '}
          <span className="max-w-28 truncate">{row.technician.name}</span>
          {row.technician.inactive ? <InactiveBadge /> : null}
        </p>
      ) : (
        <p className="text-sm text-helper">No technician</p>
      )}
      {row.partsPerson ? (
        <p className="flex items-center gap-2 text-xs text-helper">
          <span className="max-w-28 truncate">Parts: {row.partsPerson.name}</span>
          {row.partsPerson.inactive ? <InactiveBadge /> : null}
        </p>
      ) : null}
    </div>
  )
}

/** First service and "+1 more"; screen readers get the whole list. */
function Services({ row, className }: { row: QueueRow; className?: string }) {
  return (
    <p className={cn('flex min-w-0 items-baseline gap-1.5', className)}>
      <span className="sr-only">{row.booking.services.join(', ')}</span>
      <span aria-hidden="true" className="truncate" title={row.booking.services.join(', ')}>
        {row.firstService}
      </span>
      {row.moreServices > 0 ? (
        <span aria-hidden="true" className="shrink-0 text-xs text-helper">
          +{row.moreServices} more
        </span>
      ) : null}
    </p>
  )
}

/*
 * Column tiers by the card's width (container queries; the card is the `@container`). Booking,
 * status, assigned and next step keep their natural width; "Customer and vehicle" and "Services"
 * share what is left (`max-w-0` + a width share) and truncate inside it, so the table never
 * overflows the card. "Assigned" shows from 864px, "Services" from 1,072px; below that the
 * services sit under the vehicle.
 */
const FLEX_CUSTOMER = 'w-[55%] max-w-0'
const FLEX_SERVICES = 'w-[45%] max-w-0'
const ASSIGNED_COLUMN = 'hidden @min-[54rem]:table-cell'
const SERVICES_COLUMN = 'hidden @min-[67rem]:table-cell'
const SERVICES_INLINE = '@min-[67rem]:hidden'

function Slot({ row, className }: { row: QueueRow; className?: string }) {
  return row.slotDateTime ? (
    <time dateTime={row.slotDateTime} className={className}>
      {row.slot}
    </time>
  ) : (
    <span className={className}>{row.slot}</span>
  )
}

/**
 * Desktop and tablet table (DESIGN.md "Data tables"). The reference is the row's link; a click
 * anywhere else on the row opens the booking too (spec 09 §4.7), without nesting controls.
 */
export function BookingsTable({
  rows,
  caption,
}: {
  rows: ReadonlyArray<QueueRow>
  caption: string
}) {
  const router = useRouter()

  const openRow = (event: MouseEvent<HTMLTableRowElement>, href: string) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey) return
    if ((event.target as HTMLElement).closest('a, button')) return
    if (window.getSelection()?.toString()) return
    router.push(href)
  }

  return (
    <Table>
      <TableCaption className="sr-only">{caption}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Booking</TableHead>
          <TableHead scope="col" className={FLEX_CUSTOMER}>
            Customer and vehicle
          </TableHead>
          <TableHead scope="col" className={cn(FLEX_SERVICES, SERVICES_COLUMN)}>
            Services
          </TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col" className={ASSIGNED_COLUMN}>
            Assigned
          </TableHead>
          <TableHead scope="col">Next step</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const { booking } = row
          return (
            <TableRow
              key={booking.id}
              className="cursor-pointer"
              onClick={(event) => openRow(event, row.href)}
            >
              <TableCell className="py-3">
                <Link
                  href={row.href}
                  className="rounded-sm font-mono text-sm font-semibold text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {booking.reference}
                </Link>
                <p className="mt-0.5 text-xs text-helper">
                  <Slot row={row} />
                </p>
              </TableCell>
              <TableCell className={cn('py-3', FLEX_CUSTOMER)}>
                <p className="truncate font-medium text-foreground" title={booking.customerName}>
                  {booking.customerName}
                </p>
                <p className="mt-1 flex min-w-0 items-center gap-2 text-xs text-helper">
                  <Plate plate={booking.licensePlate} />
                  <span className="truncate" title={vehicleName(booking)}>
                    {vehicleName(booking)}
                  </span>
                </p>
                <Services
                  row={row}
                  className={cn('mt-1 text-xs text-muted-foreground', SERVICES_INLINE)}
                />
              </TableCell>
              <TableCell className={cn('py-3', FLEX_SERVICES, SERVICES_COLUMN)}>
                <Services row={row} className="text-foreground" />
                {row.estimate ? (
                  <p className="mt-0.5 text-xs text-helper tabular-nums">{row.estimate}</p>
                ) : null}
              </TableCell>
              <TableCell className="py-3">
                <StatusBadge status={booking.status} audience="staff" />
                {row.updated ? <p className="mt-1 text-xs text-helper">{row.updated}</p> : null}
              </TableCell>
              <TableCell className={cn('py-3', ASSIGNED_COLUMN)}>
                <Assigned row={row} />
              </TableCell>
              <TableCell className="py-3">
                <NextStepLabel step={row.nextStep} />
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

/**
 * Phones and narrow cards: one stacked card per booking (spec 10 SA-01 "Mobile": reference,
 * status, slot, customer, vehicle and the next step, plus services and technician). The
 * reference link stretches over the card, so the whole card opens the booking.
 */
export function BookingsList({
  rows,
  label,
  className,
}: {
  rows: ReadonlyArray<QueueRow>
  label: string
  className?: string
}) {
  return (
    <ul aria-label={label} className={cn('divide-y divide-border-faint', className)}>
      {rows.map((row) => {
        const { booking } = row
        return (
          <li
            key={booking.id}
            className="relative px-5 py-4 transition-colors duration-150 hover:bg-brand-blue-subtle/40 has-[a:focus-visible]:bg-brand-blue-subtle/40"
          >
            <div className="flex items-start justify-between gap-3">
              <Link
                href={row.href}
                className="font-mono text-sm font-semibold text-brand-blue-ink outline-none after:absolute after:inset-0 focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-ring focus-visible:after:outline-solid"
              >
                {booking.reference}
              </Link>
              <StatusBadge status={booking.status} audience="staff" />
            </div>
            <p className="mt-2 truncate text-sm font-medium text-foreground">
              {booking.customerName}
            </p>
            <p className="mt-1 flex min-w-0 items-center gap-2 text-xs text-helper">
              <Plate plate={booking.licensePlate} />
              <span className="truncate">{vehicleName(booking)}</span>
            </p>
            <Services row={row} className="mt-1.5 text-xs text-muted-foreground" />
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-helper">
              <p className="flex items-center gap-1.5">
                <Clock className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="sr-only">Scheduled:</span> <Slot row={row} />
              </p>
              {row.technician ? (
                <p className="flex min-w-0 items-center gap-1.5">
                  <Wrench className="size-3.5 shrink-0" aria-hidden="true" />
                  <span className="sr-only">Technician:</span>{' '}
                  <span className="truncate">{row.technician.name}</span>
                  {row.technician.inactive ? <InactiveBadge /> : null}
                </p>
              ) : null}
            </div>
            {row.nextStep.kind === 'action' ? (
              <div className="mt-3">
                <NextStepLabel step={row.nextStep} />
              </div>
            ) : row.nextStep.kind === 'waiting' ? (
              <p className="mt-2 text-xs text-helper">{row.nextStep.label}</p>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
