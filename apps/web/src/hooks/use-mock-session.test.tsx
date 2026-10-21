import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { endMockSession, SIGNED_IN_MARKER, useHasMockSession } from './use-mock-session'

function clearCookies() {
  for (const name of ['bf_session', SIGNED_IN_MARKER]) {
    document.cookie = `${name}=; path=/; max-age=0`
  }
}

describe('useHasMockSession', () => {
  afterEach(clearCookies)

  it('is signed out without a session cookie', () => {
    const { result } = renderHook(() => useHasMockSession())
    expect(result.current).toBe(false)
  })

  it('reads the mock session cookie', () => {
    document.cookie = 'bf_session=active_1; path=/'
    const { result } = renderHook(() => useHasMockSession())
    expect(result.current).toBe(true)
  })

  it("stays signed in on the marker alone (the API's httpOnly bf_session is invisible)", () => {
    document.cookie = `${SIGNED_IN_MARKER}=1; path=/`
    const { result } = renderHook(() => useHasMockSession())
    expect(result.current).toBe(true)
    act(() => endMockSession())
    expect(result.current).toBe(false)
  })
})
