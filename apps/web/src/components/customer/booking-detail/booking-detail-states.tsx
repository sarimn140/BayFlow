import { SearchX } from 'lucide-react'
import Link from 'next/link'

import { DetailLayout } from '@/components/layout/detail-layout'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

/**
 * Loading (DESIGN.md §6.9): shaped like the page — header, banner, then the page's
 * `DetailLayout` (progress and side cards first, the estimate beside them in two columns).
 */
export function BookingDetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-5 w-28 rounded-full" />
        <Skeleton className="h-4 w-48 rounded-full" />
        <Skeleton className="h-10 w-64 max-w-full" />
        <Skeleton className="h-5 w-96 max-w-full" />
      </div>
      <Skeleton className="h-16 rounded-xl" />
      <DetailLayout
        aside={
          <>
            <Skeleton className="h-96 rounded-2xl" />
            <Skeleton className="h-56 rounded-2xl" />
          </>
        }
      >
        <Skeleton className="h-[32rem] rounded-2xl" />
      </DetailLayout>
      <span className="sr-only">Loading your booking…</span>
    </div>
  )
}

/**
 * X-02 in-page (spec 10): an unknown booking, or one that isn't the viewer's. Never says which
 * (D20, D21).
 */
export function BookingNotFound() {
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center gap-4 rounded-3xl border border-border bg-card px-6 py-10 text-center shadow-xs sm:px-10">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-blue-subtle text-brand-blue-ink">
        <SearchX className="size-7" aria-hidden="true" />
      </span>
      <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
        We couldn&apos;t find that.
      </h1>
      <p className="text-base text-muted-foreground">
        Check the link, or open the booking from your list of bookings.
      </p>
      <Button asChild size="lg" className="mt-2">
        <Link href="/bookings">Go to my bookings</Link>
      </Button>
    </div>
  )
}
