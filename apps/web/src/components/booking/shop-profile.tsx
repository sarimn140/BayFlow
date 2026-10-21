'use client'

import { AlertCircle, ArrowRight, Clock, ExternalLink, MapPin, Phone, Wrench } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'

import { BookingHero, HeroBackLink } from '@/components/booking/booking-hero'
import { ServiceIcon } from '@/components/booking/service-icon'
import { fromPrice, openingToday, telHref } from '@/components/booking/shop-card'
import { ShopDirectory } from '@/components/booking/shop-directory'
import { RatingValue } from '@/components/booking/shop-rating'
import { EmptyState } from '@/components/layout/empty-state'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { WEEKDAYS, addDays, hoursOn, slotLabel, weekdayOf } from '@/lib/booking-slots'
import { formatPKR, shopDateKey } from '@/lib/format'
import { getShopSuspensions } from '@/lib/mock-admin'
import { getServices, getShopBySlug, type MockService, type MockShop } from '@/lib/mock-data'
import { shopPhoto } from '@/lib/shop-photos'
import { cn } from '@/lib/utils'

/** The services snapshot of an unknown shop: one stable array, as `useMockStore` requires. */
const NO_SERVICES: ReadonlyArray<MockService> = []

/** One date per weekday (any week will do), so `hoursOn` reads each day the way the wizard does. */
const DATE_OF_WEEKDAY = new Map(
  Array.from({ length: 7 }, (_, offset) => {
    const key = addDays('2026-01-05', offset)
    return [weekdayOf(key), key] as const
  }),
)

/** Monday to Sunday (glossary weekday 0 = Monday): "09:00 am – 06:00 pm", or null when closed. */
function weekHours(shop: MockShop) {
  return WEEKDAYS.map((day) => {
    const hours = hoursOn(shop, DATE_OF_WEEKDAY.get(day) ?? '')
    return { day, hours: hours ? `${slotLabel(hours.open)} – ${slotLabel(hours.close)}` : null }
  })
}

const BOOKING_STEPS = [
  {
    title: 'Choose services and a time',
    text: 'Pick what your car needs and a free slot. It takes about two minutes.',
  },
  {
    title: 'The shop inspects your car',
    text: 'A technician checks it, then the shop sends you an itemised estimate.',
  },
  {
    title: 'Approve the price online',
    text: 'Nothing is repaired until you approve the estimate on your phone.',
  },
  {
    title: 'Follow the repair live',
    text: 'See each step as it happens and pick up your car when it is ready.',
  },
] as const

/**
 * `/shops/<slug>`: P-02 shop detail (spec 10). Everything a customer needs to judge the shop
 * before booking: the photo, rating, address and phone, the services with prices, the opening
 * hours in shop time and how booking works. Unknown, unlisted and suspended shops are not public
 * (E-08 answers 404, D96); a shop without an active service is shown but can't be booked (D64).
 */
export function ShopProfile({ slug }: { slug: string }) {
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const found = useMockStore(() => getShopBySlug(slug))
  const suspensions = useMockStore(getShopSuspensions)
  const services = useMockStore(() => (found ? getServices(found.id) : NO_SERVICES))

  if (!ready) return <ShopProfileSkeleton />

  // A suspended shop is treated exactly like an unlisted one: not found (D96).
  const shop = found && found.is_listed && !suspensions[found.id] ? found : undefined
  if (!shop) return <ShopNotFound />

  return <ShopDetail shop={shop} services={services.filter((s) => s.is_active)} nowIso={nowIso} />
}

