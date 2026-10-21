'use client'

import { useSyncExternalStore } from 'react'

const subscribeNever = () => () => {}

/**
 * "Now" to the minute, as an ISO string: read on the client only, never while rendering on the
 * server (spec 09 §2.4 rule 7), and stable within a minute so it is a valid external-store
 * snapshot. Rounded up, so something that happened this minute reads "seconds ago", never "in
 * seconds". `null` on the server and during hydration.
 */
export function useNowMinute(): string | null {
  return useSyncExternalStore(
    subscribeNever,
    () => new Date(Math.ceil(Date.now() / 60_000) * 60_000).toISOString(),
    () => null,
  )
}
