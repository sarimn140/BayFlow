import { Package } from 'lucide-react'
import type { ReactNode } from 'react'

import { EmptyState } from '@/components/layout/empty-state'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatPKR } from '@/lib/format'
import type { MockPurchaseOrder } from '@/lib/mock-data'

import { formatCount, lineTotal, plural, unitCount } from './po-model'

/** A card title that is an `<h2>` in the page outline (`CardTitle` is a plain `div`). */
export function PoCardHeading({ children }: { children: ReactNode }) {
  return (
    <CardTitle>
      <h2 className="font-semibold">{children}</h2>
    </CardTitle>
  )
}

/**
 * The order's lines (spec 10 PP-05) in a flush card that is its own `@container`: stacked rows
 * while the card is narrow (phones, tablets, the two-column layout below about 1400px), the data
 * table once it is 672px wide. Part, SKU (mono), ordered quantity, unit cost, line total and the
 * order total, money right-aligned in tabular figures.
 */
export function PoItemsCard({ po }: { po: MockPurchaseOrder }) {
  const units = unitCount(po)

  return (
    <Card className="@container/po-items gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <PoCardHeading>Items</PoCardHeading>
        <CardDescription>
          {plural(po.items.length, 'part')} · {plural(units, 'unit')} ordered
        </CardDescription>
      </CardHeader>

      {po.items.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={Package}
          title="No items on this order"
          description="There is nothing to receive."
        />
      ) : (
        <>
          <ul
            className="divide-y divide-border-faint @2xl/po-items:hidden"
            aria-label={`Items on ${po.po_number}`}
          >
            {po.items.map((line, index) => (
              <li
                key={`${line.part_sku}-${index}`}
                className="flex items-start justify-between gap-4 px-5 py-4 sm:px-6"
              >
                <div className="min-w-0 space-y-1">
                  <p className="text-base leading-6 font-medium text-foreground">
                    {line.part_name}
                  </p>
                  <p className="text-sm text-muted-foreground tabular-nums">
                    <span className="font-mono">{line.part_sku}</span> ·{' '}
                    {formatCount(line.quantity)} × {formatPKR(line.unit_price)}
                  </p>
                </div>
                <p className="shrink-0 pt-0.5 text-base font-semibold text-foreground tabular-nums">
                  {formatPKR(lineTotal(line))}
                </p>
              </li>
            ))}
          </ul>
          <div className="flex items-baseline justify-between gap-4 border-t border-border-faint bg-muted px-5 py-4 sm:px-6 @2xl/po-items:hidden">
            <span className="text-base font-semibold text-foreground">Order total</span>
            <span className="text-lg font-bold text-foreground tabular-nums">
              {formatPKR(po.total_amount)}
            </span>
          </div>

          <div className="hidden @2xl/po-items:block">
            <Table>
              <TableCaption className="sr-only">Items on {po.po_number}</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>Part</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead className="text-right">Ordered</TableHead>
                  <TableHead className="text-right">Unit cost</TableHead>
                  <TableHead className="text-right">Line total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {po.items.map((line, index) => (
                  <TableRow key={`${line.part_sku}-${index}`}>
                    <TableCell className="min-w-48 font-medium whitespace-normal">
                      {line.part_name}
                    </TableCell>
                    <TableCell className="font-mono text-muted-foreground">
                      {line.part_sku}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCount(line.quantity)}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {formatPKR(line.unit_price)}
                    </TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {formatPKR(lineTotal(line))}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
              <TableFooter>
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={2} className="text-base">
                    Order total
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatCount(units)}{' '}
                    <span className="sr-only">{units === 1 ? 'unit' : 'units'}</span>
                  </TableCell>
                  <TableCell />
                  <TableCell className="text-right text-lg font-bold tabular-nums">
                    {formatPKR(po.total_amount)}
                  </TableCell>
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </>
      )}
    </Card>
  )
}
