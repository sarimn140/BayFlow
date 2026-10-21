import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface PageHeaderProps {
  /** The page's only `<h1>` (UX rule R8). A string, or text with one `<Handwritten>` word. */
  title: ReactNode
  /** One sentence under the title. */
  description?: ReactNode
  /** Header actions: at most one primary `<Button>`, the rest outline / ghost (UX rule R7). */
  actions?: ReactNode
  /** Small brand-blue line above the title: the area or the record type ("Service advisor"). */
  eyebrow?: ReactNode
  /** Back link above everything, for detail pages ("← Bookings"). */
  back?: { href: string; label: string }
  /** Chips beside the title, e.g. the booking's `StatusBadge size="md"` on a detail page. */
  badges?: ReactNode
  /** No visual effect any more (POS and portal share one scale); kept so older call sites compile. */
  variant?: 'portal' | 'pos'
  className?: string
}

/**
 * Page title row (DESIGN.md "Page header"): optional back link and eyebrow, a 30/36px extra-bold
 * title with chips beside it, a muted description, and the actions.
 *
 * The actions sit on the right only when the header itself has room for them beside a title block
 * of at least 24rem (384px); otherwise they wrap below it. It answers to the header's own width,
 * not the screen's, so a 256px sidebar on a tablet never squeezes the title to one word per line.
 * (A flex wrap rather than a container query: containment would collapse the header wherever a
 * page puts it in a flex row of its own.) Put it first in the page's `space-y-6` stack; it adds 8px
 * below itself.
 */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  back,
  badges,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn('flex flex-col gap-3 pb-2', className)}>
      {back ? (
        <Link
          href={back.href}
          className="-ml-1 inline-flex w-fit items-center gap-1.5 rounded-full px-1 py-0.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {back.label}
        </Link>
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-[1_1_24rem] space-y-2">
          {eyebrow ? <p className="text-sm font-semibold text-brand-blue-ink">{eyebrow}</p> : null}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl">
              {title}
            </h1>
            {badges}
          </div>
          {description ? (
            <p className="max-w-2xl text-base text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex min-w-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </div>
  )
}
