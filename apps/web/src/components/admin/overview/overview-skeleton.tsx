import { Skeleton } from '@/components/ui/skeleton'

/** Loading state shaped like the platform overview (DESIGN.md §6.9). */
export function OverviewSkeleton() {
  return (
    <div className="@container/admin space-y-6" aria-busy="true">
      <Skeleton className="h-56 rounded-3xl sm:h-64" />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 @2xl/admin:grid-cols-3 @5xl/admin:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-6 @4xl/admin:grid-cols-3">
        <Skeleton className="h-96 rounded-2xl @4xl/admin:col-span-2" />
        <Skeleton className="h-96 rounded-2xl" />
      </div>
      <span className="sr-only">Loading the platform overview…</span>
    </div>
  )
}
