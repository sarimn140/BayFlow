'use client'

import { Boxes, PackageCheck, Truck } from 'lucide-react'
import Link from 'next/link'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { orderForJob } from '@/components/pos/purchase-orders/po-model'
import { Button } from '@/components/ui/button'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import {
  getBookings,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  getShopById,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

import {
  QUEUE_STAGES,
  partRequirements,
  partsSummary,
  queueByStage,
  queueSummary,
  type QueueStage,
} from './parts-data'
import { PartsQueueSkeleton, ReadOnlyNotice } from './parts-states'
import { QueueStageCard } from './queue-stage-card'

/**
 * PP-01 Parts queue (spec 10): every job waiting on parts, in three stages — to check against
 * stock, on order from a supplier, ready to allocate — with how many parts stock covers and how
 * long each job has waited. The Owner sees it read-only (D16). Renders this browser's stored
 * data only (a skeleton until then), so nothing flashes.
 */
export function PartsQueue({ shopId }: { shopId: string }) {
  const storeReady = useMockStoreReady()
  const nowIso = useNowMinute()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const bookings = useMockStore(() => getBookings(shopId))
  const inventory = useMockStore(() => getInventory(shopId))
  const purchaseOrders = useMockStore(() => getPurchaseOrders(shopId))

  if (!storeReady || nowIso === null) return <PartsQueueSkeleton />

  const base = `/pos/shops/${encodeURIComponent(shopId)}`
  const readOnly = sectionAccess(user.role, 'parts') === 'read'
  const now = new Date(nowIso)
  const byStage = queueByStage(bookings)
  const counts = Object.fromEntries(
    QUEUE_STAGES.map((stage) => [stage, byStage[stage].length]),
  ) as Record<QueueStage, number>
  const total = QUEUE_STAGES.reduce((sum, stage) => sum + counts[stage], 0)

  return (
    <div className="@container/queue space-y-6">
      <PageHeader
        eyebrow="Parts"
        title="Parts queue"
        description={queueSummary(counts)}
        actions={
          <>
            <Button asChild variant="outline">
              <Link href={`${base}/purchase-orders`}>
                <Truck aria-hidden="true" />
                Purchase orders
              </Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={`${base}/inventory`}>
                <Boxes aria-hidden="true" />
                Inventory
              </Link>
            </Button>
          </>
        }
      />

      {readOnly ? (
        <ReadOnlyNotice>
          Your Parts Person reserves, orders and allocates parts. To act on a booking, open it in{' '}
          <Link href={`${base}/bookings`}>Bookings</Link>.
        </ReadOnlyNotice>
      ) : null}

      {total === 0 ? (
        <EmptyState
          tone="success"
          icon={PackageCheck}
          title="No jobs waiting for parts"
          description="When a service advisor assigns an approved estimate, the job appears here to check against stock."
        />
      ) : (
        <div className="grid items-start gap-6 @4xl/queue:grid-cols-3 @4xl/queue:gap-4">
          {QUEUE_STAGES.map((stage) => (
            <QueueStageCard
              key={stage}
              stage={stage}
              jobs={byStage[stage].map((booking) => ({
                booking,
                summary: partsSummary(partRequirements(booking.estimateItems, inventory)),
              }))}
              now={now}
              timeZone={shop?.timezone}
              base={base}
              // On order: the purchase order each job waits on (D43), when one names it.
              orderOf={
                stage === 'PARTS_ORDERED'
                  ? (bookingId) => orderForJob(bookingId, purchaseOrders)
                  : undefined
              }
            />
          ))}
        </div>
      )}
    </div>
  )
}
