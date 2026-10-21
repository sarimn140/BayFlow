'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { AlertCircle, ArrowLeft, ArrowRight, Check, MapPin } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FormProvider, useForm, useWatch, type FieldErrors } from 'react-hook-form'

import { BookingHero, Handwritten, HeroBackLink } from '@/components/booking/booking-hero'
import { BookingSteps, type WizardStep } from '@/components/booking/booking-steps'
import { BookingSummary, BookingSummaryBar } from '@/components/booking/booking-summary'
import { ShopDirectory } from '@/components/booking/shop-directory'
import { RatingValue } from '@/components/booking/shop-rating'
import {
  EMPTY_VALUES,
  STEP_FIELDS,
  clearAnswers,
  firstIncompleteStep,
  loadSavedAnswers,
  saveAnswers,
  wizardSchema,
  type FormStep,
  type WizardValues,
} from '@/components/booking/wizard-schema'
import { StepDetails, StepReview, StepServices, StepTime } from '@/components/booking/wizard-steps'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { endMockSession, useHasMockSession } from '@/hooks/use-mock-session'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { freeSlots, minutesInZone, openDates, type SlotContext } from '@/lib/booking-slots'
import { shopDateKey } from '@/lib/format'
import { getAdminUsers, getShopSuspensions } from '@/lib/mock-admin'
import {
  createBookingRecord,
  getBookings,
  getCurrentUser,
  getServices,
  getShopBySlug,
  type MockBooking,
  type MockService,
  type MockShop,
} from '@/lib/mock-data'

type Step = Exclude<WizardStep, 'shop'>
const ORDER: ReadonlyArray<Step> = ['services', 'time', 'details', 'review']

/** The services snapshot of an unknown shop: one stable array, as `useMockStore` requires. */
const NO_SERVICES: ReadonlyArray<MockService> = []

const HEADINGS: Record<Step, { title: string; guest?: string; description: string }> = {
  services: {
    title: 'What does your car need?',
    description:
      'Choose one or more services. You approve the technician’s estimate before any work starts.',
  },
  time: {
    title: 'When suits you?',
    description: 'Pick a day, then a time. Only free times are shown.',
  },
  details: {
    title: 'Your details and vehicle',
    description: 'The shop uses these to recognise your car and keep you updated.',
    guest:
      'You create your BayFlow account as you book. You’ll use it to approve the estimate and follow the repair.',
  },
  review: {
    title: 'Check and confirm',
    description: 'Make sure everything is right. You can edit any section.',
  },
}

const parseStep = (value: string | null): Step =>
  ORDER.includes(value as Step) ? (value as Step) : 'services'

/**
 * `/book/<slug>`: wizard steps 2–5 (spec 10 P-03). Renders a skeleton until the mock store and the
 * clock are available on the client, then either the form or, for a shop that isn't taking
 * bookings, the inline alert and the directory (W1).
 */
export function BookingWizard({ slug }: { slug: string }) {
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const found = useMockStore(() => getShopBySlug(slug))
  const suspensions = useMockStore(getShopSuspensions)
  const services = useMockStore(() => (found ? getServices(found.id) : NO_SERVICES))

  if (!ready || !nowIso) return <WizardSkeleton />

  // Unlisted and suspended shops are treated as missing (D96); one needs an active service (D64).
  const shop = found && found.is_listed && !suspensions[found.id] ? found : undefined
  const active = services.filter((s) => s.is_active)
  if (!shop || active.length === 0) return <NotTakingBookings />

  return <WizardForm key={slug} shop={shop} services={active} nowIso={nowIso} />
}

