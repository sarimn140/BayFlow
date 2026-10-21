import { ArrowRight, ScrollText } from 'lucide-react'
import Link from 'next/link'

import { Handwritten } from '@/components/booking/booking-hero'
import { Button } from '@/components/ui/button'

/**
 * The platform admin's greeting (DESIGN.md "Page hero"): the page's only `<h1>`, today's date,
 * one line on the state of the platform and the two ways in: shops and the audit log.
 */
export function OverviewHero({
  greeting,
  firstName,
  dateLabel,
  summary,
}: {
  /** "Good morning". */
  greeting: string
  /** The admin's first name: the page's one handwritten word. */
  firstName: string
  /** "Saturday, 10 October". */
  dateLabel: string
  summary: string
}) {
  return (
    <header className="bg-hero rounded-3xl border border-border px-5 py-7 sm:px-8 sm:py-10">
      <div className="flex flex-col gap-6 @4xl/admin:flex-row @4xl/admin:items-end @4xl/admin:justify-between">
        <div className="min-w-0 space-y-3">
          <p className="text-sm font-semibold text-brand-blue-ink">
            Platform overview · {dateLabel}
          </p>
          <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground @lg/admin:text-4xl @4xl/admin:text-5xl">
            {greeting}, <Handwritten>{firstName}</Handwritten>
          </h1>
          <p className="max-w-3xl text-base text-muted-foreground">{summary}</p>
        </div>
        <div className="flex flex-wrap gap-2 @4xl/admin:shrink-0 @4xl/admin:justify-end">
          <Button asChild variant="outline">
            <Link href="/admin/audit">
              <ScrollText data-icon="inline-start" aria-hidden="true" />
              Audit log
            </Link>
          </Button>
          <Button asChild>
            <Link href="/admin/shops">
              Manage shops
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
