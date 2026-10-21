import { Skeleton } from '@/components/ui/skeleton'

/** The queue card while this browser's data loads: toolbar, then five rows (spec 09 §4.7). */
export function QueueSkeleton() {
  return (
    <div
      aria-busy="true"
      className="overflow-clip rounded-2xl border border-border bg-card shadow-xs"
    >
      <div className="flex flex-col gap-3 border-b border-border-faint px-5 py-3 sm:flex-row sm:flex-wrap sm:items-center">
        <Skeleton className="h-9 w-80 max-w-full rounded-full" />
        <Skeleton className="h-9 w-full rounded-full sm:w-72" />
        <div className="flex gap-2">
          <Skeleton className="h-9 w-36 rounded-md" />
          <Skeleton className="h-9 w-32 rounded-md" />
        </div>
      </div>
      <div className="h-11 border-b border-border-faint bg-layer/60" />
      <ul className="divide-y divide-border-faint">
        {[0, 1, 2, 3, 4].map((key) => (
          <li key={key} className="flex items-center gap-6 px-5 py-4">
            <div className="w-28 space-y-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-28" />
            </div>
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-40 max-w-full" />
              <Skeleton className="h-3 w-56 max-w-full" />
            </div>
            <Skeleton className="hidden h-6 w-28 rounded-full sm:block" />
            <Skeleton className="hidden h-6 w-32 rounded-full md:block" />
          </li>
        ))}
      </ul>
      <span className="sr-only">Loading bookings…</span>
    </div>
  )
}
