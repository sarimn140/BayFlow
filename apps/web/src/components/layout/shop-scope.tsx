'use client'

import type { ReactNode } from 'react'

import { SidebarInset } from '@/components/ui/sidebar'

import { PosSidebar } from './pos-sidebar'
import { SectionGate } from './section-gate'
import { ShopNotFoundState, useShopMembership } from './shop-membership'

/** The page column of a shop: max-w-7xl on the canvas, 24/32px gutters (DESIGN.md). */
const PAGE = 'mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8'

/**
 * Shop scope (spec 09 §2.8, D20): a member gets the shop's sidebar (their role's sections) and
 * the gated section; anyone else gets the 404 view on its own — no sidebar, so not even the
 * shop's name shows. Until this browser's session is read, the page renders its own skeleton in
 * the usual shell.
 */
export function ShopScope({ shopId, children }: { shopId: string; children: ReactNode }) {
  const { ready, membership } = useShopMembership(shopId)

  if (ready && !membership) {
    return (
      <main id="main" tabIndex={-1} className="flex-1 overflow-x-clip bg-canvas outline-none">
        <div className={PAGE}>
          <ShopNotFoundState />
        </div>
      </main>
    )
  }

  return (
    <div className="flex flex-1">
      <PosSidebar shopId={shopId} role={membership?.role} />
      <SidebarInset
        id="main"
        tabIndex={-1}
        className="min-w-0 overflow-x-clip bg-canvas outline-none"
      >
        <div className={PAGE}>
          <SectionGate shopId={shopId}>{children}</SectionGate>
        </div>
      </SidebarInset>
    </div>
  )
}
