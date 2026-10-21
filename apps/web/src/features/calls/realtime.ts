'use client'

/**
 * The shared realtime socket (D70, spec 03 §6): `GET /api/v1/realtime/ticket` → `WS /api/v1/ws`
 * with a fresh 60-second ticket on every (re)connect, a ping every 25 s, and reconnects with
 * backoff. Without a real API session the ticket request fails and the hook retries slowly, so it
 * connects on its own after the person signs in.
 */
import { useEffect, useRef } from 'react'

import { getRealtimeTicket } from './api'
import { REALTIME_URL } from './config'

export interface RealtimeMessage {
  type: string
  data: unknown
}

const PING_EVERY_MS = 25_000
const MAX_BACKOFF_MS = 30_000

export function useRealtime(enabled: boolean, onMessage: (message: RealtimeMessage) => void) {
  const handler = useRef(onMessage)
  useEffect(() => {
    handler.current = onMessage
  })

  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let ping: ReturnType<typeof setInterval> | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let stopped = false

    const schedule = (delay: number) => {
      if (stopped) return
      retry = setTimeout(connect, delay)
    }

    async function connect() {
      let ticket: string
      try {
        ticket = await getRealtimeTicket()
      } catch {
        attempt += 1
        schedule(MAX_BACKOFF_MS) // not signed in to the API (yet): try again later
        return
      }
      if (stopped) return
      socket = new WebSocket(`${REALTIME_URL}?ticket=${encodeURIComponent(ticket)}`)
      socket.onopen = () => {
        attempt = 0
        ping = setInterval(
          () => socket?.send(JSON.stringify({ type: 'ping', data: {} })),
          PING_EVERY_MS,
        )
      }
      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const message = JSON.parse(event.data) as RealtimeMessage
          if (message.type !== 'pong') handler.current(message)
        } catch {
          // not JSON: ignore
        }
      }
      socket.onclose = () => {
        clearInterval(ping)
        socket = null
        attempt += 1
        schedule(Math.min(1000 * 2 ** Math.min(attempt, 5), MAX_BACKOFF_MS))
      }
    }

    void connect()
    return () => {
      stopped = true
      clearTimeout(retry)
      clearInterval(ping)
      socket?.close()
    }
  }, [enabled])
}
