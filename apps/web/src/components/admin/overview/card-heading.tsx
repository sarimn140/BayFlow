import type { ReactNode } from 'react'

import { CardTitle } from '@/components/ui/card'

/** A card title that is an `<h2>` in the page outline (the page header or hero holds the `<h1>`). */
export function CardHeading({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <CardTitle>
      <h2 id={id} className="flex flex-wrap items-center gap-2 font-semibold">
        {children}
      </h2>
    </CardTitle>
  )
}
