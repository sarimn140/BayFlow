import { ChartNoAxesColumn } from 'lucide-react'
import Link from 'next/link'

import { EmptyState } from '@/components/layout/empty-state'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import {
  STATUS_PHASE_LABELS,
  statusLabel,
  type BookingStatus,
  type StatusPhase,
} from '@/lib/status'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import { listOf, plural, type PhaseCount } from './overview-data'

/** Bars take the phase's ink (DESIGN.md §2.2): the same hue as the status chips. */
const PHASE_FILL: Record<StatusPhase, string> = {
  INTAKE: 'bg-status-intake-fg',
  INSPECTION: 'bg-status-inspection-fg',
  ESTIMATE: 'bg-status-estimate-fg',
  PARTS: 'bg-status-parts-fg',
  REPAIR_QC: 'bg-status-repair-qc-fg',
  HANDOVER: 'bg-status-handover-fg',
  CLOSED: 'bg-status-closed-fg',
}

/** ESTIMATE_REJECTED keeps the estimate phase but its chip is red, so its bar is too. */
function fillFor(phase: StatusPhase, status: BookingStatus) {
  return status === 'ESTIMATE_REJECTED' ? 'bg-status-estimate-rejected-fg' : PHASE_FILL[phase]
}

/** Share of all bookings, with a visible sliver for a single booking in a busy shop. */
function share(count: number, total: number) {
  return `${Math.max((count / total) * 100, 4)}%`
}

/**
 * Bookings by status (spec 10 O-01 §4): a pipeline bar across the seven phases, then one column
 * per phase that has bookings, each status as a bar in the phase colour with its count. A status
 * opens SA-01 filtered to it (`?status=`).
 */
export function StatusBreakdownCard({ phases, base }: { phases: PhaseCount[]; base: string }) {
  const total = phases.reduce((sum, p) => sum + p.total, 0)
  const busy = phases.filter((p) => p.total > 0)
  const empty = phases.filter((p) => p.total === 0)

  return (
    <Card>
      <CardHeader>
        <CardHeading>Bookings by status</CardHeading>
        <CardDescription>
          Where every booking is in the workflow. Select a status to open its bookings.
        </CardDescription>
        {total > 0 ? (
          <CardAction>
            <p className="text-sm font-semibold text-foreground tabular-nums">
              {plural(total, 'booking')}
            </p>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="gap-6">
        {total === 0 ? (
          <EmptyState
            variant="inline"
            tone="neutral"
            icon={ChartNoAxesColumn}
            title="No bookings to chart yet"
            description="Each booking shows up here by status as soon as it is made."
            className="p-6 sm:p-8"
          />
        ) : (
          <>
            <div
              aria-hidden="true"
              className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-secondary"
            >
              {busy.map((p) => (
                <span
                  key={p.phase}
                  className={cn('h-full', PHASE_FILL[p.phase])}
                  style={{ width: `${(p.total / total) * 100}%` }}
                />
              ))}
            </div>

            <div className="grid gap-x-8 gap-y-6 @md/overview:grid-cols-2 @4xl/overview:grid-cols-4">
              {busy.map((p) => (
                <div key={p.phase} className="min-w-0">
                  <h3 className="flex items-center gap-2 border-b border-border-faint pb-2 text-sm font-semibold text-foreground">
                    <span
                      aria-hidden="true"
                      className={cn('size-2.5 shrink-0 rounded-full', PHASE_FILL[p.phase])}
                    />
                    <span className="min-w-0 flex-1 truncate">{STATUS_PHASE_LABELS[p.phase]}</span>
                    <span className="font-semibold tabular-nums">
                      {p.total}
                      <span className="sr-only"> {p.total === 1 ? 'booking' : 'bookings'}</span>
                    </span>
                  </h3>
                  <ul className="mt-1.5 space-y-0.5">
                    {p.statuses
                      .filter((s) => s.count > 0)
                      .map((s) => (
                        <li key={s.status}>
                          <Link
                            href={`${base}/bookings?status=${s.status}`}
                            className="-mx-2 flex min-h-11 flex-col justify-center gap-1.5 rounded-lg px-2 py-1.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                          >
                            <span className="flex items-baseline justify-between gap-3">
                              <span className="truncate text-sm text-muted-foreground">
                                {statusLabel(s.status, 'staff')}
                              </span>
                              <span className="text-sm font-semibold text-foreground tabular-nums">
                                {s.count}
                                <span className="sr-only">
                                  {' '}
                                  {s.count === 1 ? 'booking' : 'bookings'}
                                </span>
                              </span>
                            </span>
                            <span
                              aria-hidden="true"
                              className="block h-1.5 overflow-hidden rounded-full bg-secondary"
                            >
                              <span
                                className={cn(
                                  'block h-full rounded-full',
                                  fillFor(p.phase, s.status),
                                )}
                                style={{ width: share(s.count, total) }}
                              />
                            </span>
                          </Link>
                        </li>
                      ))}
                  </ul>
                </div>
              ))}
            </div>

            {empty.length > 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing in {listOf(empty.map((p) => STATUS_PHASE_LABELS[p.phase]))} right now.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
