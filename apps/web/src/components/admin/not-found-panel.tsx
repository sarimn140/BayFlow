import { ArrowLeft, SearchX } from 'lucide-react'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'

/**
 * An unknown ID in the console (spec 03: the same 404 everywhere; spec 09 §4.8 copy). It never
 * says whether the item exists elsewhere (D20). The page's `<h1>`, on the same dashed card as the
 * forbidden state.
 */
export function NotFoundPanel({ backHref, backLabel }: { backHref: string; backLabel: string }) {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <SearchX aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          We couldn&apos;t find that.
        </h1>
        <EmptyDescription className="text-base">
          It may have been mistyped, or it never existed.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={backHref}>
            <ArrowLeft data-icon="inline-start" aria-hidden="true" />
            {backLabel}
          </Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
