import { ClipboardList } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { EmptyState } from '@/components/layout/empty-state'
import { Timeline, type TimelineItem, type TimelineTone } from '@/components/layout/timeline'
import { STATUS_ICONS } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime, formatPKR } from '@/lib/format'
import type { AdminUser } from '@/lib/mock-admin'
import type { BookingHistoryStep, HistoryActorRole } from '@/lib/mock-booking-history'
import type { MockBooking, MockEstimateItem, MockShop } from '@/lib/mock-data'
import { statusLabel, type BookingStatus } from '@/lib/status'
import { cn } from '@/lib/utils'

import { PlateTag } from './booking-list'
import { slotParts, vehicleLabel } from './slot'

const LINK =
  'rounded-sm font-medium text-brand-blue-ink outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

const ROLE_NAME: Record<HistoryActorRole, string> = {
  CUSTOMER: 'Customer',
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
}

function CardHeading({ children }: { children: ReactNode }) {
  return <h2 className="text-lg leading-7 font-semibold text-foreground">{children}</h2>
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right font-medium break-words text-foreground">{children}</dd>
    </div>
  )
}

function Secondary({ children }: { children: ReactNode }) {
  return <span className="block text-xs font-normal text-helper">{children}</span>
}

/** Where, who and when: the shop, the customer, the technician, the slot and the record dates. */
export function BookingDetailsCard({
  booking,
  customer,
  shop,
  timeZone,
}: {
  booking: MockBooking
  customer: AdminUser | undefined
  shop: MockShop | undefined
  timeZone: string
}) {
  const slot = slotParts(booking)
  return (
    <Card>
      <CardHeader>
        <CardHeading>Details</CardHeading>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border-faint text-sm">
          <Fact label="Shop">
            <Link href={`/admin/shops/${booking.shopId}`} className={LINK}>
              {booking.shopName}
            </Link>
            {shop ? <Secondary>{shop.city}</Secondary> : null}
          </Fact>
          <Fact label="Customer">
            {customer ? (
              <Link href={`/admin/users/${customer.id}`} className={LINK}>
                {booking.customerName}
              </Link>
            ) : (
              booking.customerName
            )}
            <Secondary>{booking.customerPhone}</Secondary>
            <Secondary>
              <span className="break-all">{booking.customerEmail}</span>
            </Secondary>
          </Fact>
          <Fact label="Technician">
            {booking.assignedTechnicianName ?? (
              <span className="font-normal text-muted-foreground">Not assigned yet</span>
            )}
          </Fact>
          <Fact label="Slot">
            {slot.date}
            <Secondary>{slot.time} (shop time)</Secondary>
          </Fact>
          <Fact label="Booked">
            <time dateTime={booking.createdAt}>{formatDateTime(booking.createdAt, timeZone)}</time>
          </Fact>
          <Fact label="Last update">
            <time dateTime={booking.updatedAt}>{formatDateTime(booking.updatedAt, timeZone)}</time>
          </Fact>
        </dl>
      </CardContent>
    </Card>
  )
}

const KM = new Intl.NumberFormat('en-PK')

