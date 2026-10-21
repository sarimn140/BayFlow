import type { ReactNode } from 'react'

import { PosHeader } from '@/components/layout/pos-header'
import { SidebarProvider } from '@/components/ui/sidebar'
import { CallProvider } from '@/features/calls/call-provider'

/**
 * POS shell (spec 09 §2.3, spec 10 S-01; DESIGN.md "App shell"): the light 64px PosHeader over
 * the cool-grey canvas. The sidebar state lives here so the header's toggle can drive the shop
 * sidebar (rendered by the shop layout). `proxy.ts` guards `/pos/**` by cookie presence.
 * TODO(auth): client `RequireSession`.
 * Each child renders its own `<main id="main">` (the shop layout uses the sidebar inset).
 */
export default function PosLayout({ children }: { children: ReactNode }) {
  return (
    <SidebarProvider className="min-h-dvh flex-col bg-canvas">
      {/* In-app calling (spec 05 §9.1): the incoming-call panel and in-call bar on every POS page. */}
      <CallProvider>
        <PosHeader />
        <div className="flex flex-1 flex-col">{children}</div>
      </CallProvider>
    </SidebarProvider>
  )
}
