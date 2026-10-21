import type { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { CardTitle } from '@/components/ui/card'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { cn } from '@/lib/utils'

/** A card title that is an `<h2>` in the page outline (the page header holds the `<h1>`). */
export function CardHeading({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <CardTitle>
      <h2 id={id} className="flex flex-wrap items-center gap-2 font-semibold">
        {children}
      </h2>
    </CardTitle>
  )
}

/** A licence plate as it reads on the car: monospaced in a small bordered tag. */
export function PlateTag({ plate, size = 'sm' }: { plate: string; size?: 'sm' | 'md' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border border-border-medium bg-card font-mono font-semibold whitespace-nowrap text-foreground',
        size === 'md' ? 'px-2 py-0.5 text-base' : 'px-1.5 text-sm',
      )}
    >
      <span className="sr-only">Plate </span>
      {plate}
    </span>
  )
}

/** A page-level "not found" (D20): never says whether the record exists elsewhere. */
export function NotFoundState({
  icon: Icon,
  title,
  description,
  href,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  href: string
  action: string
}) {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Icon aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">{title}</h1>
        <EmptyDescription className="text-base">{description}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={href}>{action}</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