/** The car, the services booked and the customer's own description of the problem. */
export function VehicleCard({ booking }: { booking: MockBooking }) {
  const extras = [
    booking.vehicleColor,
    booking.mileageKm ? `${KM.format(booking.mileageKm)} km` : undefined,
  ].filter(Boolean)
  return (
    <Card>
      <CardHeader>
        <CardHeading>Vehicle and services</CardHeading>
      </CardHeader>
      <CardContent className="gap-5">
        <div>
          <p className="text-base font-semibold text-foreground">{vehicleLabel(booking)}</p>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <PlateTag plate={booking.licensePlate} className="text-sm" />
            {extras.length > 0 ? <span>{extras.join(' · ')}</span> : null}
          </p>
        </div>
        <div>
          <h3 className="text-sm font-medium text-muted-foreground">Services booked</h3>
          {booking.services.length > 0 ? (
            <ul className="mt-1.5 space-y-1 text-sm font-medium text-foreground">
              {booking.services.map((service) => (
                <li key={service}>{service}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-sm text-muted-foreground">No services listed</p>
          )}
        </div>
        {booking.customerNotes ? (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground">Customer&apos;s notes</h3>
            <p className="mt-1.5 rounded-xl bg-layer px-4 py-3 text-sm whitespace-pre-line text-foreground">
              {booking.customerNotes}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

const APPROVED_OR_LATER: ReadonlySet<BookingStatus> = new Set([
  'ESTIMATE_APPROVED',
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
  'READY_FOR_PICKUP',
  'COMPLETED',
])

/** Where the estimate stands, read from the booking's status. */
function estimateState(booking: MockBooking): {
  label: string
  variant: 'secondary' | 'warning' | 'success' | 'destructive'
} {
  if (booking.status === 'AWAITING_CUSTOMER') return { label: 'Sent', variant: 'warning' }
  if (booking.status === 'ESTIMATE_REJECTED') return { label: 'Declined', variant: 'destructive' }
  if (
    APPROVED_OR_LATER.has(booking.status) ||
    (booking.status === 'CANCELLED' && booking.estimateApproved)
  ) {
    return { label: 'Approved', variant: 'success' }
  }
  if (booking.status === 'CANCELLED') return { label: 'Not approved', variant: 'secondary' }
  if (booking.status === 'ESTIMATE_REVIEW') return { label: 'In review', variant: 'secondary' }
  return { label: 'Draft', variant: 'secondary' }
}

/** "1" for parts, "1.5 h" for labour (labour quantities are hours, spec 02 §3.12). */
function quantity(line: MockEstimateItem): string {
  return line.type === 'LABOR' ? `${line.quantity} h` : String(line.quantity)
}

function LineType({ line }: { line: MockEstimateItem }) {
  return line.type === 'PART' ? (
    <Badge variant="info">Part</Badge>
  ) : (
    <Badge variant="neutral">Labour</Badge>
  )
}

const EDGE = 'first:pl-(--card-spacing) last:pr-(--card-spacing)'

/** The estimate as the shop wrote it: the total first, then every line (read-only). */
export function EstimateCard({ booking }: { booking: MockBooking }) {
  const lines = booking.estimateItems
  const parts = lines.filter((l) => l.type === 'PART').reduce((sum, l) => sum + l.total, 0)
  const labour = lines.filter((l) => l.type === 'LABOR').reduce((sum, l) => sum + l.total, 0)
  const state = lines.length > 0 ? estimateState(booking) : null

  return (
    <Card className="@container/estimate gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Estimate</CardHeading>
        <CardDescription>
          {lines.length === 0
            ? 'Parts and labour, once the technician has inspected the car'
            : `${lines.length} ${lines.length === 1 ? 'line' : 'lines'} · parts and labour`}
        </CardDescription>
        {state ? (
          <CardAction>
            <Badge variant={state.variant}>{state.label}</Badge>
          </CardAction>
        ) : null}
      </CardHeader>

      {lines.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={ClipboardList}
          title="No estimate yet"
          description="The technician writes it during the inspection, then the service advisor sends it to the customer."
          className="p-6 sm:p-8"
        />
      ) : (
        <>
          <div className="p-(--card-spacing)">
            <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 rounded-xl bg-layer p-4 sm:p-5">
              <div>
                <p className="text-sm font-medium text-muted-foreground">Estimate total</p>
                <p className="mt-1 text-3xl font-extrabold tracking-tight text-foreground tabular-nums">
                  {formatPKR(booking.estimateTotal)}
                </p>
              </div>
              <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                <div>
                  <dt className="text-muted-foreground">Parts</dt>
                  <dd className="mt-0.5 font-semibold text-foreground tabular-nums">
                    {formatPKR(parts)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Labour</dt>
                  <dd className="mt-0.5 font-semibold text-foreground tabular-nums">
                    {formatPKR(labour)}
                  </dd>
                </div>
                {booking.paidAmount > 0 ? (
                  <div>
                    <dt className="text-muted-foreground">Paid</dt>
                    <dd className="mt-0.5 font-semibold text-success-ink tabular-nums">
                      {formatPKR(booking.paidAmount)}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </div>
          </div>

          {/* Narrow cards: each line stacked as "name · qty × price = total". */}
          <div className="border-t border-border-faint @xl/estimate:hidden">
            <ul aria-label="Estimate lines" className="divide-y divide-border-faint">
              {lines.map((line) => (
                <li
                  key={line.id}
                  className="flex items-start justify-between gap-4 px-(--card-spacing) py-3.5"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="text-sm font-medium text-foreground">{line.description}</p>
                    <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground tabular-nums">
                      <LineType line={line} />
                      {quantity(line)} × {formatPKR(line.unit_price)}
                    </p>
                  </div>
                  <p className="shrink-0 text-sm font-semibold text-foreground tabular-nums">
                    {formatPKR(line.total)}
                  </p>
                </li>
              ))}
            </ul>
            <p className="flex items-baseline justify-between gap-4 border-t border-border-faint bg-muted px-(--card-spacing) py-3.5">
              <span className="text-sm font-semibold text-foreground">Total</span>
              <span className="text-lg font-bold text-foreground tabular-nums">
                {formatPKR(booking.estimateTotal)}
              </span>
            </p>
          </div>

          {/* Wide cards: the lines as a table, the total in the footer. */}
          <div className="hidden border-t border-border-faint @xl/estimate:block">
            <Table aria-label="Estimate lines">
              <TableHeader>
                <TableRow>
                  <TableHead className={EDGE}>Item</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Unit price</TableHead>
                  <TableHead className={cn('text-right', EDGE)}>Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.map((line) => (
                  <TableRow key={line.id}>
                    <TableCell className={cn('font-medium whitespace-normal', EDGE)}>
                      {line.description}
                    </TableCell>
                    <TableCell>
                      <LineType line={line} />
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {quantity(line)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {formatPKR(line.unit_price)}
                    </TableCell>
                    <TableCell className={cn('text-right font-semibold tabular-nums', EDGE)}>
                      {formatPKR(line.total)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
              <TableFooter>
                <TableRow className="hover:bg-transparent">
                  <TableHead scope="row" colSpan={4} className={cn('text-foreground', EDGE)}>
                    Total
                  </TableHead>
                  <TableCell className={cn('text-right text-lg font-bold tabular-nums', EDGE)}>
                    {formatPKR(booking.estimateTotal)}
                  </TableCell>
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </>
      )}
    </Card>
  )
}

/** The technician's and the QC inspector's notes, when there are any. */
export function ShopNotesCard({ booking }: { booking: MockBooking }) {
  if (!booking.inspectionNotes && !booking.qcNotes) return null
  return (
    <Card>
      <CardHeader>
        <CardHeading>Notes from the shop</CardHeading>
      </CardHeader>
      <CardContent className="gap-5">
        {booking.inspectionNotes ? (
          <div>
            <h3 className="text-sm font-medium text-muted-foreground">Technician notes</h3>
            <p className="mt-1.5 rounded-xl bg-layer px-4 py-3 text-sm text-foreground">
              {booking.inspectionNotes}
            </p>
          </div>
        ) : null}
        {booking.qcNotes ? (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-medium text-muted-foreground">QC notes</h3>
              {booking.qcPassed === true ? <Badge variant="success">Passed</Badge> : null}
              {booking.qcPassed === false ? <Badge variant="destructive">Failed</Badge> : null}
            </div>
            <p className="mt-1.5 rounded-xl bg-layer px-4 py-3 text-sm text-foreground">
              {booking.qcNotes}
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** Outcomes keep their colour; the current step is blue (amber while the customer decides). */
function stepTone(status: BookingStatus, current: boolean): TimelineTone {
  if (status === 'ESTIMATE_REJECTED' || status === 'CANCELLED') return 'danger'
  if (status === 'ESTIMATE_APPROVED' || status === 'READY_FOR_PICKUP' || status === 'COMPLETED')
    return 'success'
  if (current) return status === 'AWAITING_CUSTOMER' ? 'warning' : 'brand'
  return 'default'
}

/** Every step the booking went through, newest first, with who did it and when. */
export function BookingTimelineCard({
  steps,
  timeZone,
}: {
  /** Newest first. */
  steps: ReadonlyArray<BookingHistoryStep>
  timeZone: string
}) {
  const items: TimelineItem[] = steps.map((step, index) => ({
    id: `${step.status}-${step.at}`,
    title: statusLabel(step.status, 'staff'),
    description: (
      <>
        {step.actorName} · {ROLE_NAME[step.actorRole]} ·{' '}
        <span className="font-mono text-xs">{step.action}</span>
      </>
    ),
    time: <time dateTime={step.at}>{formatDateTime(step.at, timeZone)}</time>,
    icon: STATUS_ICONS[step.status],
    tone: stepTone(step.status, index === 0),
    current: index === 0,
  }))
  return (
    <Card>
      <CardHeader>
        <CardHeading>Timeline</CardHeading>
        <CardDescription>Every step, newest first, with who did it.</CardDescription>
      </CardHeader>
      <CardContent>
        {items.length > 0 ? (
          <Timeline aria-label="Booking timeline" items={items} />
        ) : (
          <p className="text-sm text-muted-foreground">No steps recorded yet.</p>
        )}
      </CardContent>
    </Card>
  )
}
