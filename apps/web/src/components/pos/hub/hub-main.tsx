import type { ReactNode } from 'react'

/**
 * The content landmark of the three POS pages outside a shop (DESIGN.md §3): the hub `/pos`, new
 * shop `/pos/shops/new` and the all-shops summary `/pos/summary` have no sidebar, so they render
 * their own `<main>` (the skip link's target) at the shell's width and gutters. Horizontal overflow
 * is clipped as a safety net; wide tables scroll inside their card.
 */
export function HubMain({ children }: { children: ReactNode }) {
  return (
    <main id="main" tabIndex={-1} className="flex-1 overflow-x-clip outline-none">
      <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        {children}
      </div>
    </main>
  )
}
