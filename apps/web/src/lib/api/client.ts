/**
 * The one module that creates API clients (D50, spec 09 §2.6). Types come only from the
 * generated `schema.d.ts` (glossary §13: never hand-written). Components never call `api.*`
 * directly; each endpoint is wrapped once in `features/<domain>/api.ts`.
 */
import createClient, { type ClientOptions, type Middleware } from 'openapi-fetch'

import { emitSessionExpired } from '@/lib/auth/session'

import { ApiError, NetworkError } from './errors'
import type { paths } from './schema'

/** 401 on these paths is an expected answer (wrong password, anonymous visitor), not an expired session. */
const AUTH_PROBES: ReadonlySet<string> = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/register-owner',
  '/api/v1/me',
])

/** Exported for tests; attached to the browser client below. */
export const sessionMiddleware: Middleware = {
  onResponse({ response, schemaPath }) {
    if (response.status === 401 && !AUTH_PROBES.has(schemaPath)) emitSessionExpired()
    return undefined
  },
}

export function createApiClient(baseUrl: string, options: Omit<ClientOptions, 'baseUrl'> = {}) {
  return createClient<paths>({ ...options, baseUrl })
}

/**
 * Browser client. `baseUrl` "" keeps every request same-origin (`/api/v1/…`); `next.config.ts`
 * rewrites `/api/:path*` to the API (D7). The httpOnly `bf_session` cookie travels with each
 * request; the app never touches tokens (D8).
 */
export const api = createApiClient('', { credentials: 'include' })
api.use(sessionMiddleware)

type ApiResult<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error?: unknown; response: Response }

/**
 * openapi-fetch resolves to `{ data } | { error }`; TanStack Query needs thrown errors.
 * Throws `NetworkError` when fetch rejects and `ApiError` (problem+json → typed `code`) for
 * any non-2xx response.
 */
export async function unwrap<T>(call: Promise<ApiResult<T>>): Promise<T> {
  let result: ApiResult<T>
  try {
    result = await call
  } catch (cause) {
    throw new NetworkError(cause)
  }
  if (!result.response.ok) throw ApiError.fromResponse(result.response, result.error)
  // response.ok, so this is openapi-fetch's success member (data is undefined only for 204).
  return result.data as T
}
