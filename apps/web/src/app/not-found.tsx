import { SearchX } from 'lucide-react'
import type { Metadata } from 'next'
import Link from 'next/link'

import { Logo } from '@/components/layout/logo'
import { Button } from '@/components/ui/button'

export const metadata: Metadata = { title: 'Page not found' }

/**
 * X-02 (spec 10): unknown URLs. Never says whether a resource exists elsewhere (D20, D21).
 * TODO(auth): link to the user's home via `resolveHome` once `GET /api/v1/me` is wired.
 */
export default function NotFound() {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="bg-hero flex flex-1 flex-col items-center justify-center gap-8 px-4 py-16 text-center outline-none"
    >
      <Link
        href="/"
        aria-label="BayFlow home"
        className="rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring focus-visible:outline-solid"
      >
        <Logo />
      </Link>
      <div className="flex max-w-lg flex-col items-center gap-4 rounded-3xl border border-border bg-card px-6 py-10 shadow-xs sm:px-10">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-brand-blue-subtle text-brand-blue-ink">
          <SearchX aria-hidden="true" className="size-7" />
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
          We couldn&apos;t find that.
        </h1>
        <p className="max-w-prose text-base text-muted-foreground">
          The page may have moved, or you may not have access to it.
        </p>
        <Button asChild size="lg" className="mt-2">
          <Link href="/">Go home</Link>
        </Button>
      </div>
    </main>
  )
}
