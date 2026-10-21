import { CircleCheck, PackageX, TriangleAlert, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'

import type { StockState } from './inventory-model'

/** Spec 09 §3.4 stock vocabulary: soft chips with an icon and a word, never colour alone. */
export const STOCK_META: Record<
  StockState,
  { label: string; variant: 'success' | 'warning' | 'destructive'; icon: LucideIcon }
> = {
  OK: { label: 'In stock', variant: 'success', icon: CircleCheck },
  LOW: { label: 'Low stock', variant: 'warning', icon: TriangleAlert },
  OUT: { label: 'Out of stock', variant: 'destructive', icon: PackageX },
}

/** Ink for an "available" figure in the state's colour (the chip beside it carries the word). */
export const STOCK_INK: Record<StockState, string> = {
  OK: 'text-foreground',
  LOW: 'text-warning-ink',
  OUT: 'text-danger-ink',
}

export function StockBadge({ state, className }: { state: StockState; className?: string }) {
  const { label, variant, icon: Icon } = STOCK_META[state]
  return (
    <Badge variant={variant} className={className}>
      <Icon data-icon="inline-start" aria-hidden="true" />
      {label}
    </Badge>
  )
}
