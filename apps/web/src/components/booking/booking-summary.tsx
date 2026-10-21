'use client'

import { CalendarDays, Car, ChevronDown, Info, MapPin, Wrench } from 'lucide-react'
import Image from 'next/image'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { formatDateKey } from '@/lib/booking-slots'
import { formatPKR } from '@/lib/format'
import type { MockService, MockShop } from '@/lib/mock-data'
import { shopPhoto } from '@/lib/shop-photos'

export interface SummaryData {
  shop: MockShop
  services: ReadonlyArray<MockService>
  date: string
  time: string
  vehicle: string
}

/** One line of a booking summary: a blue icon dot, a small label and the value under it. */
export function SummaryRow({
  icon,
  label,
  children,
}: {
  icon: ReactNode
  label: string
  children: ReactNode
}) {
  return (
    <div className="flex gap-3 py-3.5">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-blue-subtle text-brand-blue-ink [&_svg]:size-4">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <div className="mt-0.5 text-sm text-foreground">{children}</div>
      </div>
    </div>
  )
}

/**
 * The head of a booking summary: the shop's cover photo under a dark fade, with the shop's name
 * and city over it and an optional action (the wizard's "Change") on the right.
 */
export function ShopPhotoBanner({
  slug,
  name,
  city,
  label,
  action,
  sizes = '380px',
}: {
  slug: string
  name: string
  city?: string
  label: string
  action?: ReactNode
  sizes?: string
}) {
  const photo = shopPhoto(slug)
  return (
    <div className="relative aspect-[16/9]">
      <Image src={photo.src} alt={photo.alt} fill sizes={sizes} className="object-cover" />
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent"
      />
      <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4 text-white">
        <div className="min-w-0">
          <p className="text-xs font-medium text-white/80">{label}</p>
          <p className="truncate font-heading text-2xl leading-tight font-bold">{name}</p>
          {city && (
            <p className="flex items-center gap-1 text-xs text-white/85">
              <MapPin className="size-3.5" aria-hidden />
              {city}
            </p>
          )}
        </div>
        {action}
      </div>
    </div>
  )
}

const Pending = ({ children }: { children: ReactNode }) => (
  <span className="text-muted-foreground">{children}</span>
)

function SummaryRows({ services, date, time, vehicle }: Omit<SummaryData, 'shop'>) {
  const total = services.reduce((sum, s) => sum + (s.base_price ?? 0), 0)
  const someUnpriced = services.some((s) => !s.base_price)
  return (
    <>
      <div className="divide-y divide-border-faint">
        <SummaryRow icon={<Wrench />} label="Services">
          {services.length === 0 ? (
            <Pending>Choose what your car needs</Pending>
          ) : (
            <ul className="space-y-1">
              {services.map((s) => (
                <li key={s.id} className="flex justify-between gap-3">
                  <span className="min-w-0">{s.name}</span>
                  <span className="shrink-0 font-medium tabular-nums">
                    {s.base_price ? formatPKR(s.base_price) : 'On inspection'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </SummaryRow>
        <SummaryRow icon={<CalendarDays />} label="Date and time">
          {date && time ? (
            <span className="font-semibold">
              {formatDateKey(date)} · {time}
            </span>
          ) : date ? (
            <>
              {formatDateKey(date)} · <Pending>pick a time</Pending>
            </>
          ) : (
            <Pending>Pick a date and time</Pending>
          )}
        </SummaryRow>
        <SummaryRow icon={<Car />} label="Vehicle">
          {vehicle ? (
            <span className="font-medium">{vehicle}</span>
          ) : (
            <Pending>Added in step 4</Pending>
          )}
        </SummaryRow>
      </div>
      {total > 0 && (
        <div className="mt-1 flex items-baseline justify-between border-t border-border pt-4">
          <span className="text-sm font-semibold text-foreground">
            Estimated from{someUnpriced && <span className="text-muted-foreground"> *</span>}
          </span>
          <span className="text-2xl font-bold text-foreground tabular-nums">
            {formatPKR(total)}
          </span>
        </div>
      )}
      <p className="mt-4 flex gap-2 rounded-2xl bg-muted px-3.5 py-3 text-xs leading-relaxed text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0 text-brand-blue-ink" aria-hidden />
        <span>
          The final price comes from the technician&apos;s inspection estimate. You approve it
          online before any work starts.
          {someUnpriced && ' * Some services are priced after inspection.'}
        </span>
      </p>
    </>
  )
}

/** "Your booking", sticky beside the step on large screens (spec 10 P-03 Shell). */
export function BookingSummary(data: SummaryData) {
  return (
    <section
      aria-label="Your booking"
      className="overflow-hidden rounded-3xl border border-border bg-card shadow-sm"
    >
      <ShopPhotoBanner
        slug={data.shop.slug}
        name={data.shop.name}
        city={data.shop.city}
        label="Your booking at"
        action={
          <Link
            href="/book"
            className="shrink-0 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white backdrop-blur outline-none hover:bg-white/25 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white focus-visible:outline-solid"
          >
            Change<span className="sr-only"> workshop</span>
          </Link>
        }
      />
      <div className="p-5 pt-2">
        <SummaryRows {...data} />
      </div>
    </section>
  )
}

/** The same summary as a collapsible bar above the step on small screens. */
export function BookingSummaryBar(data: SummaryData) {
  const parts = [
    data.services.length === 1 ? '1 service' : `${data.services.length} services`,
    data.date && data.time ? `${formatDateKey(data.date)} · ${data.time}` : null,
  ].filter(Boolean)
  return (
    <Collapsible className="group/summary overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
      <CollapsibleTrigger className="flex w-full items-center gap-3 rounded-3xl px-5 py-4 text-left outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid">
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-foreground">Your booking</span>
          <span className="block truncate text-xs text-muted-foreground">
            {data.shop.name}
            {parts.length > 0 && ` · ${parts.join(' · ')}`}
          </span>
        </span>
        <ChevronDown
          className="size-5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]/summary:rotate-180"
          aria-hidden
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t border-border-faint px-5 pb-5">
        <SummaryRows {...data} />
      </CollapsibleContent>
    </Collapsible>
  )
}
