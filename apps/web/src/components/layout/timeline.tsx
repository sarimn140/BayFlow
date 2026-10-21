import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type TimelineTone = 'default' | 'brand' | 'success' | 'warning' | 'danger'

const NODE_TONE: Record<TimelineTone, string> = {
  default: 'bg-secondary text-muted-foreground',
  brand: 'bg-brand-blue-subtle text-brand-blue-ink',
  success: 'bg-success-subtle text-success-ink',
  warning: 'bg-warning-subtle text-warning-ink',
  danger: 'bg-danger-subtle text-danger-ink',
}

export interface TimelineItem {
  id: string
  title: ReactNode
  /** Who did it, notes, a reference. */
  description?: ReactNode
  /** When: pass a `<time dateTime=…>` with the formatted date. */
  time?: ReactNode
  icon?: LucideIcon
  tone?: TimelineTone
  /** The step the booking is at now, for progress timelines (spec 09 §4.4: `aria-current="step"`). */
  current?: boolean
}

/**
 * Activity timeline (DESIGN.md "Timeline"): newest first, an icon node per event on a hairline
 * rail, the title, a muted description and the time.
 */
export function Timeline({
  items,
  className,
  'aria-label': ariaLabel,
}: {
  items: ReadonlyArray<TimelineItem>
  className?: string
  'aria-label'?: string
}) {
  return (
    <ol className={cn('relative', className)} aria-label={ariaLabel}>
      {items.map((item, index) => {
        const Icon = item.icon
        const last = index === items.length - 1
        return (
          <li
            key={item.id}
            aria-current={item.current ? 'step' : undefined}
            className={cn('relative flex gap-3', !last && 'pb-5')}
          >
            {!last ? (
              <span aria-hidden="true" className="absolute top-9 bottom-1 left-4 w-px bg-border" />
            ) : null}
            <span
              className={cn(
                'relative flex size-8 shrink-0 items-center justify-center rounded-full',
                NODE_TONE[item.tone ?? 'default'],
              )}
            >
              {Icon ? (
                <Icon className="size-4" aria-hidden="true" />
              ) : (
                <span className="size-2 rounded-full bg-current" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <p className="text-sm font-semibold text-foreground">{item.title}</p>
                {item.time ? <p className="text-xs text-helper">{item.time}</p> : null}
              </div>
              {item.description ? (
                <div className="mt-0.5 text-sm text-muted-foreground">{item.description}</div>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
