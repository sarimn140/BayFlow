import { Wrench } from 'lucide-react'

import { EmptyState } from '@/components/layout/empty-state'
import { Card, CardDescription, CardHeader } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

import {
  availabilityLabel,
  availablePercent,
  lineState,
  plural,
  shortList,
  type JobStage,
  type PartRequirement,
  type PartsSummary,
} from './parts-data'
import { CardHeading } from './parts-states'
import { LineStockChip } from './stock-chip'

/** D31: a labour-only job still passes the parts steps; say what that means at each stage. */
const LABOUR_ONLY: Record<JobStage, string> = {
  'not-yet': 'Nothing to reserve or order for this job.',
  check: 'Mark parts ready, then allocate to release the job to repair.',
  ordered: 'Mark parts ready, then allocate to release the job to repair.',
  ready: 'Allocate to release the job to repair.',
  allocated: 'This job needed labour only.',
  cancelled: 'Nothing to reserve or order for this job.',
}

function SkuLine({ row }: { row: PartRequirement }) {
  return row.inInventory ? (
    <p className="font-mono text-xs text-helper">{row.sku}</p>
  ) : (
    <p className="text-xs text-helper">Not in inventory</p>
  )
}

export interface RequirementsCardProps {
  reference: string
  rows: ReadonlyArray<PartRequirement>
  summary: PartsSummary
  stage: JobStage
  technician: string
}

/**
 * Required vs available (spec 10 PP-02): the approved estimate's parts against stock on hand,
 * with a summary line ("2 of 3 parts in stock — short: ignition coil × 1"), then a table when
 * the card is at least 40rem wide, else a card per part with a three-up stat row. The card's own
 * width decides (a container query): beside the aside on a laptop the column can be phone-narrow.
 */
export function RequirementsCard({
  reference,
  rows,
  summary,
  stage,
  technician,
}: RequirementsCardProps) {
  const allocated = stage === 'allocated'

  return (
    <Card className="@container/parts gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading id="required-parts">Required parts</CardHeading>
        <CardDescription>
          From the approved estimate, compared with the stock on hand.
        </CardDescription>
      </CardHeader>

      {rows.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={Wrench}
          title="No parts on the approved estimate"
          description={LABOUR_ONLY[stage]}
        />
      ) : (
        <>
          <div className="space-y-2.5 border-b border-border-faint px-5 py-4 sm:px-6">
            {allocated ? (
              <p className="text-sm font-semibold text-foreground">
                {plural(summary.requiredCount, 'part')} handed to {technician}
              </p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  <span className="font-semibold text-foreground tabular-nums">
                    {availabilityLabel(summary)}
                  </span>
                  {summary.short.length > 0 ? (
                    <>
                      {' — short: '}
                      {shortList(summary.short)}
                    </>
                  ) : null}
                </p>
                <Progress
                  value={availablePercent(summary)}
                  aria-labelledby="required-parts"
                  aria-valuetext={availabilityLabel(summary)}
                />
              </>
            )}
          </div>

          {/* Narrow: a card per part with the three numbers side by side. */}
          <ul className="divide-y divide-border-faint @min-[40rem]/parts:hidden">
            {rows.map((row) => {
              const state = lineState(row, stage)
              const stats = [
                { label: 'Required', value: row.required },
                { label: 'On hand', value: row.onHand },
                { label: 'Short by', value: row.shortage },
              ]
              return (
                <li key={row.id} className="space-y-3 px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 space-y-0.5">
                      <p className="text-sm font-medium text-foreground">{row.description}</p>
                      <SkuLine row={row} />
                    </div>
                    <LineStockChip state={state} shortage={row.shortage} />
                  </div>
                  <dl className="grid grid-cols-3 gap-2">
                    {stats.map((stat) => (
                      <div key={stat.label} className="rounded-xl bg-layer px-3 py-2">
                        <dt className="text-xs text-muted-foreground">{stat.label}</dt>
                        <dd
                          className={cn(
                            'text-lg font-bold text-foreground tabular-nums',
                            stat.label === 'Short by' &&
                              (state === 'short' || state === 'on-order') &&
                              'text-warning-ink',
                          )}
                        >
                          {stat.value}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </li>
              )
            })}
          </ul>

          {/* Wide: the table. */}
          <div className="hidden @min-[40rem]/parts:block">
            <Table>
              <TableCaption className="sr-only">
                Required parts for {reference}, compared with the stock on hand
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Part</TableHead>
                  <TableHead className="text-right">Required</TableHead>
                  <TableHead className="text-right">On hand</TableHead>
                  <TableHead className="text-right">Short by</TableHead>
                  <TableHead>Stock</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => {
                  const state = lineState(row, stage)
                  return (
                    <TableRow key={row.id}>
                      <TableCell className="py-3 whitespace-normal">
                        <p className="font-medium text-foreground">{row.description}</p>
                        <SkuLine row={row} />
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{row.required}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.onHand}</TableCell>
                      <TableCell
                        className={cn(
                          'text-right tabular-nums',
                          state === 'short' || state === 'on-order'
                            ? 'font-semibold text-warning-ink'
                            : 'text-muted-foreground',
                        )}
                      >
                        {row.shortage}
                      </TableCell>
                      <TableCell>
                        <LineStockChip state={state} shortage={row.shortage} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </Card>
  )
}
