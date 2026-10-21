'use client'

import { ArrowRight, Clock, MapPin } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'

import { RatingValue } from '@/components/booking/shop-rating'
import { Button } from '@/components/ui/button'
import { hoursOn, slotLabel } from '@/lib/booking-slots'
import { formatPKR, shopDateKey } from '@/lib/format'
import type { MockService, MockShop } from '@/lib/mock-data'
import { shopPhoto } from '@/lib/shop-photos'

/** "Open today · 09:00 am – 06:00 pm" in the shop's timezone, or "Closed today". */
export function openingToday(shop: MockShop, nowIso: string): string {
  const hours = hoursOn(shop, shopDateKey(nowIso, shop.timezone))
  return hours
    ? `Open today · ${slotLabel(hours.open)} – ${slotLabel(hours.close)}`
    : 'Closed today'
}

/** A `tel:` link for a shop phone such as "+92 42 35789011" (digits and the leading + only). */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

/** Lowest listed price among the shop's services, or null when every price is set on inspection. */
export function fromPrice(services: ReadonlyArray<MockService>): number | null {
  const prices = services.flatMap((s) => (s.base_price ? [s.base_price] : []))
  return prices.length ? Math.min(...prices) : null
}

/** A shop in the booking directory: photo, rating, address, top services and the two actions. */
export function ShopCard({
  shop,
  services,
  nowIso,
  priority = false,
}: {
  shop: MockShop
  services: ReadonlyArray<MockService>
  /** Shop-local "now" decides the opening chip; null until the page has mounted. */
  nowIso: string | null
  priority?: boolean
}) {
  const photo = shopPhoto(shop.slug)
  const price = fromPrice(services)

  return (
    <article className="group flex flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm transition-[box-shadow,transform] duration-300 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-brand-navy/10">
      <div className="relative aspect-[16/10] overflow-hidden bg-muted">
        <Image
          src={photo.src}
          alt={photo.alt}
          fill
          priority={priority}
          sizes="(min-width: 1024px) 360px, (min-width: 640px) 50vw, 100vw"
          className="object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04]"
        />
        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/5 to-transparent"
        />
        <span className="absolute top-3 left-3 inline-flex items-center gap-1 rounded-full bg-card/95 px-2.5 py-1 text-xs font-semibold text-foreground shadow-sm backdrop-blur">
          <MapPin className="size-3.5 text-brand-blue-ink" aria-hidden />
          {shop.city}
        </span>
        <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-card/95 px-2.5 py-1 text-xs font-semibold text-foreground shadow-sm backdrop-blur">
          {shop.rating ? <RatingValue rating={shop.rating} /> : 'New'}
        </span>
        {nowIso && (
          <span className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 text-xs font-medium text-white">
            <Clock className="size-3.5" aria-hidden />
            {openingToday(shop, nowIso)}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4 p-5">
        <div className="space-y-1">
          <h3 className="text-2xl leading-tight font-bold text-foreground">
            <Link
              href={`/shops/${shop.slug}`}
              className="rounded-md transition-colors outline-none hover:text-brand-blue-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
            >
              {shop.name}
            </Link>
          </h3>
          <p className="truncate text-sm text-muted-foreground">{shop.address}</p>
        </div>

        {services.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label="Popular services">
            {services.slice(0, 3).map((service) => (
              <li
                key={service.id}
                className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground"
              >
                {service.name}
              </li>
            ))}
            {services.length > 3 && (
              <li className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground">
                +{services.length - 3} more
              </li>
            )}
          </ul>
        )}

        <div className="mt-auto flex items-end justify-between gap-3 border-t border-border-faint pt-4">
          <p className="text-xs text-muted-foreground">
            {price ? (
              <>
                From <span className="text-base font-bold text-foreground">{formatPKR(price)}</span>
              </>
            ) : (
              'Price after inspection'
            )}
          </p>
          <Button
            asChild
            className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-5 font-semibold"
          >
            <Link href={`/book/${shop.slug}?step=services`} aria-label={`Book at ${shop.name}`}>
              Book now
              <ArrowRight
                aria-hidden
                className="transition-transform group-hover:translate-x-0.5"
              />
            </Link>
          </Button>
        </div>
      </div>
    </article>
  )
}
