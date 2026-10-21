import { DetailLayout, detailLayoutOnly } from '@/components/layout/detail-layout'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

function HeaderSkeleton({ back = false }: { back?: boolean }) {
  return (
    <div className="space-y-3 pb-2">
      {back ? <Skeleton className="h-5 w-24 rounded-full" /> : null}
      <Skeleton className="h-4 w-28 rounded-full" />
      <Skeleton className="h-10 w-64 max-w-full" />
      <Skeleton className="h-5 w-full max-w-xl" />
    </div>
  )
}

/** Loading state shaped like the QC queue (DESIGN.md §6.9): header, the two queue cards, history. */
export function QcQueueSkeleton() {
  return (
    <div className="@container/qc space-y-6" aria-busy="true">
      <HeaderSkeleton />
      <div className="grid items-start gap-6 @4xl/qc:grid-cols-2">
        <Skeleton className="h-80 rounded-2xl" />
        <Skeleton className="h-56 rounded-2xl" />
      </div>
      <Skeleton className="h-24 rounded-2xl" />
      <span className="sr-only">Loading the QC queue…</span>
    </div>
  )
}

/**
 * Loading state shaped like an inspection: header, then the page's `DetailLayout` — the checklist
 * first, the decision card beside it only in two columns, then the job.
 */
export function QcInspectionSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <HeaderSkeleton back />
      <DetailLayout
        asideFirstOnMobile={false}
        aside={
          <>
            <Skeleton className={cn('h-72 rounded-2xl', detailLayoutOnly.twoColumns)} />
            <Skeleton className="h-80 rounded-2xl" />
          </>
        }
      >
        <Skeleton className="h-[34rem] rounded-2xl" />
        <Skeleton className="h-56 rounded-2xl" />
      </DetailLayout>
      <span className="sr-only">Loading the inspection…</span>
    </div>
  )
}
