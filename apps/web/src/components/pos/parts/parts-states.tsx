import { Eye, SearchX } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { DetailLayout, detailLayoutOnly } from '@/components/layout/detail-layout'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { CardTitle } from '@/components/ui/card'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** A card title that is an `<h2>` in the page outline (the page header holds the `<h1>`). */
export function CardHeading({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <CardTitle>
      <h2 id={id} className="flex flex-wrap items-center gap-2 font-semibold">
        {children}
      </h2>
    </CardTitle>
  )
}

/**
 * `ReadOnlyBanner` (spec 09 §4.11) for the Owner's view of the parts screens (D16): the Parts
 * Person reserves, orders and allocates parts; the Owner acts on bookings from Bookings.
 */
export function ReadOnlyNotice({ children }: { children: ReactNode }) {
  return (
    <Alert variant="info" role="note">
      <Eye aria-hidden="true" />
      <AlertTitle>Read-only view</AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  )
}

/** Loading (DESIGN.md §6.9): shaped like the queue — header, then the three stage cards. */
export function PartsQueueSkeleton() {
  return (
    <div className="@container/queue space-y-6" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-5 w-16 rounded-full" />
        <Skeleton className="h-10 w-56 max-w-full" />
        <Skeleton className="h-5 w-96 max-w-full" />
      </div>
      <div className="grid items-start gap-6 @4xl/queue:grid-cols-3 @4xl/queue:gap-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-72 rounded-2xl" />
        ))}
      </div>
      <span className="sr-only">Loading the parts queue…</span>
    </div>
  )
}

/**
 * Loading (DESIGN.md §6.9): shaped like a parts job — header, then the page's `DetailLayout`: the
 * next step, the parts table, and the job card (beside the table in two columns, after it in one).
 */
export function PartsJobSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-5 w-28 rounded-full" />
        <Skeleton className="h-10 w-64 max-w-full" />
        <Skeleton className="h-5 w-96 max-w-full" />
      </div>
      <DetailLayout
        aside={
          <>
            <Skeleton className="h-56 rounded-2xl" />
            <Skeleton className={cn('h-64 rounded-2xl', detailLayoutOnly.twoColumns)} />
          </>
        }
      >
        <Skeleton className="h-[28rem] rounded-2xl" />
        <Skeleton className={cn('h-64 rounded-2xl', detailLayoutOnly.oneColumn)} />
      </DetailLayout>
      <span className="sr-only">Loading the parts job…</span>
    </div>
  )
}

/**
 * X-02 in-page (spec 10): an unknown booking, or one of another shop. Never says which (D20).
 */
export function PartsJobNotFound({ queueHref }: { queueHref: string }) {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <SearchX aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          We couldn&apos;t find that job
        </h1>
        <EmptyDescription className="text-base">
          Check the link, or open the job from the parts queue.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={queueHref}>Go to the parts queue</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
