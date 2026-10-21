'use client'

import {
  ArrowRight,
  CalendarDays,
  Car,
  Check,
  CircleCheckBig,
  Copy,
  MapPin,
  NotebookPen,
  SearchX,
  UserRoundCheck,
  Wrench,
} from 'lucide-react'
import Link from 'next/link'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { Handwritten } from '@/components/booking/booking-hero'
import { ShopPhotoBanner, SummaryRow } from '@/components/booking/booking-summary'
import { telHref } from '@/components/booking/shop-card'
import { EmptyState } from '@/components/layout/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { formatDateKey } from '@/lib/booking-slots'
import { getCurrentUser, getCustomerBooking, getShopById, type MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

/** Spec 10 C-03 "What happens next", in the customer's words (UX rule R5: no "QC", no "SA"). */
const NEXT_STEPS = [
  {
    title: 'The shop confirms',
    text: 'A service advisor checks the time and confirms your booking.',
  },
  {
    title: 'A technician inspects your car',
    text: 'They look into what you described and note what the car needs.',
  },
  {
    title: 'You approve the estimate online',
    text: 'You see every part and labour cost. No work starts until you approve.',
  },
  {
    title: 'Repair and quality check',
    text: 'The technician repairs your car, then a quality inspector checks the work.',
  },
  {
    title: 'Pick up your car',
    text: 'We let you know when it’s ready. Confirm in My bookings once you’ve collected it.',
  },
] as const

/**
 * `/book/confirmed/<bookingId>`: C-03, the wizard's success page (spec 10). Waits for this
 * browser's store (a new booking lives only there), then shows the booking or, for an unknown
 * id, an empty state: never a made-up reference.
 */
export function BookingConfirmation({
  bookingId,
  newAccount,
}: {
  bookingId: string
  /** `?new_account=1`: the wizard just created the customer's BayFlow account (D32). */
  newAccount: boolean
}) {
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  // C-03 is for the booking's customer only (D21): anyone else gets the not-found state.
  const booking = useMockStore(() => getCustomerBooking(bookingId, user.email))

  if (!ready) return <ConfirmationSkeleton />
  if (!booking) return <BookingNotFound />
  return <Confirmation booking={booking} newAccount={newAccount} />
}

function Confirmation({ booking, newAccount }: { booking: MockBooking; newAccount: boolean }) {
  const shop = useMockStore(() => getShopById(booking.shopId))

  const vehicle = [
    `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`,
    booking.vehicleColor,
    booking.mileageKm !== undefined ? `${booking.mileageKm.toLocaleString('en')} km` : undefined,
  ]
    .filter(Boolean)
    .join(' · ')
  const awaitingShop = booking.status === 'PENDING'

  return (
    <div className="space-y-6">
      <section
        aria-labelledby="booking-received"
        className="bg-hero rounded-3xl border border-border px-5 py-8 text-center sm:px-10 sm:py-12"
      >
        <span className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-success-subtle text-success-ink">
          <CircleCheckBig className="size-7" aria-hidden />
        </span>
        <h1
          id="booking-received"
          className="mt-5 text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl lg:text-5xl"
        >
          Booking <Handwritten>received</Handwritten>
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-base text-balance text-muted-foreground">
          We’ve sent your booking to{' '}
          <span className="font-semibold text-foreground">{booking.shopName}</span>. A service
          advisor will confirm it shortly.
        </p>

        <ReferenceCopy reference={booking.reference} />

        {newAccount && (
          <Alert variant="success" role="status" className="mx-auto mt-6 max-w-xl text-left">
            <UserRoundCheck aria-hidden />
            <AlertTitle>Your BayFlow account is ready</AlertTitle>
            <AlertDescription>
              Log in with{' '}
              <span className="font-semibold wrap-anywhere text-foreground">
                {booking.customerEmail}
              </span>{' '}
              next time to follow this booking and approve the estimate.
            </AlertDescription>
          </Alert>
        )}

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Button asChild size="lg" className="w-full sm:w-auto">
            <Link href={`/bookings/${booking.id}`}>
              Track your booking
              <ArrowRight aria-hidden />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
            <Link href="/bookings">My bookings</Link>
          </Button>
        </div>
      </section>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22.5rem] xl:gap-8">
        {/* First on phones (what and when matter most), the side column from lg. */}
        <section aria-labelledby="appointment" className="min-w-0 lg:col-start-2 lg:row-start-1">
          <Card className="gap-0 py-0">
            <ShopPhotoBanner
              slug={booking.shopSlug}
              name={shop?.name ?? booking.shopName}
              city={shop?.city}
              label="Your appointment at"
              sizes="(min-width: 1024px) 360px, 100vw"
            />
            <div className="px-5 pb-2 sm:px-6">
              <h2 id="appointment" className="sr-only">
                Your appointment
              </h2>
              <div className="flex items-center justify-between gap-3 border-b border-border-faint py-3.5">
                <span className="text-sm text-muted-foreground">Status</span>
                <StatusBadge status={booking.status} audience="customer" />
              </div>
              <div className="divide-y divide-border-faint">
                <SummaryRow icon={<CalendarDays />} label="Date and time">
                  <span className="font-semibold">
                    {formatDateKey(booking.scheduledDate, true)} · {booking.scheduledTime}
                  </span>
                  <span className="block text-xs text-helper">
                    Shop local time{shop && ` (${shop.timezone})`}
                  </span>
                </SummaryRow>
                {shop && (
                  <SummaryRow icon={<MapPin />} label="Workshop">
                    <span className="block">
                      {shop.address}, {shop.city}
                    </span>
                    <a
                      href={telHref(shop.phone)}
                      className="rounded-sm font-semibold text-brand-blue-ink tabular-nums underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                    >
                      {shop.phone}
                    </a>
                  </SummaryRow>
                )}
                <SummaryRow
                  icon={<Wrench />}
                  label={booking.services.length === 1 ? 'Service' : 'Services'}
                >
                  <ul className="space-y-0.5">
                    {booking.services.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </SummaryRow>
                <SummaryRow icon={<Car />} label="Vehicle">
                  <span className="block font-mono font-semibold">{booking.licensePlate}</span>
                  <span className="block text-muted-foreground">{vehicle}</span>
                </SummaryRow>
                {booking.customerNotes && (
                  <SummaryRow icon={<NotebookPen />} label="Your notes">
                    <p className="whitespace-pre-line text-muted-foreground">
                      {booking.customerNotes}
                    </p>
                  </SummaryRow>
                )}
              </div>
            </div>
          </Card>
        </section>

        <section aria-labelledby="next-steps" className="min-w-0 lg:col-start-1 lg:row-start-1">
          <Card>
            <CardHeader>
              <h2 id="next-steps" className="text-lg leading-7 font-semibold text-foreground">
                What happens next
              </h2>
              <CardDescription>
                Follow every step in My bookings. Nothing is repaired until you approve the price.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ol>
                {NEXT_STEPS.map((step, index) => {
                  const isNext = awaitingShop && index === 0
                  return (
                    <li key={step.title} className="relative flex gap-4 pb-6 last:pb-0">
                      {index < NEXT_STEPS.length - 1 && (
                        <span
                          aria-hidden
                          className="absolute top-12 bottom-1.5 left-5 w-px -translate-x-1/2 bg-border"
                        />
                      )}
                      <span
                        aria-hidden
                        className={cn(
                          'flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                          isNext
                            ? 'bg-brand-blue text-white shadow-md ring-4 shadow-brand-blue/25 ring-brand-blue/15'
                            : 'bg-brand-blue-subtle text-brand-blue-ink',
                        )}
                      >
                        {index + 1}
                      </span>
                      <div className="min-w-0 pt-2">
                        <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold text-foreground">
                          {step.title}
                          {isNext && <Badge variant="brand">Next</Badge>}
                        </h3>
                        <p className="mt-1 text-sm text-muted-foreground">{step.text}</p>
                      </div>
                    </li>
                  )
                })}
              </ol>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  )
}

/** The reference in large mono type with a copy button (spec 09 §4.3 `BookingReference`). */
function ReferenceCopy({ reference }: { reference: string }) {
  const [copied, setCopied] = useState(false)
  const resetTimer = useRef<number | undefined>(undefined)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(reference)
    } catch {
      toast.error('Couldn’t copy the reference. Select it and copy it instead.')
      return
    }
    setCopied(true)
    toast.success('Reference copied')
    window.clearTimeout(resetTimer.current)
    resetTimer.current = window.setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="mx-auto mt-7 flex w-full max-w-sm flex-col items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4 shadow-xs sm:w-fit sm:max-w-none sm:flex-row sm:gap-8 sm:pr-4 sm:pl-6 sm:text-left">
      <div className="min-w-0">
        <p className="text-sm text-muted-foreground">Booking reference</p>
        <p className="font-mono text-2xl font-semibold text-foreground select-all sm:text-3xl">
          {reference}
        </p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={copy}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        {copied ? 'Copied' : 'Copy'}
        <span className="sr-only"> booking reference {reference}</span>
      </Button>
    </div>
  )
}

function BookingNotFound() {
  return (
    <EmptyState
      icon={SearchX}
      title={
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
          We couldn’t find that booking
        </h1>
      }
      description="Check the link, or open My bookings to see every booking on your account."
      action={
        <Button asChild>
          <Link href="/bookings">My bookings</Link>
        </Button>
      }
      className="py-16"
    />
  )
}

function ConfirmationSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-[26rem] rounded-3xl" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22.5rem] xl:gap-8">
        <Skeleton className="h-[30rem] rounded-2xl" />
        <Skeleton className="hidden h-[34rem] rounded-2xl lg:block" />
      </div>
      <span className="sr-only">Loading your booking…</span>
    </div>
  )
}
