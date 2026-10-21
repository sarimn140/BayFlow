'use client'

import { CircleCheck, PackageCheck, PackageOpen, ShoppingCart, Truck } from 'lucide-react'
import Link from 'next/link'
import { useRef, useState, type ComponentProps, type ReactNode } from 'react'

import { DetailLayout, StickyActionBar, detailLayoutOnly } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { newPurchaseOrderIdentity } from '@/components/pos/purchase-orders/po-model'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import type { DialogContent } from '@/components/ui/dialog'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import {
  getBookingById,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  saveBooking,
  savePurchaseOrder,
  type MockPurchaseOrder,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

import { JobCard, NextStepCard, nextStepFor } from './job-aside'
import { AllocateDialog, MarkReadyDialog, OrderPartsDialog } from './parts-dialogs'
import {
  jobStage,
  orderTotal,
  partRequirements,
  partsSummary,
  plural,
  vehicleLabel,
} from './parts-data'
import { PartsJobNotFound, PartsJobSkeleton, ReadOnlyNotice } from './parts-states'
import { RequirementsCard } from './requirements-card'

type ActionDialog = 'order' | 'ready' | 'allocate'

interface Notice {
  title: string
  body: string
  /** The job left the queue (spec 09 §4.6 rule 4): offer the way back. */
  backToQueue?: boolean
}

type CloseAutoFocusEvent = Parameters<
  NonNullable<ComponentProps<typeof DialogContent>['onCloseAutoFocus']>
>[0]

export interface PartsJobProps {
  shopId: string
  bookingId: string
}

/**
 * PP-02 Parts job (spec 10): the approved estimate's parts against stock, then the one next
 * action — order the missing parts, mark the parts ready, or allocate them to the technician.
 * The Owner sees it read-only (D16). Renders this browser's stored data only (a skeleton until
 * then), so the seed status never flashes.
 */
export function PartsJob({ shopId, bookingId }: PartsJobProps) {
  const storeReady = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const booking = useMockStore(() => getBookingById(bookingId))
  const inventory = useMockStore(() => getInventory(shopId))
  const purchaseOrders = useMockStore(() => getPurchaseOrders(shopId))

  const [openDialog, setOpenDialog] = useState<ActionDialog | null>(null)
  const [supplierName, setSupplierName] = useState('Toyota Genuine Parts Wholesale')
  const [notice, setNotice] = useState<Notice | null>(null)
  const noticeRef = useRef<HTMLDivElement>(null)
  // The button that opened the dialog. Radix only returns focus to a `DialogTrigger`, and these
  // buttons sit outside the dialogs (in the next-step card and the phone action bar).
  const openerRef = useRef<HTMLElement | null>(null)
  // Set by a confirmed action: once its dialog has closed, focus goes to the outcome instead of
  // the opener (which the new status may have replaced).
  const focusNoticeOnClose = useRef(false)

  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  if (!storeReady) return <PartsJobSkeleton />
  // D20: a booking of another shop reads as not found, never as someone else's data.
  if (!booking || (booking.shopId !== shopId && booking.shopSlug !== shopId)) {
    return <PartsJobNotFound queueHref={`${base}/parts`} />
  }

  const readOnly = sectionAccess(user.role, 'parts') === 'read'
  const rows = partRequirements(booking.estimateItems, inventory)
  const summary = partsSummary(rows)
  const stage = jobStage(booking.status)
  const technicianName = booking.assignedTechnicianName || null
  const technician = technicianName ?? 'the technician'
  const step = nextStepFor(stage, summary, technician, booking.status)

  const openDialogFrom = (dialog: ActionDialog, opener: HTMLElement) => {
    openerRef.current = opener
    setOpenDialog(dialog)
  }

  const closeDialog = (open: boolean) => {
    if (!open) setOpenDialog(null)
  }

  const showOutcome = (next: Notice) => {
    focusNoticeOnClose.current = true
    setOpenDialog(null)
    setNotice(next)
  }

  /** After a dialog closes: focus the outcome of a confirmed action, else the opener again. */
  const handleCloseAutoFocus = (event: CloseAutoFocusEvent) => {
    event.preventDefault()
    if (focusNoticeOnClose.current) {
      focusNoticeOnClose.current = false
      noticeRef.current?.focus()
    } else {
      openerRef.current?.focus()
    }
  }

  // Actions: the same writes as before the redesign (mock E-37 `order-parts`,
  // `mark-parts-ready`, `allocate-parts`).
  const handleCreatePo = () => {
    const shortRows = rows.filter((r) => r.shortage > 0)
    const newPo: MockPurchaseOrder = {
      // Never a number already in use: saving replaces the shop's order with the same number.
      ...newPurchaseOrderIdentity(getPurchaseOrders()),
      shopId,
      // D43: an order raised by `order-parts` belongs to its job (PP-02, PP-04, PP-05 link it).
      bookingId: booking.id,
      supplier: supplierName.trim(),
      created_at: new Date().toISOString(),
      status: 'ORDERED',
      items: shortRows.map((r) => ({
        part_sku: r.sku,
        part_name: r.description,
        quantity: r.shortage,
        unit_price: r.unitCost,
      })),
      total_amount: orderTotal(shortRows),
    }

    savePurchaseOrder(newPo)

    // Update booking status to PARTS_ORDERED
    saveBooking({
      ...booking,
      status: 'PARTS_ORDERED',
    })

    showOutcome({
      title: `Purchase order ${newPo.po_number} created`,
      body: `${plural(shortRows.length, 'part')} ordered from ${newPo.supplier || 'the supplier'}. ${booking.reference} is now Parts ordered — receive the delivery on the purchase order when it arrives.`,
    })
  }

  const handleMarkReady = () => {
    saveBooking({
      ...booking,
      status: 'PARTS_READY',
    })
    showOutcome({
      title: 'Parts ready',
      body: `${booking.reference} is ready to allocate. Hand the parts to ${technician} to start the repair.`,
    })
  }

  const handleAllocateParts = () => {
    saveBooking({
      ...booking,
      status: 'IN_REPAIR',
    })
    showOutcome({
      title: `Parts allocated — ${booking.reference} is in repair`,
      body: `${technicianName ?? 'The technician'} has the parts and can start the repair. The job has left your queue.`,
      backToQueue: true,
    })
  }

  // The view's one primary action (R7), plus at most one outline action (spec 09 §4.6).
  let primary: ReactNode = null
  let secondary: ReactNode = null
  if (!readOnly) {
    const markReady = (variant: 'default' | 'outline') => (
      <Button
        key="mark-ready"
        variant={variant}
        onClick={(event) => openDialogFrom('ready', event.currentTarget)}
      >
        <PackageCheck aria-hidden="true" />
        Mark parts ready
      </Button>
    )
    if (stage === 'check') {
      primary = summary.allAvailable ? (
        markReady('default')
      ) : (
        <Button key="order" onClick={(event) => openDialogFrom('order', event.currentTarget)}>
          <ShoppingCart aria-hidden="true" />
          Order missing parts
        </Button>
      )
    } else if (stage === 'ordered') {
      if (summary.allAvailable) {
        primary = markReady('default')
      } else {
        // The job's own open order when it is known, else the list to find it in.
        const jobOrder = purchaseOrders.find(
          (po) => po.bookingId === booking.id && po.status !== 'RECEIVED',
        )
        primary = (
          <Button key="receive" asChild>
            <Link
              href={
                jobOrder
                  ? `${base}/purchase-orders/${encodeURIComponent(jobOrder.id)}`
                  : `${base}/purchase-orders`
              }
            >
              <Truck aria-hidden="true" />
              {jobOrder ? `Open ${jobOrder.po_number}` : 'Open purchase orders'}
            </Link>
          </Button>
        )
        secondary = markReady('outline')
      }
    } else if (stage === 'ready') {
      primary = (
        <Button key="allocate" onClick={(event) => openDialogFrom('allocate', event.currentTarget)}>
          <PackageOpen aria-hidden="true" />
          Allocate parts
        </Button>
      )
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: `${base}/parts`, label: 'Parts queue' }}
        eyebrow="Parts job"
        title={<span className="font-mono">{booking.reference}</span>}
        badges={<StatusBadge status={booking.status} audience="staff" size="md" />}
        description={
          <>
            <span className="font-medium text-foreground">{vehicleLabel(booking)}</span>
            {' · '}
            <span className="font-mono">{booking.licensePlate}</span>
            {' · '}
            {technicianName ? `Technician ${technicianName}` : 'No technician yet'}
          </>
        }
      />

      {notice ? (
        <Alert
          key={notice.title}
          ref={noticeRef}
          tabIndex={-1}
          variant="success"
          className="outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <CircleCheck aria-hidden="true" />
          <AlertTitle>{notice.title}</AlertTitle>
          <AlertDescription>
            <p>
              {notice.body}
              {notice.backToQueue ? (
                <>
                  {' '}
                  <Link href={`${base}/parts`}>Back to the parts queue</Link>
                </>
              ) : null}
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      {readOnly ? (
        <ReadOnlyNotice>
          Your Parts Person reserves, orders and allocates parts. To act on this booking, open it in{' '}
          <Link href={`${base}/bookings/${encodeURIComponent(booking.id)}`}>Bookings</Link>.
        </ReadOnlyNotice>
      ) : null}

      {/* The job card sits in the aside while the layout has two columns; in one column it comes
          after the parts (the reason for this page), so a phone or tablet reads: next step,
          parts, then the job. */}
      <DetailLayout
        aside={
          // A flex gap, not `space-y`: the hidden job card must not leave a margin behind.
          <div className="flex flex-col gap-6">
            <NextStepCard step={step} primary={primary} secondary={secondary} />
            <JobCard booking={booking} className={detailLayoutOnly.twoColumns} />
          </div>
        }
      >
        <RequirementsCard
          reference={booking.reference}
          rows={rows}
          summary={summary}
          stage={stage}
          technician={technician}
        />
        <JobCard booking={booking} className={detailLayoutOnly.oneColumn} />
      </DetailLayout>

      {/* Phones: the main decision stays at the bottom of the screen (DESIGN.md §6.11); an
          outline alternative stays in the next-step card. */}
      {primary ? <StickyActionBar className="*:flex-1 md:hidden">{primary}</StickyActionBar> : null}

      {!readOnly ? (
        <>
          <OrderPartsDialog
            open={openDialog === 'order'}
            onOpenChange={closeDialog}
            reference={booking.reference}
            onConfirm={handleCreatePo}
            onCloseAutoFocus={handleCloseAutoFocus}
            short={summary.short}
            supplier={supplierName}
            onSupplierChange={setSupplierName}
          />
          <MarkReadyDialog
            open={openDialog === 'ready'}
            onOpenChange={closeDialog}
            reference={booking.reference}
            onConfirm={handleMarkReady}
            onCloseAutoFocus={handleCloseAutoFocus}
            requiredCount={summary.requiredCount}
            short={summary.short}
            technician={technician}
          />
          <AllocateDialog
            open={openDialog === 'allocate'}
            onOpenChange={closeDialog}
            reference={booking.reference}
            onConfirm={handleAllocateParts}
            onCloseAutoFocus={handleCloseAutoFocus}
            rows={rows}
            technician={technician}
          />
        </>
      ) : null}
    </div>
  )
}
