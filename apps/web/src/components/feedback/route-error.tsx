'use client'

import { CircleAlert } from 'lucide-react'
import Link from 'next/link'
import { useEffect } from 'react'

import { Button } from '@/components/ui/button'

export interface RouteErrorProps {
  error: Error & { digest?: string }
  /** Next 16.3+ `retry()`: re-fetches and re-renders the failed segment. */
  retry: () => void
  homeHref?: string
}

/** Body of every `error.tsx` boundary (spec 10 X-05): human message, Try again, Go home. */
export function RouteError({ error, retry, homeHref = '/' }: RouteErrorProps) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="px-4 py-12 sm:py-16">
      <div className="mx-auto flex max-w-lg flex-col items-center gap-4 rounded-3xl border border-border bg-card px-6 py-10 text-center shadow-xs sm:px-10">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-danger-subtle text-danger-ink">
          <CircleAlert aria-hidden="true" className="size-7" />
        </span>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
          Something went wrong
        </h1>
        <p className="text-base text-muted-foreground">
          Please try again. If it keeps happening, go back to the start.
        </p>
        {error.digest ? (
          <p className="text-xs text-helper">
            Reference: <span className="font-mono">{error.digest}</span>
          </p>
        ) : null}
        <div className="flex flex-wrap justify-center gap-2 pt-2">
          <Button onClick={() => retry()}>Try again</Button>
          <Button asChild variant="outline">
            <Link href={homeHref}>Go home</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
