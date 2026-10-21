import { Skeleton } from '@/components/ui/skeleton'

/**
 * Loading state shaped like the shop overview (DESIGN.md §6.9): hero, KPI row, the attention and
 * bookings column beside team and inventory, then bookings by status.
 */
export function OverviewSkeleton({ label = 'Loading the shop overview…' }: { label?: string }) {
  return (
    <div className="@container/overview space-y-6" aria-busy="true">
      <Skeleton className="h-64 rounded-3xl sm:h-72" />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 @4xl/overview:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-36 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-6 @4xl/overview:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <div className="space-y-6">
          <Skeleton className="h-64 rounded-2xl" />
          <Skeleton className="h-[36rem] rounded-2xl" />
        </div>
        <div className="grid content-start items-start gap-6 @2xl/overview:grid-cols-2 @4xl/overview:grid-cols-1">
          <Skeleton className="h-[34rem] rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      </div>
      <Skeleton className="h-72 rounded-2xl" />
      <span className="sr-only">{label}</span>
    </div>
  )
}
