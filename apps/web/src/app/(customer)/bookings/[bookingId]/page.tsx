'use client'

import {
  Ban,
  CarFront,
  CircleAlert,
  CircleCheck,
  CircleCheckBig,
  ClipboardList,
  ShieldCheck,
} from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useState } from 'react'

import {
  ActionNeededCallout,
  StateBanner,
} from '@/components/customer/booking-detail/booking-banners'
import {
  BookingDetailSkeleton,
  BookingNotFound,
} from '@/components/customer/booking-detail/booking-detail-states'
import { ShopCard, VehicleCard } from '@/components/customer/booking-detail/booking-info-cards'
import { BookingProgress } from '@/components/customer/booking-detail/booking-progress'
import { CopyReferenceButton } from '@/components/customer/booking-detail/copy-reference-button'
import { EstimateCard } from '@/components/customer/booking-detail/estimate-card'
import { bookingSlot, telHref, todaysHours } from '@/components/customer/booking-detail/format'
import { estimateDecisionOf } from '@/components/customer/estimate-decision'
import { DetailLayout, StickyActionBar } from '@/components/layout/detail-layout'
import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { BookingCallsCard } from '@/features/calls/booking-calls-card'
import { CallButton } from '@/features/calls/call-button'
import { getSaRecord } from '@/components/pos/sa-booking/sa-records'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { DEFAULT_SHOP_TZ, formatDateTime, formatPKR } from '@/lib/format'
import { getShopSuspensions } from '@/lib/mock-admin'
import { bookingHistory } from '@/lib/mock-booking-history'
import {
  getCurrentUser,
  getCustomerBooking,
  getShops,
  saveBooking,
  type MockBooking,
} from '@/lib/mock-data'
import { CANCELLABLE_STATUSES, type BookingStatus } from '@/lib/status'

/** What the estimate section says before there is an estimate to show. */
function estimatePlaceholder(status: BookingStatus): { title: string; description: string } {
  if (status === 'ESTIMATE_REVIEW') {
    return {
      title: 'Your estimate is being prepared',
      description: "We'll notify you when it's ready to review.",
    }
  }
  if (status === 'CANCELLED') {
    return {
      title: 'Nothing to approve',
      description: 'This booking is cancelled, so there is no estimate to review.',
    }
  }
  return {
    title: 'Your estimate comes after the inspection',
    description:
      'A technician checks your car first. You will see the price here and approve it before any work starts.',
  }
}

/**
 * Moves focus to the confirmation when it appears (the button that was pressed is gone by then),
 * so keyboard and screen reader users land on the outcome.
 */
function focusOnMount(node: HTMLDivElement | null) {
  node?.focus()
}

