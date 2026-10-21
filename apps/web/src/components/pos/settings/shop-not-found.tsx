import { Store } from 'lucide-react'
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
 * D20: an unknown shop reads as "not found", never as someone else's data (the same state as the
 * shop overview's).
 */
export function ShopNotFound() {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Store aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          We couldn&apos;t find that shop
        </h1>
        <EmptyDescription className="text-base">
          Check the link, or open one of your shops from the workshop hub.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href="/pos">Go to my shops</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
