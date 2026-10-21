import 'server-only'

import { createApiClient } from './client'

/**
 * Server Components only, and only for `/api/v1/public/*` (spec 09 §2.4 rule 2, §2.6).
 * Node cannot fetch relative URLs, so this client calls the API origin directly. Authenticated
 * data is never fetched on the server, and responses are never cached (D61).
 */
const apiBaseUrl = (process.env.API_BASE_URL || 'http://localhost:4000').replace(/\/+$/, '')

export const serverApi = createApiClient(apiBaseUrl, { cache: 'no-store' })
