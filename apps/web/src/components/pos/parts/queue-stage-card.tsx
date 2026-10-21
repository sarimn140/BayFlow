import { ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import type { MockBooking, MockPurchaseOrder } from '@/lib/mock-data'

import {
  availabilityLabel,
  availablePercent,
  jobHealth,
  shopDateTime,
  vehicleLabel,
  waitingFor,
  type PartsSummary,
  type QueueStage,
} from './parts-data'
import { CardHeading } from './parts-states'
import { JobStockChip } from './stock-chip'

/** What each stage asks of the parts person (spec 10 PP-01 sections). */
const STAGE_COPY: Record<QueueStage, { title: string; hint: string; empty: string }> = {
  PARTS_PENDING: {
    title: 'To check',
    hint: 'Compare with stock, then reserve the parts or order what is missing.',
    empty: 'Nothing to check right now.',
  },
  PARTS_ORDERED: {
    title: 'On order',
    hint: 'Waiting for the supplier. Receive the delivery, then mark the parts ready.',
    empty: 'Nothing on order.',
  },
  PARTS_READY: {
    title: 'Ready to allocate',
    hint: 'Hand the parts to the technician so the repair can start.',
    empty: 'Nothing waiting to be allocated.',
  },
}

/** Flush rows: the whole row is the link; the focus ring sits inside the card's clipped edge. */
const ROW_LINK =
  'group flex items-center gap-3 px-5 py-4 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6'

export interface QueueJob {
  booking: MockBooking
  summary: PartsSummary
}

export interface QueueStageCardProps {
  stage: QueueStage
  /** The stage's jobs, the longest wait first. */
  jobs: ReadonlyArray<QueueJob>
  now: Date
  timeZone: string | undefined
  base: string
  /** "On order": the purchase order a job waits on (`orderForJob`), named in its row. */
  orderOf?: (bookingId: string) => Pick<MockPurchaseOrder, 'po_number' | 'status'> | undefined
}

/**
 * One stage of the parts queue (spec 10 PP-01): its jobs with the vehicle, technician, how many
 * parts stock covers and how long the job has waited, and on order the purchase order it waits
 * on. Each row opens the job (PP-02). Rows stack in a narrow card and spread into columns in a
 * wide one (container query).
 */
export function QueueStageCard({ stage, jobs, now, timeZone, base, orderOf }: QueueStageCardProps) {
  const copy = STAGE_COPY[stage]
  const headingId = `stage-${stage.toLowerCase()}`

  return (
    <Card className="@container/stage gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading id={headingId}>
          {copy.title}
          <Badge variant="secondary" className="tabular-nums">
            {jobs.length}
            <span className="sr-only"> {jobs.length === 1 ? 'job' : 'jobs'}</span>
          </Badge>
        </CardHeading>
        {/* The chip sits beside the title only, so the hint gets the card's full width. */}
        <CardDescription className="col-span-full">{copy.hint}</CardDescription>
        <CardAction className="row-span-1 self-center">
          <StatusBadge status={stage} audience="staff" />
        </CardAction>
      </CardHeader>

      {jobs.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground sm:px-6">{copy.empty}</p>
      ) : (
        <ul aria-labelledby={headingId} className="divide-y divide-border-faint">
          {jobs.map(({ booking, summary }) => {
            const waiting = waitingFor(booking.updatedAt, now)
            const since = shopDateTime(booking.updatedAt, timeZone)
            const order = orderOf?.(booking.id)
            return (
              <li key={booking.id}>
                <Link href={`${base}/parts/${encodeURIComponent(booking.id)}`} className={ROW_LINK}>
                  <div className="grid min-w-0 flex-1 gap-3 @2xl/stage:grid-cols-[minmax(0,1fr)_10rem_9.5rem] @2xl/stage:items-center @2xl/stage:gap-5">
                    <div className="min-w-0 space-y-0.5">
                      <p className="font-mono text-sm font-semibold text-brand-blue-ink">
                        {booking.reference}
                      </p>
                      <p className="truncate text-sm font-medium text-foreground">
                        {vehicleLabel(booking)}
                      </p>
                      <p className="truncate text-sm text-muted-foreground">
                        <span className="font-mono">{booking.licensePlate}</span>
                        {' · '}
                        {booking.assignedTechnicianName
                          ? `Technician ${booking.assignedTechnicianName}`
                          : 'No technician yet'}
                      </p>
                      {order ? (
                        <p className="truncate text-sm text-muted-foreground">
                          On{' '}
                          <span className="font-mono font-medium text-foreground">
                            {order.po_number}
                          </span>
                          {order.status === 'RECEIVED'
                            ? ' · delivered'
                            : order.status === 'PARTIALLY_RECEIVED'
                              ? ' · partly delivered'
                              : null}
                        </p>
                      ) : null}
                    </div>

                    <div className="order-3 space-y-1.5 @2xl/stage:order-2">
                      <p className="text-xs text-muted-foreground tabular-nums">
                        {availabilityLabel(summary)}
                      </p>
                      {summary.requiredCount > 0 ? (
                        <Progress
                          value={availablePercent(summary)}
                          aria-hidden="true"
                          className="h-1.5"
                        />
                      ) : null}
                    </div>

                    <div className="order-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 @2xl/stage:order-3 @2xl/stage:flex-col @2xl/stage:items-end">
                      <JobStockChip
                        health={jobHealth(summary, booking.status)}
                        shortCount={summary.short.length}
                      />
                      {waiting ? (
                        <time
                          dateTime={booking.updatedAt}
                          title={since ? `In this step since ${since}` : undefined}
                          className="text-xs text-helper"
                        >
                          {waiting}
                        </time>
                      ) : null}
                    </div>
                  </div>
                  <ChevronRight
                    className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
