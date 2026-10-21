'use client'

import { PackageCheck, Plus, SearchX, Truck } from 'lucide-react'
import { useParams, useRouter } from 'next/navigation'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { NewPurchaseOrderDialog } from '@/components/pos/purchase-orders/new-po-dialog'
import { PurchaseOrderRows } from '@/components/pos/purchase-orders/po-list'
import {
  PO_FILTERS,
  filterCounts,
  formatCount,
  matchesFilter,
  matchesQuery,
  poJob,
  sortForList,
  type PoFilter,
} from '@/components/pos/purchase-orders/po-model'
import { PoReadOnlyNotice, PurchaseOrdersSkeleton } from '@/components/pos/purchase-orders/po-ui'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { DEFAULT_SHOP_TZ, formatPKR } from '@/lib/format'
import {
  getBookings,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  getShopById,
  type MockPurchaseOrder,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

function isPoFilter(value: string): value is PoFilter {
  return PO_FILTERS.some((option) => option.value === value)
}

/**
 * PP-04 Purchase orders (spec 10): the shop's orders to suppliers, open ones first and shown by
 * default, with search, the status filter and "New purchase order" for a general restock. Parts
 * staff create and receive; the Owner's view is read-only (D16).
 */
export default function PurchaseOrdersPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const router = useRouter()

  const ready = useMockStoreReady()
  const pos = useMockStore(() => getPurchaseOrders(shopId))
  const inventory = useMockStore(() => getInventory(shopId))
  // The jobs orders were raised for (D43), from this shop's bookings only (D20).
  const bookings = useMockStore(() => getBookings(shopId))
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  const [createOpen, setCreateOpen] = useState(false)
  const [filter, setFilter] = useState<PoFilter>('open')
  const [query, setQuery] = useState('')
  const newOrderRef = useRef<HTMLButtonElement>(null)

  // The seed data stands in for this browser's orders until they load (no flash of stale rows).
  if (!ready) return <PurchaseOrdersSkeleton />

  // D16: Parts staff create and receive purchase orders; the Owner follows them (lib/pos-access).
  const canManage = sectionAccess(user.role, 'purchase-orders') === 'manage'
  const timeZone = shop?.timezone ?? DEFAULT_SHOP_TZ
  const counts = filterCounts(pos)
  const rows = sortForList(pos.filter((po) => matchesFilter(po, filter) && matchesQuery(po, query)))
  const rowsValue = rows.reduce((sum, po) => sum + po.total_amount, 0)
  const searching = query.trim() !== ''

  const handleCreated = (po: MockPurchaseOrder) => {
    setCreateOpen(false)
    // Show the new order: it is open, and a search could hide it.
    setFilter('open')
    setQuery('')
    const line = po.items[0]
    toast.success(`${po.po_number} created`, {
      description: line
        ? `${formatCount(line.quantity)} × ${line.part_name} from ${po.supplier}`
        : po.supplier,
      action: {
        label: 'View',
        onClick: () => router.push(`${base}/purchase-orders/${encodeURIComponent(po.id)}`),
      },
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={canManage ? 'Parts' : 'Role view'}
        title="Purchase orders"
        description={
          canManage
            ? 'Order parts from your suppliers and receive deliveries into stock.'
            : 'What your parts staff ordered from suppliers, and what has arrived.'
        }
        actions={
          canManage ? (
            <Button ref={newOrderRef} onClick={() => setCreateOpen(true)}>
              <Plus aria-hidden="true" data-icon="inline-start" />
              New purchase order
            </Button>
          ) : undefined
        }
      />

      {canManage ? null : <PoReadOnlyNotice inventoryHref={`${base}/inventory`} />}

      {pos.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="No purchase orders yet"
          description={
            canManage
              ? 'They’re created from a job’s parts screen (Order missing parts) or here for restocking.'
              : 'Your parts staff create them from a job’s parts screen or here for restocking.'
          }
        />
      ) : (
        <DataTableCard
          className="@container/po-list"
          toolbar={
            <>
              <TableSearch
                value={query}
                onValueChange={setQuery}
                label="Search purchase orders"
                placeholder="PO number, supplier or part"
              />
              <ToggleGroup
                type="single"
                variant="outline"
                size="sm"
                value={filter}
                onValueChange={(value) => {
                  if (isPoFilter(value)) setFilter(value)
                }}
                aria-label="Show purchase orders"
                className="flex-wrap"
              >
                {PO_FILTERS.map((option) => (
                  <ToggleGroupItem key={option.value} value={option.value} className="px-3.5">
                    {option.label}{' '}
                    <Badge variant="secondary" className="h-5 min-w-5 px-1.5 tabular-nums">
                      {formatCount(counts[option.value])}
                    </Badge>
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
              <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
                <span className="font-semibold text-foreground tabular-nums">
                  {formatCount(rows.length)}
                </span>{' '}
                {rows.length === 1 ? 'order' : 'orders'} ·{' '}
                <span className="font-semibold text-foreground tabular-nums">
                  {formatPKR(rowsValue)}
                </span>
              </p>
            </>
          }
        >
          {rows.length > 0 ? (
            <PurchaseOrderRows
              orders={rows}
              base={base}
              canReceive={canManage}
              timeZone={timeZone}
              jobOf={(po) => poJob(po, bookings, base, user.role)}
            />
          ) : searching ? (
            <EmptyState
              variant="inline"
              icon={SearchX}
              title="No purchase orders match"
              description={`Nothing matches “${query.trim()}”${
                filter === 'all' ? '' : ` in ${filter} orders`
              }. Try another PO number, supplier or part.`}
              action={
                <Button variant="outline" onClick={() => setQuery('')}>
                  Clear search
                </Button>
              }
            />
          ) : filter === 'open' ? (
            <EmptyState
              variant="inline"
              tone="success"
              icon={PackageCheck}
              title="Nothing awaiting delivery"
              description="Every purchase order has been received into stock."
              action={
                <Button variant="outline" onClick={() => setFilter('all')}>
                  Show all orders
                </Button>
              }
            />
          ) : (
            <EmptyState
              variant="inline"
              tone="neutral"
              icon={Truck}
              title="Nothing received yet"
              description="Orders move here once their delivery is received into stock."
              action={
                <Button variant="outline" onClick={() => setFilter('all')}>
                  Show all orders
                </Button>
              }
            />
          )}
        </DataTableCard>
      )}

      {canManage ? (
        <NewPurchaseOrderDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          shopId={shopId}
          inventory={inventory}
          onCreated={handleCreated}
          onCloseAutoFocus={(event) => {
            // Back to "New purchase order" (Radix only returns focus to a `DialogTrigger`).
            event.preventDefault()
            newOrderRef.current?.focus()
          }}
        />
      ) : null}
    </div>
  )
}
