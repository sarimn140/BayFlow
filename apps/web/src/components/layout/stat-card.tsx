import type { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export type StatTone = 'default' | 'brand' | 'success' | 'warning' | 'danger'

const ICON_TONE: Record<StatTone, string> = {
  default: 'bg-secondary text-muted-foreground',
  brand: 'bg-brand-blue-subtle text-brand-blue-ink',
  success: 'bg-success-subtle text-success-ink',
  warning: 'bg-warning-subtle text-warning-ink',
  danger: 'bg-danger-subtle text-danger-ink',
}

export interface StatCardProps {
  /** What is counted, e.g. "Needs action". */
  label: string
  /** The number (use `formatPKR` for money); rendered with tabular figures. */
  value: ReactNode
  icon?: LucideIcon
  /** One short line under the value, e.g. "Intake, estimates and pick-up calls". */
  hint?: ReactNode
  /** Makes the whole card a link to the filtered list it counts. */
  href?: string
  /** Colours the icon tile; `warning` and `danger` also colour the value. */
  tone?: StatTone
  className?: string
}

/** KPI card (DESIGN.md "Stat cards"): label + icon tile, a big number, an optional hint. */
export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  href,
  tone = 'default',
  className,
}: StatCardProps) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {Icon ? (
          <span
            className={cn(
              'flex size-9 shrink-0 items-center justify-center rounded-xl',
              ICON_TONE[tone],
            )}
          >
            <Icon className="size-[18px]" aria-hidden="true" />
          </span>
        ) : null}
      </div>
      <p
        className={cn(
          'text-3xl leading-none font-extrabold tracking-tight tabular-nums',
          tone === 'warning' ? 'text-warning-ink' : tone === 'danger' ? 'text-danger-ink' : '',
          tone !== 'warning' && tone !== 'danger' && 'text-foreground',
        )}
      >
        {value}
      </p>
      {hint ? <p className="text-xs text-helper">{hint}</p> : null}
    </>
  )

  const card =
    'flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-xs transition-[border-color,box-shadow] duration-150'

  if (href) {
    return (
      <Link
        href={href}
        className={cn(
          card,
          'outline-none hover:border-brand-blue/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid',
          className,
        )}
      >
        {body}
      </Link>
    )
  }
  return <div className={cn(card, className)}>{body}</div>
}
