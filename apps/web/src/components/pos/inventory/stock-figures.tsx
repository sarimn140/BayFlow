import type { ReactNode } from 'react'

import type { MockPart } from '@/lib/mock-data'

import { availableOf } from './inventory-model'

/** A part's on hand, reserved and available counts in a paper well (DESIGN.md "Paper"). */
export function StockFigures({
  part,
  children,
}: {
  part: Pick<MockPart, 'on_hand' | 'reserved'>
  /** One line under the figures. */
  children?: ReactNode
}) {
  return (
    <div className="space-y-3 rounded-xl bg-layer px-4 py-3.5">
      <dl className="grid grid-cols-3 gap-3">
        <Figure label="On hand" value={part.on_hand} />
        <Figure label="Reserved" value={part.reserved} />
        <Figure label="Available" value={Math.max(availableOf(part), 0)} />
      </dl>
      {children}
    </div>
  )
}

function Figure({ label, value }: { label: string; value: number }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-lg font-bold text-foreground tabular-nums">{value}</dd>
    </div>
  )
}
