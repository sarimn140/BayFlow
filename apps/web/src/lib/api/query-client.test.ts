// @vitest-environment node
import { describe, expect, it } from 'vitest'

import { ApiError, NetworkError } from './errors'
import { makeQueryClient, shouldRetryQuery } from './query-client'

const apiError = (status: number) =>
  ApiError.fromResponse(new Response(null, { status }), { code: 'INTERNAL_ERROR' })

describe('query retry policy (spec 09 §2.7)', () => {
  it('retries network failures and 5xx at most twice', () => {
    expect(shouldRetryQuery(0, new NetworkError())).toBe(true)
    expect(shouldRetryQuery(1, apiError(503))).toBe(true)
    expect(shouldRetryQuery(2, apiError(503))).toBe(false)
  })

  it('never retries a 4xx answer', () => {
    for (const status of [401, 403, 404, 409, 422, 429]) {
      expect(shouldRetryQuery(0, apiError(status))).toBe(false)
    }
  })

  it('configures queries and mutations', () => {
    const defaults = makeQueryClient().getDefaultOptions()
    expect(defaults.queries?.staleTime).toBe(10_000)
    expect(defaults.mutations?.retry).toBe(false)
  })
})
