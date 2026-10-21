import { ArrowRight, Clock, ExternalLink, MapPin, Settings } from 'lucide-react'
import Link from 'next/link'

import { Handwritten } from '@/components/booking/booking-hero'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { MockShop } from '@/lib/mock-data'

import { plural } from './overview-data'

export interface OverviewHeroProps {
  shop: MockShop
  /** "Good afternoon". */
  greeting: string
  /** The owner's first name: the page's one handwritten word. */
  firstName: string
  /** "Saturday, 10 October". */
  dateLabel: string
  summary: string
  base: string
}

/**
 * The Owner's greeting (DESIGN.md "Page hero"): the page's only `<h1>`, the shop and today's
 * date, one line on the state of the floor, the shop's essentials and the two header actions.
 */
export function OverviewHero({
  shop,
  greeting,
  firstName,
  dateLabel,
  summary,
  base,
}: OverviewHeroProps) {
  return (
    <header className="bg-hero rounded-3xl border border-border px-5 py-7 sm:px-8 sm:py-10">
      <div className="flex flex-col gap-6 @5xl/overview:flex-row @5xl/overview:items-end @5xl/overview:justify-between">
        <div className="min-w-0 space-y-3">
          <p className="text-sm font-semibold text-brand-blue-ink">
            {shop.name} · {dateLabel}
          </p>
          <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground @lg/overview:text-4xl @4xl/overview:text-5xl">
            {greeting}, <Handwritten>{firstName}</Handwritten>
          </h1>
          <p className="max-w-3xl text-base text-muted-foreground">{summary}</p>
          <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1 text-sm text-muted-foreground">
            <li className="flex min-w-0 items-center gap-1.5">
              <MapPin className="size-4 shrink-0 text-helper" aria-hidden="true" />
              <span className="min-w-0">
                {shop.address}, {shop.city}
              </span>
            </li>
            <li className="flex items-center gap-1.5">
              <Clock className="size-4 shrink-0 text-helper" aria-hidden="true" />
              {shop.slot_duration_minutes}-minute slots · {plural(shop.slot_capacity, 'car')} per
              slot
            </li>
            <li className="flex flex-wrap items-center gap-2">
              {shop.is_listed ? (
                <>
                  <Badge variant="success">Listed on BayFlow</Badge>
                  <Link
                    href={`/shops/${encodeURIComponent(shop.slug)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="-my-2.5 inline-flex items-center gap-1 rounded-sm py-2.5 font-medium text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                  >
                    View public page
                    <ExternalLink className="size-3.5" aria-hidden="true" />
                    <span className="sr-only"> (opens in a new tab)</span>
                  </Link>
                </>
              ) : (
                <Badge variant="neutral">Not listed in the directory</Badge>
              )}
            </li>
          </ul>
        </div>
        <div className="flex flex-wrap gap-2 @5xl/overview:shrink-0 @5xl/overview:justify-end">
          <Button asChild variant="outline">
            <Link href={`${base}/settings`}>
              <Settings data-icon="inline-start" aria-hidden="true" />
              Shop settings
            </Link>
          </Button>
          <Button asChild>
            <Link href={`${base}/bookings`}>
              Open bookings
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
