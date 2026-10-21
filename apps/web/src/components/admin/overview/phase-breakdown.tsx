import { STATUS_PHASE_LABELS, type StatusPhase } from '@/lib/status'
import { cn } from '@/lib/utils'

import type { PhaseCount } from './overview-data'

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

/** Share of the total, with a visible sliver for a single booking among many. */
function share(count: number, total: number) {
  return `${Math.max((count / total) * 100, 4)}%`
}

/**
 * Bookings per phase as labelled rows: the phase dot and name, the count, and a bar for its share
 * of the total. The name and count carry the meaning; the hue only echoes the status chips.
 */
export function PhaseBreakdown({
  phases,
  total,
  className,
}: {
  phases: ReadonlyArray<PhaseCount>
  total: number
  className?: string
}) {
  return (
    <ul className={cn('space-y-3.5', className)}>
      {phases.map(({ phase, count }) => (
        <li key={phase} className="space-y-1.5">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
              <span
                aria-hidden="true"
                className={cn('size-2.5 shrink-0 rounded-full', PHASE_FILL[phase])}
              />
              <span className="truncate">{STATUS_PHASE_LABELS[phase]}</span>
            </span>
            <span
              className={cn(
                'font-semibold tabular-nums',
                count === 0 ? 'text-helper' : 'text-foreground',
              )}
            >
              {count}
              <span className="sr-only"> {count === 1 ? 'booking' : 'bookings'}</span>
            </span>
          </div>
          <span
            aria-hidden="true"
            className="block h-1.5 overflow-hidden rounded-full bg-secondary"
          >
            {count > 0 && total > 0 ? (
              <span
                className={cn('block h-full rounded-full', PHASE_FILL[phase])}
                style={{ width: share(count, total) }}
              />
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  )
}
