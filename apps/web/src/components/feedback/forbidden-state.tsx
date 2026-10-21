import { ShieldAlert } from 'lucide-react'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'

export interface ForbiddenStateProps {
  /** Who the area is for, e.g. "This area is for Service Advisors and Owners." */
  message: string
  /** The user's own home (spec 10 S-04). */
  homeHref: string
}

/** X-03 Forbidden (spec 10): shown in place of a section the user's role cannot open. */
export function ForbiddenState({ message, homeHref }: ForbiddenStateProps) {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-warning-subtle text-warning-ink">
          <ShieldAlert aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          You don&apos;t have access to this page
        </h1>
        <EmptyDescription className="text-base">{message}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={homeHref}>Go to my home</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
