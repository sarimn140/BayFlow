'use client'

import { CircleCheckBig, PackageCheck, SearchX } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { PoItemsCard } from '@/components/pos/purchase-orders/po-items-card'
import {
  formatCount,
  isOpen,
  plural,
  poJob,
  receiptPreview,
  unitsAdded,
  type PoJob,
  type ReceiptLine,
} from '@/components/pos/purchase-orders/po-model'
import { PoStatusBadge } from '@/components/pos/purchase-orders/po-status-badge'
import { PoSummaryCard } from '@/components/pos/purchase-orders/po-summary-card'
import { PoReadOnlyNotice, PurchaseOrderSkeleton } from '@/components/pos/purchase-orders/po-ui'
import { ReceiveDialog } from '@/components/pos/purchase-orders/receive-dialog'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { DEFAULT_SHOP_TZ, formatDate } from '@/lib/format'
import {
  adjustPartStock,
  getBookings,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  getShopById,
  savePurchaseOrder,
  type MockPart,
  type MockPurchaseOrder,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

/**
 * PP-05 PO detail and receive (spec 10): the order's lines in the main column; beside them the
 * state, supplier, total and, for Parts staff while it is open, "Receive into stock", which adds
 * every line's quantity to inventory after a confirmation that shows the stock before → after.
 * The Owner's view is read-only (D16).
 */
export default function PurchaseOrderDetailPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const poId = typeof params?.poId === 'string' ? params.poId : ''

  const ready = useMockStoreReady()
  const pos = useMockStore(() => getPurchaseOrders(shopId))
  // This shop's inventory: receiving adds each line to the shop's own part with that SKU (D20).
  const parts = useMockStore(() => getInventory(shopId))
  // The job the order was raised for (D43), from this shop's bookings only (D20).
  const bookings = useMockStore(() => getBookings(shopId))
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  // Wait for this browser's stored orders: a new order is not in the seed data, so it would
  // flash "not found" while React hydrates.
  if (!ready) return <PurchaseOrderSkeleton />

  const po = pos.find((p) => p.id === poId || p.po_number === poId)

  if (!po) {
    return (
      <Empty className="border bg-card py-16 sm:py-20">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <SearchX aria-hidden="true" />
          </EmptyMedia>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            We couldn’t find this purchase order
          </h1>
          <EmptyDescription className="text-base">
            It may belong to another shop, or the link is out of date.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild size="lg">
            <Link href={`${base}/purchase-orders`}>Back to purchase orders</Link>
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <PurchaseOrderDetail
      key={po.id}
      po={po}
      job={poJob(po, bookings, base, user.role)}
      parts={parts}
      base={base}
      // D16: Parts staff receive deliveries; the Owner follows them (lib/pos-access).
      canReceive={sectionAccess(user.role, 'purchase-orders') === 'manage'}
      timeZone={shop?.timezone ?? DEFAULT_SHOP_TZ}
    />
  )
}

type ReceivedLine = Pick<ReceiptLine, 'line' | 'part'>

function PurchaseOrderDetail({
  po,
  job,
  parts,
  base,
  canReceive,
  timeZone,
}: {
  po: MockPurchaseOrder
  job: PoJob | undefined
  parts: ReadonlyArray<MockPart>
  base: string
  canReceive: boolean
  timeZone: string
}) {
  const [receiveOpen, setReceiveOpen] = useState(false)
  /** The stock preview as the dialog opened, so it stays put while the dialog closes. */
  const [shownPreview, setShownPreview] = useState<ReceiptLine[]>([])
  /** What the last receipt on this page changed, for the confirmation notice. */
  const [received, setReceived] = useState<ReceivedLine[] | null>(null)
  const noticeRef = useRef<HTMLDivElement>(null)
  const receiveButtonRef = useRef<HTMLButtonElement>(null)

  const open = isOpen(po)
  const preview = receiptPreview(po, parts)
  const adding = unitsAdded(preview)

  const openReceive = () => {
    setShownPreview(preview)
    setReceiveOpen(true)
  }

  const handleReceiveAll = () => {
    // A second click while the dialog closes, or another window, may have received it already.
    const latest = getPurchaseOrders().find((p) => p.id === po.id)
    if (!latest || !isOpen(latest)) {
      setReceiveOpen(false)
      toast.info(`${po.po_number} is already received`, {
        description: 'Stock was not changed again.',
      })
      return
    }

    // Receive everything, as before: each line's quantity goes into stock, then the order is
    // RECEIVED. The updated parts feed the confirmation.
    const lines = po.items.map((line) => ({
      line,
      part: adjustPartStock(line.part_sku, line.quantity, po.shopId),
    }))
    const updated: MockPurchaseOrder = {
      ...po,
      status: 'RECEIVED',
    }
    savePurchaseOrder(updated)
    setReceived(lines)
    setReceiveOpen(false)
  }

  const addedNow = received ? unitsAdded(received) : 0

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: `${base}/purchase-orders`, label: 'Purchase orders' }}
        title={<span className="font-mono">{po.po_number}</span>}
        badges={<PoStatusBadge status={po.status} size="md" />}
        description={`${po.supplier} · ordered ${formatDate(po.created_at, timeZone)}`}
      />

      {canReceive ? null : <PoReadOnlyNotice inventoryHref={`${base}/inventory`} />}

      {received ? (
        <Alert
          ref={noticeRef}
          tabIndex={-1}
          variant="success"
          role="status"
          className="outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <CircleCheckBig aria-hidden="true" />
          <AlertTitle>Delivery received</AlertTitle>
          <AlertDescription className="text-pretty">
            <div>
              {addedNow > 0
                ? `${plural(addedNow, 'unit')} added to inventory.`
                : 'No stock changed: none of these parts are in inventory.'}
            </div>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
              {received.map(({ line, part }, index) => (
                <li key={`${line.part_sku}-${index}`}>
                  {line.part_name}:{' '}
                  {part ? (
                    <span className="tabular-nums">now {formatCount(part.on_hand)} on hand</span>
                  ) : (
                    'not in inventory, stock unchanged'
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-2">
              <Link href={`${base}/inventory`}>Open inventory</Link>
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      <DetailLayout
        aside={
          <PoSummaryCard
            po={po}
            job={job}
            timeZone={timeZone}
            canReceive={canReceive}
            action={
              open && canReceive ? (
                <div className="space-y-2">
                  <Button ref={receiveButtonRef} size="lg" className="w-full" onClick={openReceive}>
                    <PackageCheck aria-hidden="true" data-icon="inline-start" />
                    Receive into stock
                  </Button>
                  <p className="text-center text-sm text-muted-foreground">
                    {adding > 0
                      ? `Adds ${plural(adding, 'unit')} to inventory.`
                      : 'None of its parts are in inventory yet.'}
                  </p>
                </div>
              ) : null
            }
          />
        }
      >
        <PoItemsCard po={po} />
      </DetailLayout>

      {canReceive ? (
        <ReceiveDialog
          open={receiveOpen}
          onOpenChange={setReceiveOpen}
          po={po}
          preview={shownPreview}
          onConfirm={handleReceiveAll}
          onCloseAutoFocus={(event) => {
            // Radix only returns focus to a `DialogTrigger`: back to "Receive into stock" after
            // Cancel; after a receipt that button is gone, so to the confirmation instead.
            event.preventDefault()
            const target =
              noticeRef.current ?? receiveButtonRef.current ?? document.getElementById('main')
            target?.focus()
          }}
        />
      ) : null}
    </div>
  )
}
