/**
 * Session-expiry signal (spec 09 §2.8, X-04). The API client emits it on the first 401 from a
 * non-probe call; the auth feature subscribes and runs the recovery (clear the query cache, stop
 * realtime, best-effort logout, redirect to `/login?reason=expired&next=…`).
 *
 * The web app never reads, stores or decodes tokens: the httpOnly `bf_session` cookie is set and
 * checked by the API only (D8).
 */

type SessionExpiredListener = () => void

const listeners = new Set<SessionExpiredListener>()
let expired = false

/** Emits once until `resetSessionExpired()` — many parallel 401s produce one redirect. */
export function emitSessionExpired(): void {
  if (expired) return
  expired = true
  for (const listener of listeners) listener()
}

/** Subscribes to session expiry; returns the unsubscribe function. */
export function onSessionExpired(listener: SessionExpiredListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Call after a successful login so a later expiry is reported again. */
export function resetSessionExpired(): void {
  expired = false
}
