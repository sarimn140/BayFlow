import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { cn } from '@/lib/utils'

const ICON_TONE = {
  brand: '',
  success: 'bg-success-subtle text-success-ink',
  neutral: 'bg-secondary text-muted-foreground',
} as const

export interface EmptyStateProps {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  /** One action: "Add service" (first use), "Clear filters" (no results). None for "all done". */
  action?: ReactNode
  /** `brand` first use / no results; `success` all done; `neutral` nothing to show. */
  tone?: keyof typeof ICON_TONE
  /** `card`: a dashed card on the canvas; `inline`: inside another card (no border). */
  variant?: 'card' | 'inline'
  className?: string
}

/** Empty state (DESIGN.md "Empty states"): icon tile, title, one sentence, at most one action. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = 'brand',
  variant = 'card',
  className,
}: EmptyStateProps) {
  return (
    <Empty className={cn(variant === 'card' ? 'border bg-card' : 'p-8 sm:p-10', className)}>
      <EmptyHeader>
        {Icon ? (
          <EmptyMedia variant="icon" className={ICON_TONE[tone]}>
            <Icon aria-hidden="true" />
          </EmptyMedia>
        ) : null}
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  )
}
