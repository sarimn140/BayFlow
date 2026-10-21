import {
  CircleCheck,
  PackageOpen,
  TriangleAlert,
  Truck,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'

import { plural, type JobHealth, type LineState } from './parts-data'

type ChipVariant = 'success' | 'warning' | 'info' | 'neutral'

interface ChipLook {
  variant: ChipVariant
  icon: LucideIcon
}

function StockBadge({ look, children }: { look: ChipLook; children: string }) {
  const Icon = look.icon
  return (
    <Badge variant={look.variant}>
      <Icon aria-hidden="true" data-icon="inline-start" />
      {children}
    </Badge>
  )
}

const LINE_LOOK: Record<LineState, ChipLook> = {
  'in-stock': { variant: 'success', icon: CircleCheck },
  short: { variant: 'warning', icon: TriangleAlert },
  'on-order': { variant: 'info', icon: Truck },
  allocated: { variant: 'neutral', icon: PackageOpen },
}

/**
 * One required part's stock state (spec 10 PP-02): In stock, Short by N, On order or Allocated.
 * A soft chip with an icon and words, so colour is never the only signal.
 */
export function LineStockChip({ state, shortage }: { state: LineState; shortage: number }) {
  const label =
    state === 'in-stock'
      ? 'In stock'
      : state === 'short'
        ? `Short by ${shortage}`
        : state === 'on-order'
          ? 'On order'
          : 'Allocated'
  return <StockBadge look={LINE_LOOK[state]}>{label}</StockBadge>
}

const JOB_LOOK: Record<JobHealth, ChipLook> = {
  'no-parts': { variant: 'neutral', icon: Wrench },
  'in-stock': { variant: 'success', icon: CircleCheck },
  short: { variant: 'warning', icon: TriangleAlert },
  'on-order': { variant: 'info', icon: Truck },
}

/** A whole job's stock state in the queue: All in stock, 2 parts short, 1 part on order. */
export function JobStockChip({ health, shortCount }: { health: JobHealth; shortCount: number }) {
  const label =
    health === 'no-parts'
      ? 'No parts needed'
      : health === 'in-stock'
        ? 'All in stock'
        : health === 'short'
          ? `${plural(shortCount, 'part')} short`
          : `${plural(shortCount, 'part')} on order`
  return <StockBadge look={JOB_LOOK[health]}>{label}</StockBadge>
}