export default function CustomerBookingDetailPage() {
  const params = useParams()
  const bookingId = typeof params?.bookingId === 'string' ? params.bookingId : ''

  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  // D21 / SM-17: only the booking's own customer sees it; anyone else gets the not-found state.
  const booking = useMockStore(() => getCustomerBooking(bookingId, user.email))
  const shops = useMockStore(getShops)
  const suspensions = useMockStore(getShopSuspensions)
  // Who declined or cancelled the booking and why, when the shop did (T03, T22): kept by SA-02.
  const saRecord = useMockStore(() => getSaRecord(bookingId))
  const now = useNowMinute()

  const [declineDialogOpen, setDeclineDialogOpen] = useState(false)
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false)
  const [declineReason, setDeclineReason] = useState('')
  const [cancelReason, setCancelReason] = useState('')
  const [actionSuccess, setActionSuccess] = useState<{ title: string; body: string } | null>(null)

  // Until this browser's stored bookings are read, the seed data could show a stale status or
  // "not found" for a booking made in this browser.
  if (!ready) return <BookingDetailSkeleton />
  if (!booking) return <BookingNotFound />

  // Customer Actions: Approve Estimate
  const handleApproveEstimate = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'ESTIMATE_APPROVED',
      estimateApproved: true,
    }
    saveBooking(updated)
    setActionSuccess({
      title: 'Estimate approved — thank you!',
      body: 'The shop will now get the parts ready and start the repair.',
    })
  }

  // Customer Actions: Decline Estimate
  const handleDeclineEstimate = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'ESTIMATE_REJECTED',
      estimateApproved: false,
    }
    saveBooking(updated)
    setDeclineDialogOpen(false)
    setActionSuccess({
      title: 'Estimate declined',
      body: 'The service advisor will review your note and contact you with options.',
    })
  }

  // Customer Actions: Collected Vehicle
  const handleCollectVehicle = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'COMPLETED',
      paidAmount: booking.estimateTotal,
    }
    saveBooking(updated)
    setActionSuccess({
      title: 'Collection confirmed',
      body: `Thank you for choosing ${booking.shopName}. This booking is now complete.`,
    })
  }

  // Customer Actions: Cancel Booking
  const handleCancelBooking = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'CANCELLED',
    }
    saveBooking(updated)
    setCancelDialogOpen(false)
    setActionSuccess({
      title: 'Booking cancelled',
      body: 'Your slot has been released.',
    })
  }

  const status = booking.status
  const shop = shops.find((s) => s.id === booking.shopId || s.slug === booking.shopSlug)
  const shopName = shop?.name ?? booking.shopName
  const timeZone = shop?.timezone ?? DEFAULT_SHOP_TZ
  const shopSuspended = Boolean(suspensions[booking.shopId])
  const isAwaitingEstimate = status === 'AWAITING_CUSTOMER'
  const isReadyForPickup = status === 'READY_FOR_PICKUP'
  // Glossary §3: a customer may cancel until the repair starts (D96: even at a suspended shop).
  const isCancellable = (CANCELLABLE_STATUSES as ReadonlyArray<BookingStatus>).includes(status)

  const history = bookingHistory(booking)
  const reachedAt = (s: BookingStatus) => history.find((step) => step.status === s)?.at
  const decision = estimateDecisionOf(booking)
  const decidedAt =
    decision === 'approved'
      ? reachedAt('ESTIMATE_APPROVED')
      : decision === 'declined'
        ? reachedAt('ESTIMATE_REJECTED')
        : undefined
  const completedAt = status === 'COMPLETED' ? reachedAt('COMPLETED') : undefined
  const cancelledAt = status === 'CANCELLED' ? reachedAt('CANCELLED') : undefined
  // The shop's decline or cancellation, with its reason (spec 10 C-02 "CANCELLED"). Never the
  // advisor's name: the customer's view names the shop only (E-13).
  const shopCancellation = status === 'CANCELLED' ? saRecord.cancellation : undefined
  const slot = bookingSlot(booking.scheduledDate, booking.scheduledTime)
  const vehicle = `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
  const hoursToday = shop && now ? todaysHours(shop, now) : null
  const total = formatPKR(booking.estimateTotal)

  const declineButton = (
    <Button variant="outline" onClick={() => setDeclineDialogOpen(true)} disabled={shopSuspended}>
      Decline
    </Button>
  )
  const approveButton = (
    <Button onClick={handleApproveEstimate} disabled={shopSuspended} className="max-md:flex-1">
      <CircleCheck aria-hidden="true" />
      Approve · {total}
    </Button>
  )
  const bookAgain =
    shopSuspended || !booking.shopSlug ? undefined : (
      <Button asChild>
        <Link href={`/book/${booking.shopSlug}`}>Book again</Link>
      </Button>
    )
  const placeholder = estimatePlaceholder(status)

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: '/bookings', label: 'My bookings' }}
        eyebrow={`Your booking at ${shopName}`}
        title={<span className="font-mono">{booking.reference}</span>}
        badges={
          <>
            <CopyReferenceButton reference={booking.reference} />
            <StatusBadge status={status} audience="customer" size="md" />
          </>
        }
        description={
          <>
            <span className="font-medium text-foreground">{vehicle}</span>, booked for {slot.date}{' '}
            at {slot.time}
            <span className="mt-1 block text-sm text-helper">Times are shop local time.</span>
          </>
        }
        actions={
          // In-app call to the shop's advisors (spec 05 §9.2); the shop's phone when calling is off.
          <CallButton
            target={{ audience: 'customer', reference: booking.reference }}
            counterpart={shopName}
            label="Call the shop"
            fallbackHref={shop?.phone ? telHref(shop.phone) : undefined}
          />
        }
      />

      {actionSuccess ? (
        <Alert
          key={actionSuccess.title}
          ref={focusOnMount}
          tabIndex={-1}
          variant="success"
          className="outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <CircleCheck aria-hidden="true" />
          <AlertTitle>{actionSuccess.title}</AlertTitle>
          <AlertDescription>{actionSuccess.body}</AlertDescription>
        </Alert>
      ) : null}

      {/* D96: while the shop is suspended, only cancelling is possible. */}
      {shopSuspended ? (
        <Alert variant="warning">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{shopName} is temporarily unavailable on BayFlow</AlertTitle>
          <AlertDescription>
            For now you can&apos;t approve or decline an estimate or confirm a pick-up here.
            {isCancellable ? ' You can still cancel this booking.' : null}
          </AlertDescription>
        </Alert>
      ) : null}

      {isAwaitingEstimate && !shopSuspended ? (
        <ActionNeededCallout
          action={
            <Button asChild variant="outline">
              <a href="#estimate">Review estimate</a>
            </Button>
          }
        >
          Your estimate is ready. Approve{' '}
          <span className="font-semibold whitespace-nowrap tabular-nums">{total}</span> to start the
          repair.
        </ActionNeededCallout>
      ) : null}

      {isReadyForPickup ? (
        <StateBanner
          tone="success"
          icon={CarFront}
          title="Your car is ready to collect"
          action={
            <Button size="lg" onClick={handleCollectVehicle} disabled={shopSuspended}>
              I&apos;ve collected my vehicle
            </Button>
          }
        >
          <p>
            It passed the quality check. Collect it from {shopName}
            {shop ? `, ${shop.address}, ${shop.city}` : ''}.
          </p>
          {hoursToday || shop?.phone ? (
            <p className="text-sm">
              {hoursToday?.label}
              {hoursToday && shop?.phone ? ' · ' : null}
              {shop?.phone ? (
                <a
                  href={telHref(shop.phone)}
                  className="-my-2.5 inline-flex min-h-10 items-center rounded-md font-semibold whitespace-nowrap text-foreground underline underline-offset-4 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {shop.phone}
                </a>
              ) : null}
            </p>
          ) : null}
        </StateBanner>
      ) : null}

      {status === 'COMPLETED' ? (
        <StateBanner
          tone="done"
          icon={CircleCheckBig}
          title="This booking is complete"
          action={bookAgain}
        >
          <p>
            {completedAt ? `Completed on ${formatDateTime(completedAt, timeZone)}. ` : null}
            Thank you for choosing {shopName}.
          </p>
        </StateBanner>
      ) : null}

      {status === 'CANCELLED' ? (
        <StateBanner icon={Ban} title="This booking was cancelled" action={bookAgain}>
          <p>
            {shopCancellation
              ? // The same time as the progress timeline's "Booking cancelled" step.
                `${shopName} ${shopCancellation.kind === 'decline' ? 'declined' : 'cancelled'} it on ${formatDateTime(cancelledAt ?? shopCancellation.at, timeZone)}. `
              : cancelledAt
                ? `Cancelled on ${formatDateTime(cancelledAt, timeZone)}. `
                : null}
            The slot was released.
          </p>
          {shopCancellation?.reason.trim() ? (
            <figure className="space-y-1.5 pt-2">
              <figcaption className="text-sm font-medium text-foreground">
                The shop’s reason
              </figcaption>
              <blockquote className="rounded-xl bg-layer px-4 py-3 text-base whitespace-pre-line text-foreground">
                &ldquo;{shopCancellation.reason.trim()}&rdquo;
              </blockquote>
            </figure>
          ) : null}
        </StateBanner>
      ) : null}

      <DetailLayout
        asideFirstOnMobile={!isAwaitingEstimate}
        aside={
          <>
            <BookingProgress booking={booking} timeZone={timeZone} />
            {/* Side by side while the aside spans a wide one-column layout (a tablet); stacked
                on a phone and in the side column (DetailLayout's own width, not the screen's). */}
            <div className="grid gap-6 @min-[36rem]/detail:grid-cols-2 @min-[58rem]/detail:grid-cols-1">
              <VehicleCard booking={booking} />
              <ShopCard shop={shop} shopName={shopName} />
            </div>
          </>
        }
      >
        {/* Only a passed QC is shown: a failed round's issue is a staff note (D92, spec 03 §3.3). */}
        {booking.qcPassed === true && booking.qcNotes ? (
          <Card>
            <CardHeader>
              <h2 className="text-lg leading-7 font-semibold text-foreground">Quality check</h2>
              <CardDescription>Checked by the shop&apos;s quality inspector.</CardDescription>
              <CardAction>
                <Badge variant="success">
                  <ShieldCheck aria-hidden="true" />
                  Passed
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              <p className="rounded-xl bg-layer px-4 py-3.5 text-base text-muted-foreground">
                {booking.qcNotes}
              </p>
            </CardContent>
          </Card>
        ) : null}

        {decision ? (
          <EstimateCard
            booking={booking}
            decision={decision}
            sentAt={reachedAt('AWAITING_CUSTOMER')}
            decidedAt={decidedAt}
            timeZone={timeZone}
            actions={
              isAwaitingEstimate ? (
                <>
                  {declineButton}
                  {approveButton}
                </>
              ) : null
            }
          />
        ) : (
          <Card>
            <CardHeader>
              <h2 className="text-lg leading-7 font-semibold text-foreground">Your estimate</h2>
            </CardHeader>
            <CardContent>
              <EmptyState
                variant="inline"
                tone="neutral"
                icon={ClipboardList}
                title={placeholder.title}
                description={placeholder.description}
                className="p-4 sm:p-6"
              />
            </CardContent>
          </Card>
        )}
        <BookingCallsCard target={{ audience: 'customer', reference: booking.reference }} />
      </DetailLayout>

      {isCancellable ? (
        <Card>
          <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-foreground">Need to cancel?</h2>
              <p className="text-sm text-muted-foreground">
                You can cancel until the repair starts. Your slot will be released.
              </p>
            </div>
            <Button
              variant="destructive-outline"
              onClick={() => setCancelDialogOpen(true)}
              className="max-sm:w-full"
            >
              <Ban aria-hidden="true" />
              Cancel booking
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {/* Phones: the decision stays at the bottom of the screen (spec 10 C-02 Mobile). */}
      {isAwaitingEstimate ? (
        <StickyActionBar className="md:hidden">
          {declineButton}
          {approveButton}
        </StickyActionBar>
      ) : null}

      {/* Decline Estimate Dialog */}
      <Dialog open={declineDialogOpen} onOpenChange={setDeclineDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Decline the estimate for{' '}
              <span className="whitespace-nowrap">{booking.reference}</span>?
            </DialogTitle>
            <DialogDescription>
              Tell the service advisor why you are declining so they can adjust the work or the
              parts. The shop will contact you to revise it.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="decReason">Reason (optional)</FieldLabel>
            <Textarea
              id="decReason"
              value={declineReason}
              onChange={(e) => setDeclineReason(e.target.value)}
              placeholder="For example: skip the cabin filter for now, only replace the brake pads."
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeclineDialogOpen(false)}>
              Go back
            </Button>
            <Button variant="destructive" onClick={handleDeclineEstimate}>
              Decline estimate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel Booking Dialog */}
      <Dialog open={cancelDialogOpen} onOpenChange={setCancelDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Cancel booking <span className="whitespace-nowrap">{booking.reference}</span>?
            </DialogTitle>
            <DialogDescription>
              Your slot at {shopName} will be released. You can book again at any time.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="cncReason">Reason (optional)</FieldLabel>
            <Textarea
              id="cncReason"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              placeholder="For example: rescheduling for next week"
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelDialogOpen(false)}>
              Keep booking
            </Button>
            <Button variant="destructive" onClick={handleCancelBooking}>
              Cancel booking
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
