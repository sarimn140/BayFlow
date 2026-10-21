import { CircleAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * `ActionNeededCallout` (spec 09 §4.11; DESIGN.md §6.13): the attention surface with a one-line
 * message and one CTA. Its text comes from the action the customer may take, never from the status
 * alone. The CTA goes full width on phones (spec 10 C-01 Mobile).
 */
export function ActionNeededCallout({
  children,
  action,
}: {
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-attention-border bg-attention px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:px-5">
      <div className="flex min-w-0 gap-3">
        <CircleAlert className="mt-0.5 size-5 shrink-0 text-cta" aria-hidden="true" />
        <p className="text-base text-foreground">
          <span className="font-semibold text-cta">Action needed: </span>
          {children}
        </p>
      </div>
      {action ? <div className="shrink-0 max-sm:*:w-full">{action}</div> : null}
    </div>
  )
}

const BANNER_TONE = {
  /** Something good the customer acts on now (ready for pick-up). */
  success: {
    surface: 'border-status-handover-border bg-success-subtle',
    tile: 'bg-card text-success-ink',
  },
  /** A finished booking. */
  done: { surface: 'border-border bg-card shadow-xs', tile: 'bg-success-subtle text-success-ink' },
  /** A closed booking. */
  neutral: {
    surface: 'border-border bg-card shadow-xs',
    tile: 'bg-secondary text-muted-foreground',
  },
} as const

/**
 * A state banner under the page header: `ReadyForPickupBanner` (success, spec 09 §4.11) and the
 * closed states of C-02 (cancelled, completed): an icon tile, a title, one or two lines and at
 * most one action.
 */
export function StateBanner({
  icon: Icon,
  title,
  children,
  action,
  tone = 'neutral',
}: {
  icon: LucideIcon
  title: ReactNode
  children?: ReactNode
  action?: ReactNode
  tone?: keyof typeof BANNER_TONE
}) {
  const style = BANNER_TONE[tone]
  return (
    <section
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6',
        style.surface,
      )}
    >
      <div className="flex min-w-0 gap-4">
        <span
          className={cn(
            'flex size-12 shrink-0 items-center justify-center rounded-2xl',
            style.tile,
          )}
        >
          <Icon className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0 space-y-1">
          <h2 className="text-xl leading-7 font-bold text-foreground">{title}</h2>
          {children ? (
            <div className="space-y-1 text-base text-muted-foreground">{children}</div>
          ) : null}
        </div>
      </div>
      {action ? <div className="shrink-0 max-sm:*:w-full">{action}</div> : null}
    </section>
  )
}