function ShopDetail({
  shop,
  services,
  nowIso,
}: {
  shop: MockShop
  services: ReadonlyArray<MockService>
  nowIso: string | null
}) {
  const bookable = services.length > 0
  const bookHref = `/book/${shop.slug}`
  const photo = shopPhoto(shop.slug)
  const price = fromPrice(services)
  const servicesCount = services.length === 1 ? '1 service' : `${services.length} services`
  const today = nowIso ? weekdayOf(shopDateKey(nowIso, shop.timezone)) : null
  const week = weekHours(shop)
  const mapsHref = `https://maps.google.com/?q=${encodeURIComponent(`${shop.name} ${shop.address} ${shop.city}`)}`

  return (
    <div className={cn('marketing bg-background', bookable ? 'md:pb-20' : 'pb-16 md:pb-20')}>
      <BookingHero
        eyebrow={<HeroBackLink href="/book">All shops</HeroBackLink>}
        title={shop.name}
        description={
          <span className="flex flex-col gap-4">
            <span className="flex flex-wrap items-center gap-x-4 gap-y-2">
              {shop.rating ? (
                <span className="inline-flex items-center gap-1.5">
                  <RatingValue rating={shop.rating} className="font-semibold text-foreground" />
                  rating
                </span>
              ) : (
                <span className="inline-flex items-center gap-2">
                  <Badge variant="brand">New</Badge>
                  No ratings yet
                </span>
              )}
              {nowIso && (
                <span className="inline-flex items-center gap-1.5">
                  <Clock className="size-4 text-brand-blue-ink" aria-hidden />
                  {openingToday(shop, nowIso)}
                </span>
              )}
            </span>
            <span className="flex flex-col gap-2">
              <span className="flex items-start gap-2">
                <MapPin className="mt-1 size-4 shrink-0 text-brand-blue-ink" aria-hidden />
                <span className="flex flex-col items-start gap-0.5">
                  <span>
                    {shop.address}, {shop.city}
                  </span>
                  <a
                    href={mapsHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-sm text-sm font-semibold text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                  >
                    Open in Google Maps
                    <ExternalLink className="size-3.5" aria-hidden />
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                </span>
              </span>
              <span className="flex items-center gap-2">
                <Phone className="size-4 shrink-0 text-brand-blue-ink" aria-hidden />
                <a
                  href={telHref(shop.phone)}
                  className="rounded-sm font-semibold text-brand-blue-ink tabular-nums underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {shop.phone}
                </a>
              </span>
            </span>
          </span>
        }
        media={
          <div className="relative aspect-[16/10] overflow-hidden rounded-3xl border border-border bg-muted shadow-sm lg:aspect-[4/3]">
            <Image
              src={photo.src}
              alt={photo.alt}
              fill
              priority
              sizes="(min-width: 1024px) 480px, 100vw"
              className="object-cover"
            />
          </div>
        }
        // Phones get the same action in the sticky bar at the bottom of the screen instead.
        childrenClassName={bookable ? 'hidden md:block' : undefined}
      >
        {bookable ? (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <Button asChild size="lg">
              <Link href={bookHref}>
                Book a service
                <ArrowRight aria-hidden />
              </Link>
            </Button>
            <p className="text-sm text-muted-foreground">
              {servicesCount}
              {price && (
                <>
                  {' '}
                  · from <span className="font-semibold text-foreground">{formatPKR(price)}</span>
                </>
              )}
            </p>
          </div>
        ) : (
          <Alert variant="warning" role="status" className="max-w-xl">
            <AlertCircle aria-hidden />
            <AlertTitle>This shop isn’t taking online bookings yet</AlertTitle>
            <AlertDescription>
              Call the shop to arrange a visit, or <Link href="/book">choose another workshop</Link>
              .
            </AlertDescription>
          </Alert>
        )}
      </BookingHero>

      <div className="mx-auto grid max-w-6xl items-start gap-6 px-4 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22.5rem] lg:px-8 lg:pt-10 xl:gap-8">
        <section aria-labelledby="shop-services" className="min-w-0">
          <Card className="gap-0 py-0">
            <CardHeader className="border-b pt-(--card-spacing)">
              <h2 id="shop-services" className="text-lg leading-7 font-semibold text-foreground">
                Services
              </h2>
              <CardDescription>
                {bookable
                  ? `${servicesCount}. Prices are a starting point: you approve the final estimate before any work starts.`
                  : 'The services this shop offers online appear here.'}
              </CardDescription>
            </CardHeader>
            {bookable ? (
              <ul className="divide-y divide-border-faint">
                {services.map((service) => (
                  <ServiceRow key={service.id} service={service} shopSlug={shop.slug} />
                ))}
              </ul>
            ) : (
              <EmptyState
                variant="inline"
                tone="neutral"
                icon={Wrench}
                title="No services listed yet"
                description="This shop hasn’t published its services online yet."
              />
            )}
          </Card>
        </section>

        <div className="min-w-0 space-y-6">
          <section aria-labelledby="shop-hours">
            <Card>
              <CardHeader>
                <h2 id="shop-hours" className="text-lg leading-7 font-semibold text-foreground">
                  Opening hours
                </h2>
                <CardDescription>Shop local time ({shop.timezone})</CardDescription>
              </CardHeader>
              <CardContent>
                {week.some((entry) => entry.hours) ? (
                  <dl className="-mx-3 space-y-0.5 text-sm">
                    {week.map(({ day, hours }) => {
                      const isToday = day === today
                      return (
                        <div
                          key={day}
                          className={cn(
                            'flex items-center justify-between gap-3 rounded-lg px-3 py-2',
                            isToday && 'bg-brand-blue-subtle',
                          )}
                        >
                          <dt
                            className={cn(
                              'flex items-center gap-2',
                              isToday ? 'font-semibold text-foreground' : 'text-muted-foreground',
                            )}
                          >
                            {day}
                            {isToday && <Badge>Today</Badge>}
                          </dt>
                          <dd
                            className={cn(
                              'text-right tabular-nums',
                              isToday && 'font-semibold',
                              hours ? 'text-foreground' : 'text-muted-foreground',
                            )}
                          >
                            {hours ?? 'Closed'}
                          </dd>
                        </div>
                      )
                    })}
                  </dl>
                ) : (
                  <p className="text-sm text-muted-foreground">No opening hours published</p>
                )}
              </CardContent>
            </Card>
          </section>

          {bookable && (
            <section aria-labelledby="how-booking-works">
              <Card>
                <CardHeader>
                  <h2
                    id="how-booking-works"
                    className="text-lg leading-7 font-semibold text-foreground"
                  >
                    How booking works
                  </h2>
                </CardHeader>
                <CardContent>
                  <ol className="space-y-4">
                    {BOOKING_STEPS.map((step, index) => (
                      <li key={step.title} className="flex gap-3">
                        <span
                          aria-hidden
                          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-blue-subtle text-sm font-semibold text-brand-blue-ink"
                        >
                          {index + 1}
                        </span>
                        <div className="min-w-0 pt-1">
                          <p className="text-sm font-semibold text-foreground">{step.title}</p>
                          <p className="mt-0.5 text-sm text-muted-foreground">{step.text}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </CardContent>
              </Card>
            </section>
          )}
        </div>
      </div>

      {bookable && (
        // Phones: the page's one action stays in reach at the bottom of the screen (spec 10 P-02).
        <div className="sticky bottom-0 z-20 mt-10 border-t border-border-faint bg-card/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md md:hidden">
          <div className="flex items-center justify-between gap-3">
            <p className="min-w-0 text-sm leading-snug text-muted-foreground">
              {price && (
                <span className="block font-semibold text-foreground">From {formatPKR(price)}</span>
              )}
              {servicesCount}
            </p>
            <Button asChild className="h-11 shrink-0 px-6">
              <Link href={bookHref}>Book a service</Link>
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * A service with its own "Book" link (`?service=` preselects it in the wizard). The button sits on
 * the duration and price line on phones, and beside the whole text from `sm`.
 */
function ServiceRow({ service, shopSlug }: { service: MockService; shopSlug: string }) {
  return (
    <li className="flex gap-4 px-5 py-5 sm:px-6">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
        <ServiceIcon name={service.name} className="size-5" />
      </span>
      <div className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 sm:gap-x-6">
        <h3 className="col-span-2 text-base font-semibold text-foreground sm:col-span-1">
          {service.name}
        </h3>
        <p className="col-span-2 text-sm leading-relaxed text-muted-foreground sm:col-span-1">
          {service.description}
        </p>
        <p className="col-start-1 flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3.5" aria-hidden />≈ {service.estimated_duration_minutes} min
          </span>
          <span className="font-semibold text-foreground">
            {service.base_price
              ? `from ${formatPKR(service.base_price)}`
              : 'Price after inspection'}
          </span>
        </p>
        <Button
          asChild
          variant="outline"
          className="col-start-2 row-start-3 sm:row-span-3 sm:row-start-1"
        >
          <Link href={`/book/${shopSlug}?service=${service.id}`}>
            Book<span className="sr-only"> {service.name}</span>
          </Link>
        </Button>
      </div>
    </li>
  )
}

/** Unknown, unlisted or suspended shop: say so, then offer the workshops that do take bookings. */
function ShopNotFound() {
  return (
    <div className="marketing bg-background pb-20">
      <BookingHero
        eyebrow={<HeroBackLink href="/book">All shops</HeroBackLink>}
        title="We couldn’t find that shop"
        description="The link may be mistyped or out of date. These workshops are taking online bookings."
      />
      <section
        aria-labelledby="other-workshops"
        className="mx-auto max-w-6xl px-4 pt-10 sm:px-6 lg:px-8"
      >
        <h2 id="other-workshops" className="sr-only">
          Workshops
        </h2>
        <ShopDirectory />
      </section>
    </div>
  )
}

function ShopProfileSkeleton() {
  return (
    <div className="marketing bg-background pb-20" aria-busy="true">
      <div className="border-b border-border/60 bg-card">
        <div className="mx-auto max-w-6xl px-4 pt-10 pb-8 sm:px-6 md:pt-14 lg:px-8">
          <Skeleton className="h-5 w-24 rounded-full" />
          <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:items-center lg:gap-12">
            <div className="space-y-4">
              <Skeleton className="h-12 w-3/4 rounded-xl" />
              <Skeleton className="h-5 w-1/2 rounded-full" />
              <Skeleton className="h-5 w-2/3 rounded-full" />
              <Skeleton className="h-5 w-40 rounded-full" />
              <Skeleton className="mt-8 hidden h-12 w-52 rounded-full md:block" />
            </div>
            <Skeleton className="order-first aspect-[16/10] rounded-3xl lg:order-none lg:aspect-[4/3]" />
          </div>
        </div>
      </div>
      <div className="mx-auto grid max-w-6xl gap-6 px-4 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22.5rem] lg:px-8 lg:pt-10 xl:gap-8">
        <Skeleton className="h-[36rem] rounded-2xl" />
        <Skeleton className="hidden h-[26rem] rounded-2xl lg:block" />
      </div>
      <span className="sr-only">Loading the shop…</span>
    </div>
  )
}