function WizardForm({
  shop,
  services,
  nowIso,
}: {
  shop: MockShop
  services: ReadonlyArray<MockService>
  nowIso: string
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const signedIn = useHasMockSession()
  const user = useMockStore(getCurrentUser)
  const bookings = useMockStore(() => getBookings())

  const todayKey = shopDateKey(nowIso, shop.timezone)
  const nextYear = new Date(nowIso).getUTCFullYear() + 1
  const ctx: SlotContext = {
    todayKey,
    nowMinutes: minutesInZone(new Date(nowIso), shop.timezone),
    bookings,
  }
  const dates = openDates(shop, todayKey)
  const hasFreeSlot = (date: string) => freeSlots(shop, date, ctx).length > 0

  const [initial] = useState<WizardValues>(() => {
    const saved = loadSavedAnswers(shop.slug)
    const offered = new Set(services.map((s) => s.id))
    const values: WizardValues = { ...EMPTY_VALUES, ...saved, password: '' }
    values.serviceIds = values.serviceIds.filter((id) => offered.has(id))
    const preselect = searchParams.get('service')
    if (values.serviceIds.length === 0 && preselect && offered.has(preselect)) {
      values.serviceIds = [preselect]
    }
    // A saved day that has passed or closed is dropped; the default is the first day with a free
    // time, so the step never opens on an empty day when a later one has room.
    if (!dates.includes(values.date)) {
      values.date = dates.find(hasFreeSlot) ?? dates[0] ?? ''
      values.time = ''
    }
    return values
  })

  const resolver = useMemo(
    () => zodResolver(wizardSchema(signedIn, nextYear)),
    [signedIn, nextYear],
  )
  const form = useForm<WizardValues>({ defaultValues: initial, resolver, mode: 'onTouched' })
  const values = useWatch({ control: form.control }) as WizardValues

  // R9: every change is kept for this tab, except the password.
  useEffect(() => saveAnswers(shop.slug, values), [values, shop.slug])

  // `step` lives in the URL; a deep link past an unfinished step lands on that step instead.
  const requested = parseStep(searchParams.get('step'))
  const incomplete = firstIncompleteStep(values, signedIn, nextYear)
  const step =
    incomplete && ORDER.indexOf(requested) > ORDER.indexOf(incomplete) ? incomplete : requested
  const hrefFor = (target: WizardStep) => `/book/${shop.slug}?step=${target}`

  useEffect(() => {
    if (step !== requested) router.replace(`/book/${shop.slug}?step=${step}`, { scroll: false })
  }, [step, requested, router, shop.slug])

  // Focus moves to the step's heading when the step changes (spec 09 §5, WCAG 2.4.3).
  const headingRef = useRef<HTMLHeadingElement>(null)
  const topRef = useRef<HTMLDivElement>(null)
  const firstStep = useRef(true)
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false
      return
    }
    headingRef.current?.focus({ preventScroll: true })
  }, [step])

  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const goTo = (target: Step) => {
    router.push(hrefFor(target), { scroll: false })
    topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const slots = values.date ? freeSlots(shop, values.date, ctx) : []
  const slotIsFree = (time: string) => slots.some((slot) => slot.time === time)

  const onContinue = async () => {
    setNotice(null)
    if (step === 'review') return
    if (step === 'time' && values.time && !slotIsFree(values.time)) {
      form.setValue('time', '')
      form.setError('time', { message: 'That time was just taken. Please pick another.' })
      return
    }
    const fields = [...STEP_FIELDS[step as FormStep]]
    if (await form.trigger(fields, { shouldFocus: true })) {
      goTo(ORDER[ORDER.indexOf(step) + 1]!)
    }
  }

  const onInvalid = (errors: FieldErrors<WizardValues>) => {
    const target = (Object.keys(STEP_FIELDS) as FormStep[]).find((s) =>
      STEP_FIELDS[s].some((field) => field in errors),
    )
    if (target) goTo(target)
  }

  const confirmBooking = async (raw: WizardValues) => {
    setNotice(null)
    // 409 SLOT_FULL: someone took the time while this visitor was on the later steps.
    const latest = freeSlots(shop, raw.date, { ...ctx, bookings: getBookings() })
    if (!latest.some((slot) => slot.time === raw.time)) {
      form.setValue('time', '')
      setNotice('That time was just booked by someone else. Please pick another slot.')
      goTo('time')
      return
    }
    setSubmitting(true)
    await new Promise((resolve) => setTimeout(resolve, 500))
    const email = (signedIn ? user.email : raw.email).trim().toLowerCase()
    const accountCreated = !signedIn && !getAdminUsers().some((u) => u.email === email)
    const chosen = services.filter((s) => raw.serviceIds.includes(s.id))
    const booking = createBookingRecord(
      {
        shopId: shop.id,
        shopSlug: shop.slug,
        shopName: shop.name,
        customerName: signedIn ? user.name : raw.fullName.trim(),
        customerEmail: email,
        customerPhone: raw.phone.trim(),
        vehicleMake: raw.make.trim(),
        vehicleModel: raw.model.trim(),
        vehicleYear: Number(raw.year),
        licensePlate: raw.registration.trim().toUpperCase(),
        vehicleColor: raw.color.trim() || undefined,
        mileageKm: raw.mileage.trim() ? Number(raw.mileage) : undefined,
        services: chosen.map((s) => s.name),
        customerNotes: raw.notes.trim() || undefined,
        scheduledDate: raw.date,
        scheduledTime: raw.time,
        // CREATE lands in PENDING; the service advisor confirms it (spec 08 T01).
        status: 'PENDING' satisfies MockBooking['status'],
        // The estimate comes after the inspection, never at booking time.
        estimateItems: [],
        estimateTotal: 0,
        paidAmount: 0,
      },
      { startSession: !signedIn },
    )
    clearAnswers(shop.slug)
    router.replace(`/book/confirmed/${booking.id}${accountCreated ? '?new_account=1' : ''}`)
  }

  const chosen = services.filter((s) => values.serviceIds.includes(s.id))
  const vehicle = values.registration.trim()
    ? [
        values.registration.trim().toUpperCase(),
        [values.year, values.make, values.model].filter(Boolean).join(' '),
      ]
        .filter(Boolean)
        .join(' · ')
    : ''
  // The default day is a suggestion until the visitor reaches the time step.
  const pastServices = ORDER.indexOf(step) >= ORDER.indexOf('time')
  const summary = {
    shop,
    services: chosen,
    date: pastServices ? values.date : '',
    time: pastServices ? values.time : '',
    vehicle,
  }
  const heading = HEADINGS[step]
  const signedInAs = signedIn ? { name: user.name, email: user.email } : null
  const stepNumber = ORDER.indexOf(step) + 2

  return (
    <div className="marketing bg-background pb-16">
      <BookingHero
        eyebrow={<HeroBackLink href="/book">All workshops</HeroBackLink>}
        title={
          <>
            <Handwritten>Book at</Handwritten> {shop.name}
          </>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="size-4 text-brand-blue-ink" aria-hidden />
              {shop.address}, {shop.city}
            </span>
            {shop.rating && (
              <span className="inline-flex items-center gap-1">
                <RatingValue rating={shop.rating} className="font-semibold text-foreground" />
                rating
              </span>
            )}
          </span>
        }
      >
        <BookingSteps current={step} hrefFor={hrefFor} />
      </BookingHero>

      <div
        ref={topRef}
        className="mx-auto grid max-w-6xl scroll-mt-20 gap-8 px-4 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:px-8"
      >
        <div className="min-w-0 space-y-4">
          <div className="lg:hidden">
            <BookingSummaryBar {...summary} />
          </div>

          <FormProvider {...form}>
            <form
              noValidate
              onSubmit={(event) => {
                event.preventDefault()
                if (step === 'review') void form.handleSubmit(confirmBooking, onInvalid)(event)
                else void onContinue()
              }}
              className="rounded-3xl border border-border bg-card shadow-sm"
            >
              <div className="p-5 sm:p-8">
                <p className="text-sm font-semibold text-brand-blue-ink">Step {stepNumber} of 5</p>
                <h2
                  ref={headingRef}
                  tabIndex={-1}
                  className="mt-1 text-3xl leading-tight font-bold text-foreground outline-none sm:text-4xl"
                >
                  {heading.title}
                </h2>
                <p className="mt-2 max-w-2xl text-base text-muted-foreground">
                  {!signedIn && heading.guest ? heading.guest : heading.description}
                </p>

                {notice && (
                  <Alert variant="destructive" className="mt-6 rounded-2xl">
                    <AlertCircle aria-hidden />
                    <AlertTitle>Please pick another time</AlertTitle>
                    <AlertDescription>{notice}</AlertDescription>
                  </Alert>
                )}

                <div className="mt-8">
                  {step === 'services' && <StepServices services={services} />}
                  {step === 'time' && (
                    <StepTime
                      shop={shop}
                      openDates={dates}
                      slots={slots}
                      nextDateWithSlots={
                        dates.find((d) => d > values.date && hasFreeSlot(d)) ?? null
                      }
                    />
                  )}
                  {step === 'details' && (
                    <StepDetails
                      signedInAs={signedInAs}
                      onSignOut={endMockSession}
                      loginHref={`/login?next=${encodeURIComponent(hrefFor('details'))}`}
                    />
                  )}
                  {step === 'review' && (
                    <StepReview
                      shop={shop}
                      services={chosen}
                      signedInAs={signedInAs}
                      onEdit={goTo}
                    />
                  )}
                </div>
              </div>

              {/* 44px actions (spec 10 P-03 Mobile); on phones the primary takes the rest of the
                  row and the services step's "Change workshop" shortens to "Back", so both fit a
                  360px screen. */}
              <div className="sticky bottom-0 z-10 flex items-center justify-between gap-2 rounded-b-3xl border-t border-border bg-card/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:gap-3 sm:px-8 lg:static lg:py-5 lg:backdrop-blur-none">
                {step === 'services' ? (
                  <Button asChild variant="outline" className="h-11 px-4 sm:px-5">
                    <Link href="/book">
                      <ArrowLeft aria-hidden />
                      <span className="sm:hidden">Back</span>
                      <span className="hidden sm:inline">Change workshop</span>
                    </Link>
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11 px-4 sm:px-5"
                    onClick={() => goTo(ORDER[ORDER.indexOf(step) - 1]!)}
                    disabled={submitting}
                  >
                    <ArrowLeft aria-hidden />
                    Back
                  </Button>
                )}
                <Button
                  type="submit"
                  disabled={submitting}
                  className="h-11 max-w-60 flex-1 px-5 sm:max-w-none sm:flex-none sm:px-6"
                >
                  {step === 'review' ? (
                    submitting ? (
                      <>
                        <Spinner aria-hidden />
                        Booking…
                      </>
                    ) : (
                      <>
                        <Check aria-hidden className="max-[359px]:hidden" />
                        Confirm booking
                      </>
                    )
                  ) : (
                    <>
                      Continue
                      <ArrowRight aria-hidden />
                    </>
                  )}
                </Button>
              </div>
            </form>
          </FormProvider>
        </div>

        <aside className="hidden lg:block">
          <div className="sticky top-24">
            <BookingSummary {...summary} />
          </div>
        </aside>
      </div>
    </div>
  )
}

