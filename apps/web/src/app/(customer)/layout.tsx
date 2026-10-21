import type { ReactNode } from 'react'

import { PublicFooter } from '@/components/layout/public-footer'
import { PublicHeader } from '@/components/layout/public-header'
import { CallProvider } from '@/features/calls/call-provider'

/**
 * `(customer)` shell (spec 09 §2.3; DESIGN.md "App shell"): PublicHeader, the content column on
 * the cool-grey canvas (max-w-5xl, room for a detail page's side column), PublicFooter.
 * `proxy.ts` sends visitors without a session cookie to /login. TODO(auth): client
 * `RequireSession` (redirect when `GET /api/v1/me` resolves to null).
 */
export default function CustomerLayout({ children }: { children: ReactNode }) {
  return (
    // In-app calling (spec 05 §9.1): mounted in the shell so a call survives navigation.
    <CallProvider>
      <PublicHeader />
      <main id="main" tabIndex={-1} className="flex-1 overflow-x-clip bg-canvas outline-none">
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
          {children}
        </div>
      </main>
      <PublicFooter />
    </CallProvider>
  )
}
