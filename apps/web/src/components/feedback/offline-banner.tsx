'use client'

import { WifiOff } from 'lucide-react'
import { useSyncExternalStore } from 'react'

function subscribe(callback: () => void) {
  window.addEventListener('online', callback)
  window.addEventListener('offline', callback)
  return () => {
    window.removeEventListener('online', callback)
    window.removeEventListener('offline', callback)
  }
}

/** X-05 `OfflineBanner` (spec 09 §4.8): shown whenever the browser is offline. */
export function OfflineBanner() {
  // The server (and hydration) assume online, so nothing renders until the browser says otherwise.
  const online = useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    () => true,
  )
  if (online) return null

  return (
    <div
      role="status"
      className="sticky top-0 z-[70] flex items-center justify-center gap-2 border-b border-status-estimate-border bg-warning-subtle px-4 py-2.5 text-sm font-medium text-warning-ink"
    >
      <WifiOff className="size-4 shrink-0" aria-hidden="true" />
      You&apos;re offline — changes can&apos;t be saved until you reconnect.
    </div>
  )
}
