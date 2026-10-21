import { Eye, Undo2, type LucideIcon } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { StickyActionBar } from '@/components/layout/detail-layout'
import type { SaActivity } from '@/components/pos/sa-booking/sa-records'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { JobTone } from './job-model'

/** Card and section titles on the technician screens (an `h2`, 18px semibold like `CardTitle`). */
export const CARD_TITLE = 'text-lg leading-7 font-semibold text-foreground'

const TONE: Record<JobTone, string> = {
  brand: 'bg-brand-blue-subtle text-brand-blue-ink',
  danger: 'bg-danger-subtle text-danger-ink',
  neutral: 'bg-secondary text-muted-foreground',
  success: 'bg-success-subtle text-success-ink',
  inspection: 'bg-status-inspection-bg text-status-inspection-fg',
  repair: 'bg-status-repair-qc-bg text-status-repair-qc-fg',
}

/** Rounded icon tile in a tone (DESIGN.md §2.4 "icon tiles"). */
export function ToneTile({
  icon: Icon,
  tone,
  className,
}: {
  icon: LucideIcon
  tone: JobTone
  className?: string
}) {
  return (
    <span
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-xl',
        TONE[tone],
        className,
      )}
    >
      <Icon className="size-5" aria-hidden="true" />
    </span>
  )
}

/**
 * A number plate (DESIGN.md "plate/SKU tags": `font-mono`, 8px corners): white with a stone edge,
 * like the plate on the car. `lg` beside the job title.
 */
export function PlateTag({
  plate,
  size = 'sm',
  className,
}: {
  plate: string
  size?: 'sm' | 'lg'
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex w-fit shrink-0 items-center rounded-md border border-border-medium bg-card font-mono font-semibold whitespace-nowrap text-foreground shadow-xs',
        size === 'lg' ? 'h-8 px-2.5 text-base' : 'h-6 px-2 text-xs',
        className,
      )}
    >
      <span className="sr-only">Number plate </span>
      {plate}
    </span>
  )
}

/** Heading row of a T-01 group: tone tile, title with its count, one line on what it holds. */
export function GroupHeading({
  id,
  icon,
  tone,
  title,
  count,
  description,
}: {
  id: string
  icon: LucideIcon
  tone: JobTone
  title: string
  count: number
  description: string
}) {
  return (
    <div className="flex items-start gap-3">
      <ToneTile icon={icon} tone={tone} />
      <div className="min-w-0 space-y-0.5">
        <h2 id={id} className="flex flex-wrap items-center gap-2 text-xl leading-7 font-bold">
          {title}
          <Badge variant="secondary" className="tabular-nums">
            <span className="sr-only">(</span>
            {count}
            <span className="sr-only">{count === 1 ? ' job)' : ' jobs)'}</span>
          </Badge>
        </h2>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

/**
 * `ReadOnlyBanner` (spec 09 §4.11) on the Owner's view of the technician screens (D16): the Owner
 * can look but technicians act; the link opens the booking where the Owner can act as SA.
 */
export function ReadOnlyBanner({ href, scope }: { href: string; scope: 'list' | 'booking' }) {
  return (
    <Alert variant="info">
      <Eye aria-hidden="true" />
      <AlertTitle>Read-only view</AlertTitle>
      <AlertDescription>
        <p>
          Technician actions are done by technicians. To act on{' '}
          {scope === 'list' ? 'a booking' : 'this booking'},{' '}
          <Link href={href}>open it in Bookings</Link>.
        </p>
      </AlertDescription>
    </Alert>
  )
}

/**
 * T11 on T-02: the customer declined the estimate and the service advisor sent it back for
 * another inspection, with their note when they wrote one. Read-only, from the advisor's record
 * of the return (`currentReturn`); `to` is "you" for the technician, their name for the Owner.
 */
export function ReturnedNotice({
  returned,
  to,
  timeZone,
}: {
  returned: SaActivity
  to: string
  timeZone: string
}) {
  const note = returned.note?.trim()
  return (
    <Alert variant="warning">
      <Undo2 aria-hidden="true" />
      <AlertTitle>Estimate sent back to {to}</AlertTitle>
      <AlertDescription>
        <p>
          The customer declined the estimate. {returned.by} sent it back on{' '}
          <time dateTime={returned.at}>{formatDateTime(returned.at, timeZone)}</time>.
        </p>
        {note ? (
          <p className="whitespace-pre-line">
            <span className="font-semibold text-foreground">{returned.by}’s note:</span> “{note}”
          </p>
        ) : (
          <p>No note was added.</p>
        )}
      </AlertDescription>
    </Alert>
  )
}

/**
 * The job's main action pinned to the bottom of the screen on phones and tablets (DESIGN.md
 * §6.11): a `StickyActionBar` pinned until `xl`, since a tablet (and a laptop with the sidebar
 * open) shows the job in one column, the action far from the content. From `xl` the action sits
 * in the "Next step" card beside the content instead, so the bar is hidden there.
 */
export function JobActionBar({ summary, children }: { summary?: ReactNode; children: ReactNode }) {
  return (
    <StickyActionBar
      role="region"
      aria-label="Job actions"
      pinnedUntil="xl"
      className="gap-4 xl:hidden"
    >
      {summary ? (
        <div className="hidden min-w-0 flex-1 text-sm text-muted-foreground sm:block">
          {summary}
        </div>
      ) : null}
      <div className="flex flex-1 justify-end gap-2 *:flex-1 sm:flex-none sm:*:flex-none">
        {children}
      </div>
    </StickyActionBar>
  )
}