/** W1 edge state: unknown, unlisted, suspended or service-less shop → alert plus the directory. */
function NotTakingBookings() {
  return (
    <div className="marketing bg-background pb-20">
      <BookingHero
        title={
          <>
            Book your car in for a <Handwritten>service</Handwritten>
          </>
        }
      >
        <Alert variant="warning" className="max-w-2xl rounded-2xl">
          <AlertCircle aria-hidden />
          <AlertTitle>That shop isn’t taking bookings</AlertTitle>
          <AlertDescription>Choose one of these workshops instead.</AlertDescription>
        </Alert>
      </BookingHero>
      <div className="mx-auto max-w-6xl px-4 pt-10 sm:px-6 lg:px-8">
        <ShopDirectory />
      </div>
    </div>
  )
}

export function WizardSkeleton() {
  return (
    <div className="marketing bg-background pb-16" aria-busy="true">
      <div className="border-b border-border/60 bg-card">
        <div className="mx-auto max-w-6xl space-y-4 px-4 pt-14 pb-8 sm:px-6 lg:px-8">
          <Skeleton className="h-5 w-32 rounded-full" />
          <Skeleton className="h-12 w-2/3 rounded-xl" />
          <Skeleton className="h-5 w-1/2 rounded-full" />
          <Skeleton className="mt-6 h-8 w-full max-w-xl rounded-full" />
        </div>
      </div>
      <div className="mx-auto grid max-w-6xl gap-8 px-4 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:px-8">
        <Skeleton className="h-[480px] rounded-3xl" />
        <Skeleton className="hidden h-[420px] rounded-3xl lg:block" />
      </div>
      <span className="sr-only">Loading the booking form…</span>
    </div>
  )
}
