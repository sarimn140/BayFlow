'use client'

import {
  useEffect,
  useRef,
  useState,
  type ComponentProps,
  type ReactNode,
  type RefObject,
} from 'react'

import { cn } from '@/lib/utils'

/** The sticky aside's offset under the 64px app bar, plus a 16px margin under it: 96 + 16. */
const STICKY_ROOM = 112

/**
 * Whether the element fits on the screen below the app bar, rechecked when it or the window
 * resizes. True until measured, so a short aside sticks from the first paint.
 */
function useFitsOnScreen(ref: RefObject<HTMLElement | null>): boolean {
  const [fits, setFits] = useState(true)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const check = () => setFits(element.offsetHeight + STICKY_ROOM <= window.innerHeight)
    const observer = new ResizeObserver(check) // also reports once on `observe`
    observer.observe(element)
    window.addEventListener('resize', check)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', check)
    }
  }, [ref])
  return fits
}

export interface DetailLayoutProps {
  /** The record's sections (concern, inspection, estimate, activity), stacked. */
  children: ReactNode
  /** The side cards: status + next action first, then customer, vehicle, totals. */
  aside: ReactNode
  /**
   * Where the aside sits while the layout is one column (phones, tablets, a narrow window): first,
   * so the status and next action come before the details (default), or after the main column.
   * It is the DOM order, so reading and focus order follow what is seen.
   */
  asideFirstOnMobile?: boolean
  /** Goes on the grid. */
  className?: string
}

/**
 * Detail page body (DESIGN.md "Detail pages"): a main column and a 360px side column.
 *
 * - Two columns only when the layout itself is 58rem (928px) wide, so the main column keeps about
 *   550px or more: a container query, not a screen breakpoint, because the shop sidebar takes 256px
 *   (at a 1024px screen the main column would be 320px). Until then, one column.
 * - The DOM order is the one-column order (`asideFirstOnMobile`), so a stacked page reads and
 *   tabs exactly as it looks; in two columns the grid places the aside in column 2, still read
 *   first as one whole column. No `order-*` anywhere.
 * - In two columns the aside sticks under the app bar, but only while it fits on the screen: a
 *   taller aside (two long cards on a short laptop) scrolls with the page instead, so its end is
 *   never out of reach and there is no scroll box inside the page.
 */
export function DetailLayout({
  children,
  aside,
  asideFirstOnMobile = true,
  className,
}: DetailLayoutProps) {
  const asideRef = useRef<HTMLElement>(null)
  const sticky = useFitsOnScreen(asideRef)

  const main = (
    <div className="min-w-0 space-y-6 @min-[58rem]/detail:col-start-1 @min-[58rem]/detail:row-start-1">
      {children}
    </div>
  )
  const side = (
    <aside
      ref={asideRef}
      className={cn(
        'min-w-0 space-y-6 @min-[58rem]/detail:col-start-2 @min-[58rem]/detail:row-start-1',
        sticky && '@min-[58rem]/detail:sticky @min-[58rem]/detail:top-24',
      )}
    >
      {aside}
    </aside>
  )

  return (
    // `w-full`: a query container sizes as if empty, so it must never be left to shrink-to-fit.
    <div className="@container/detail w-full">
      <div
        className={cn(
          'grid items-start gap-6 xl:gap-8 @min-[58rem]/detail:grid-cols-[minmax(0,1fr)_22.5rem]',
          className,
        )}
      >
        {asideFirstOnMobile ? side : main}
        {asideFirstOnMobile ? main : side}
      </div>
    </div>
  )
}

/**
 * For content inside a `DetailLayout` that belongs to one of its modes, e.g. a card shown in the
 * aside in two columns and in the main column in one (render it twice, one copy with each class).
 * The layout switches on its own width, so `lg:` / `max-lg:` would be wrong on a page with a sidebar.
 */
export const detailLayoutOnly = {
  /** Shown only while the layout has two columns. */
  twoColumns: '@max-[58rem]/detail:hidden',
  /** Shown only while the layout is one column. */
  oneColumn: '@min-[58rem]/detail:hidden',
} as const

/** The breakpoint from which `StickyActionBar` renders inline instead of pinned. */
export type StickyUntil = 'md' | 'lg' | 'xl'

// Full class strings, so Tailwind sees every one. Below the breakpoint the bar spans the page
// gutter (`-mx-4 sm:-mx-6`, and `lg:-mx-8` while it is still pinned on a large screen).
const INLINE_FROM: Record<StickyUntil, string> = {
  md: 'md:static md:mx-0 md:border-0 md:bg-transparent md:p-0 md:backdrop-blur-none',
  lg: 'lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none',
  xl: 'lg:-mx-8 lg:px-8 xl:static xl:mx-0 xl:border-0 xl:bg-transparent xl:p-0 xl:backdrop-blur-none',
}

export interface StickyActionBarProps extends ComponentProps<'div'> {
  children: ReactNode
  /**
   * Pinned to the bottom of the screen below this breakpoint, inline from it. `md` (default):
   * phones. `lg` / `xl`: tablets too, for a page whose actions only move beside the content on a
   * large screen (hide the bar there with `lg:hidden` / `xl:hidden` when they do).
   */
  pinnedUntil?: StickyUntil
}

/**
 * Sticky action bar (DESIGN.md "Sticky mobile actions"): pins the page's main actions to the
 * bottom of the screen below `pinnedUntil` (`md` by default); renders inline from there up.
 */
export function StickyActionBar({
  children,
  className,
  pinnedUntil = 'md',
  ...props
}: StickyActionBarProps) {
  return (
    <div
      {...props}
      className={cn(
        'sticky bottom-0 z-20 -mx-4 flex items-center justify-end gap-2 border-t border-border-faint bg-card/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md sm:-mx-6 sm:px-6',
        INLINE_FROM[pinnedUntil],
        className,
      )}
    >
      {children}
    </div>
  )
}
