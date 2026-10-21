/**
 * The real API session next to the mock one (D102 bridge). Signing in on the login form also
 * signs in to the API with the same e-mail and password, which sets the httpOnly `bf_session`
 * cookie (D8); calls need it. Failure is silent here: the mock screens keep working and the call
 * UI explains that calling needs the account's real password. Skipped when calling is off, and
 * bounded so a slow or unreachable API never holds up the login.
 */
import { api } from '@/lib/api/client'
import { resetSessionExpired } from '@/lib/auth/session'

import { CALLING_ENABLED } from './config'

const SIGN_IN_TIMEOUT_MS = 5_000

export async function signInToApi(email: string, password: string): Promise<boolean> {
  if (!CALLING_ENABLED) return false
  try {
    const result = await api.POST('/api/v1/auth/login', {
      body: { email, password },
      signal: AbortSignal.timeout(SIGN_IN_TIMEOUT_MS),
    })
    if (result.response.ok) resetSessionExpired()
    return result.response.ok
  } catch {
    return false
  }
}

export async function signOutOfApi(): Promise<void> {
  try {
    await api.POST('/api/v1/auth/logout')
  } catch {
    // best effort: the cookie expires on its own
  }
}
