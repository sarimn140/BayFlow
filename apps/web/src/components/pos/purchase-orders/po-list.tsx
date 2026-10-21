import { ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDate, formatPKR } from '@/lib/format'
import type { MockPurchaseOrder } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { contentsLabel, isOpen, type PoJob } from './po-model'
import { PoStatusBadge } from './po-status-badge'

/** Focus ring for a text link inside a row (DESIGN.md §2.7). */
const LINK_FOCUS =
  'rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

function partNames(po: MockPurchaseOrder): string {
  return po.items.map((line) => line.part_name).join(', ')
}

/**
 * The purchase orders (spec 10 PP-04) inside the `@container/po-list` table card: stacked rows
 * that open the order while the card is narrow (phones, tablets, 1280px laptops with the
 * sidebar open), the data table once it is 1024px wide. In the table the Items column takes the
 * room that is left and truncates, so the row never scrolls sideways. `canReceive` labels an open
 * order's action "Receive" (Parts staff); the Owner's read-only view says "View". `jobOf` names
 * the job an order was raised for (D43): a link in the table's Job column; in a stacked row, which
 * is one link to the order, its reference as text (the order page links it).
 */
export function PurchaseOrderRows({
  orders,
  base,
  canReceive,
  timeZone,
  jobOf,
}: {
  orders: ReadonlyArray<MockPurchaseOrder>
  base: string
  canReceive: boolean
  timeZone: string
  jobOf: (po: MockPurchaseOrder) => PoJob | undefined
}) {
  const href = (po: MockPurchaseOrder) => `${base}/purchase-orders/${encodeURIComponent(po.id)}`

  return (
    <>
      <ul className="divide-y divide-border-faint @5xl/po-list:hidden" aria-label="Purchase orders">
        {orders.map((po) => {
          const job = jobOf(po)
          return (
            <li key={po.id}>
              <Link
                href={href(po)}
                className="group flex items-center gap-3 px-5 py-4 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6"
              >
                <span className="flex min-w-0 flex-1 flex-col gap-2 @xl/po-list:flex-row @xl/po-list:items-center @xl/po-list:gap-4">
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono text-sm font-semibold text-brand-blue-ink">
                        {po.po_number}
                      </span>
                      <PoStatusBadge status={po.status} />
                    </span>
                    <span className="block truncate text-sm font-medium text-foreground">
                      {po.supplier}
                    </span>
                    <span className="block truncate text-xs text-helper">
                      {contentsLabel(po)} · {partNames(po)}
                    </span>
                    {job ? (
                      <span className="block truncate text-xs text-helper">
                        For job{' '}
                        <span className="font-mono font-medium text-foreground">
                          {job.reference}
                        </span>{' '}
                        · {job.vehicle}
                      </span>
                    ) : null}
                  </span>
                  <span className="flex shrink-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 @xl/po-list:flex-col @xl/po-list:items-end">
                    <span className="text-sm font-semibold text-foreground tabular-nums">
                      {formatPKR(po.total_amount)}
                    </span>
                    <span className="text-xs text-helper">
                      Ordered {formatDate(po.created_at, timeZone)}
                    </span>
                  </span>
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </Link>
            </li>
          )
        })}
      </ul>

      <div className="hidden @5xl/po-list:block">
        <Table>
          <TableCaption className="sr-only">Purchase orders, open orders first</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>PO number</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>Job</TableHead>
              <TableHead>Items</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead className="w-0">
                <span className="sr-only">Action</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {orders.map((po) => {
              const receive = canReceive && isOpen(po)
              const job = jobOf(po)
              return (
                <TableRow key={po.id}>
                  <TableCell className="py-3">
                    <Link
                      href={href(po)}
                      className={cn(
                        'font-mono font-semibold text-brand-blue-ink hover:underline',
                        LINK_FOCUS,
                      )}
                    >
                      {po.po_number}
                    </Link>
                    <p className="text-xs text-helper">
                      Ordered {formatDate(po.created_at, timeZone)}
                    </p>
                  </TableCell>
                  <TableCell className="py-3 font-medium">
                    <span className="block max-w-52 truncate" title={po.supplier}>
                      {po.supplier}
                    </span>
                  </TableCell>
                  <TableCell className="py-3">
                    {job ? (
                      <>
                        <Link
                          href={job.href}
                          className={cn(
                            'font-mono font-semibold whitespace-nowrap text-brand-blue-ink hover:underline',
                            LINK_FOCUS,
                          )}
                        >
                          {job.reference}
                        </Link>
                        <p className="max-w-40 truncate text-xs text-helper" title={job.vehicle}>
                          {job.vehicle}
                        </p>
                      </>
                    ) : (
                      // No `bookingId`: a general restock (PP-04 "New purchase order").
                      <span className="text-helper">
                        {po.bookingId ? 'Unknown job' : 'Restock'}
                      </span>
                    )}
                  </TableCell>
                  {/* `w-full max-w-0`: this column takes the leftover width and truncates. */}
                  <TableCell className="w-full max-w-0 py-3">
                    <p className="truncate" title={partNames(po)}>
                      {partNames(po)}
                    </p>
                    <p className="text-xs text-helper tabular-nums">{contentsLabel(po)}</p>
                  </TableCell>
                  <TableCell className="py-3">
                    <PoStatusBadge status={po.status} />
                  </TableCell>
                  <TableCell className="py-3 text-right font-semibold tabular-nums">
                    {formatPKR(po.total_amount)}
                  </TableCell>
                  <TableCell className="py-3 text-right">
                    <Button asChild variant="outline" className="min-w-28">
                      <Link href={href(po)}>
                        {receive ? 'Receive' : 'View'}{' '}
                        <span className="sr-only">{po.po_number}</span>
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </>
  )
}
