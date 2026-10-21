'use client'

import { useSyncExternalStore } from 'react'

/**
 * Mock sign-in state: login sets a readable `bf_session` cookie (lib/mock-auth). The real session
 * cookie is httpOnly and set by the API (D8); `GET /api/v1/me` replaces this hook.
 *
 * When the login also signs in to the API (in-app calling, D105), that httpOnly `bf_session` wins:
 * the browser neither lets the mock cookie replace it nor shows it to scripts. `SIGNED_IN_MARKER`
 * is the readable flag that keeps the header signed in then.
 */
const SESSION_COOKIE = 'bf_session'
export const SIGNED_IN_MARKER = 'bf_signed_in'

function subscribe(callback: () => void) {
  window.addEventListener('bf:store-update', callback)
  window.addEventListener('focus', callback)
  return () => {
    window.removeEventListener('bf:store-update', callback)
    window.removeEventListener('focus', callback)
  }
}

const hasSession = () =>
  document.cookie
    .split('; ')
    .some(
      (cookie) =>
        cookie.startsWith(`${SESSION_COOKIE}=`) || cookie.startsWith(`${SIGNED_IN_MARKER}=`),
    )

/** True when someone is signed in (false while the server renders). */
export function useHasMockSession(): boolean {
  return useSyncExternalStore(subscribe, hasSession, () => false)
}

/** Signs out of the mock session; subscribers update right away. */
export function endMockSession(): void {
  document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0; SameSite=Lax`
  document.cookie = `${SIGNED_IN_MARKER}=; path=/; max-age=0; SameSite=Lax`
  window.dispatchEvent(new CustomEvent('bf:store-update', { detail: { key: 'session' } }))
}
