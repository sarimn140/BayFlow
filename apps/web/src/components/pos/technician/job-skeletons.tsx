import { DetailLayout } from '@/components/layout/detail-layout'
import { Skeleton } from '@/components/ui/skeleton'

/** T-01 while this browser's stored jobs load (DESIGN.md §6.9): header, two job cards, a list. */
export function JobsSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-4 w-24 rounded-full" />
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-5 w-72 max-w-full" />
      </div>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-xl" />
          <Skeleton className="h-6 w-40" />
        </div>
        {/* The list's own grid: as many 26rem cards as the content area fits. */}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,26rem),1fr))] gap-4">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-80 rounded-2xl" />
          ))}
        </div>
      </div>
      <Skeleton className="h-48 rounded-2xl" />
      <span className="sr-only">Loading jobs…</span>
    </div>
  )
}

/**
 * T-02 while the job loads: header, then the page's `DetailLayout` (DESIGN.md §6.9), so the next
 * step comes first and the columns split at the same width as the loaded job.
 */
export function JobDetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-4 w-20 rounded-full" />
        <Skeleton className="h-4 w-36 rounded-full" />
        <Skeleton className="h-10 w-80 max-w-full" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-28 rounded-md" />
          <Skeleton className="h-7 w-24 rounded-full" />
        </div>
      </div>
      <DetailLayout aside={<Skeleton className="h-44 rounded-2xl" />}>
        <Skeleton className="h-52 rounded-2xl" />
        <Skeleton className="h-96 rounded-2xl" />
      </DetailLayout>
      <span className="sr-only">Loading the job…</span>
    </div>
  )
}
