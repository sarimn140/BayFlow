import { Skeleton } from '@/components/ui/skeleton'

/** PP-03 while this browser's stored stock loads (DESIGN.md §6.9): header, summary, the list. */
export function InventorySkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="flex flex-col gap-4 pb-2 md:flex-row md:items-end md:justify-between">
        <div className="space-y-3">
          <Skeleton className="h-4 w-16 rounded-full" />
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-5 w-80 max-w-full" />
        </div>
        <Skeleton className="h-10.5 w-32 rounded-full" />
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <Skeleton className="col-span-2 h-32 rounded-2xl lg:col-span-1" />
        <Skeleton className="h-32 rounded-2xl" />
        <Skeleton className="h-32 rounded-2xl" />
      </div>
      <Skeleton className="h-96 rounded-2xl" />
      <span className="sr-only">Loading inventory…</span>
    </div>
  )
}
