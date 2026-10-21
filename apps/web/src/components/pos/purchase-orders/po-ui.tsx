import { Eye } from 'lucide-react'
import Link from 'next/link'

import { DetailLayout } from '@/components/layout/detail-layout'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * `ReadOnlyBanner` (spec 09 §4.11) on the Owner's view of the purchase orders (D16): the Owner
 * follows them, Parts staff create and receive them; the catalogue stays editable in Inventory.
 */
export function PoReadOnlyNotice({ inventoryHref }: { inventoryHref: string }) {
  return (
    <Alert variant="info">
      <Eye aria-hidden="true" />
      <AlertTitle>Read-only view</AlertTitle>
      <AlertDescription>
        <p>
          Parts staff create purchase orders and receive deliveries into stock. You can edit the
          parts catalogue in <Link href={inventoryHref}>Inventory</Link>.
        </p>
      </AlertDescription>
    </Alert>
  )
}

/** PP-04 while this browser's stored orders load (DESIGN.md §6.9): header, toolbar, rows. */
export function PurchaseOrdersSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      {/* PageHeader's own wrap: the button beside the title only while both fit. */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-[1_1_24rem] space-y-3">
          <Skeleton className="h-4 w-14 rounded-full" />
          <Skeleton className="h-10 w-64 max-w-full" />
          <Skeleton className="h-5 w-96 max-w-full" />
        </div>
        <Skeleton className="h-10.5 w-52 rounded-full" />
      </div>
      <div className="overflow-clip rounded-2xl border border-border bg-card shadow-xs">
        {/* The toolbar: 40px controls (DESIGN.md §5 `DataTableCard`). */}
        <div className="flex flex-col gap-3 border-b border-border-faint px-5 py-3 sm:flex-row sm:items-center">
          <Skeleton className="h-10 w-full rounded-full sm:w-72" />
          <Skeleton className="h-10 w-72 max-w-full rounded-full" />
        </div>
        <div className="divide-y divide-border-faint">
          {[0, 1, 2].map((row) => (
            <div key={row} className="flex items-center gap-4 px-5 py-4 sm:px-6">
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-44 max-w-full" />
                <Skeleton className="h-4 w-72 max-w-full" />
              </div>
              <Skeleton className="h-6 w-20 rounded-full" />
            </div>
          ))}
        </div>
      </div>
      <span className="sr-only">Loading purchase orders…</span>
    </div>
  )
}

/**
 * PP-05 while the order loads: header, then the page's `DetailLayout` — the summary card first,
 * beside the items card in two columns.
 */
export function PurchaseOrderSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-4 w-36 rounded-full" />
        <Skeleton className="h-4 w-28 rounded-full" />
        <div className="flex flex-wrap items-center gap-3">
          <Skeleton className="h-10 w-64 max-w-full" />
          <Skeleton className="h-7 w-24 rounded-full" />
        </div>
        <Skeleton className="h-5 w-80 max-w-full" />
      </div>
      <DetailLayout aside={<Skeleton className="h-80 rounded-2xl" />}>
        <Skeleton className="h-96 rounded-2xl" />
      </DetailLayout>
      <span className="sr-only">Loading the purchase order…</span>
    </div>
  )
}
