import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * The header band of the public booking pages, in the landing page's language: grid paper, a soft
 * blue glow, an extra-bold heading with one handwritten word, and room for the step indicator.
 * `media` (a shop photo) sits beside the text from `lg` and above it on smaller screens.
 */
export function BookingHero({
  eyebrow,
  title,
  description,
  children,
  childrenClassName,
  media,
  className,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  /** Classes for the block that holds `children`, e.g. `hidden md:block` for desktop-only actions. */
  childrenClassName?: string
  media?: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        'bg-grid-pattern relative overflow-hidden border-b border-border/60 bg-card',
        className,
      )}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-1/2 left-1/2 aspect-square w-[min(1000px,140vw)] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(16,71,250,0.10)_0%,rgba(16,71,250,0.04)_38%,transparent_68%)] blur-2xl"
      />
      <div className="relative mx-auto max-w-6xl px-4 pt-10 pb-8 sm:px-6 md:pt-14 lg:px-8">
        {eyebrow && <div className="mb-4">{eyebrow}</div>}
        <div
          className={cn(
            media &&
              'grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:items-center lg:gap-12',
          )}
        >
          <div className="min-w-0">
            <h1
              tabIndex={-1}
              className="max-w-3xl text-4xl leading-[1.08] font-extrabold tracking-tight text-foreground outline-none sm:text-5xl"
            >
              {title}
            </h1>
            {description && (
              <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}
            {children && <div className={cn('mt-8', childrenClassName)}>{children}</div>}
          </div>
          {media && <div className="order-first lg:order-none">{media}</div>}
        </div>
      </div>
    </section>
  )
}

/** The handwritten accent word used in headings, as on the landing page. */
export function Handwritten({ children }: { children: ReactNode }) {
  return (
    <span className="pr-[0.18em] font-handwriting text-[1.15em] font-normal text-brand-blue-ink italic">
      {children}
    </span>
  )
}

/** A small pill above a heading. */
export function Eyebrow({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-blue/15 bg-brand-blue-subtle px-3 py-1 text-xs font-semibold text-brand-blue-ink [&_svg]:size-3.5">
      {icon}
      {children}
    </span>
  )
}

/** "← All workshops": the back link at the top of a booking hero. */
export function HeroBackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="-ml-1 inline-flex items-center gap-1.5 rounded-full px-1 py-0.5 text-sm font-semibold text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
    >
      <ArrowLeft className="size-4" aria-hidden />
      {children}
    </Link>
  )
}
