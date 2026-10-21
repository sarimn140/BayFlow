'use client'

import { RouteError } from '@/components/feedback/route-error'

/** Error boundary for the public pages (spec 10 X-05). */
export default function ErrorBoundary({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  return <RouteError error={error} retry={retry} homeHref="/" />
}
