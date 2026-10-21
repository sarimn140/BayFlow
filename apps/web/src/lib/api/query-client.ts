import { environmentManager, QueryClient } from '@tanstack/react-query'

import { ApiError, NetworkError } from './errors'

const MAX_RETRIES = 2

/**
 * Retry only what a retry can fix: network failures and 5xx, at most twice. A 4xx is a real
 * answer — retrying a 403/404 only delays the error UI (spec 09 §2.7).
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_RETRIES) return false
  if (error instanceof NetworkError) return true
  return error instanceof ApiError && error.status >= 500
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Freshness comes from polling and realtime invalidation; this only avoids refetch storms.
        staleTime: 10_000,
        retry: shouldRetryQuery,
      },
      mutations: {
        // Booking actions are not idempotent (D30).
        retry: false,
      },
    },
  })
}

let browserQueryClient: QueryClient | undefined

/**
 * TanStack Query's Next.js App Router pattern: a new client per server request, one singleton in
 * the browser (so a suspending first render cannot throw the cache away).
 */
export function getQueryClient(): QueryClient {
  if (environmentManager.isServer()) return makeQueryClient()
  browserQueryClient ??= makeQueryClient()
  return browserQueryClient
}
