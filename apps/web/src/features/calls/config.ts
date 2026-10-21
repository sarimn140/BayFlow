/**
 * Calling switches (spec 05 §10): the call UI exists only when the LiveKit URL is configured.
 * `NEXT_PUBLIC_*` values are inlined at build time. The room URL actually used comes from each
 * `CallConnection`; this one is only the on/off switch.
 */
export const CALLING_ENABLED = Boolean(process.env.NEXT_PUBLIC_CALL_PROVIDER_URL)

/** Browser WebSocket URL of the API (`/api/v1/ws`, D70); the ticket is added per connection. */
export const REALTIME_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:4000/api/v1/ws'
