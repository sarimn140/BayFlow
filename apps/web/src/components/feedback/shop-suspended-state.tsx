import { Ban } from 'lucide-react'
import Link from 'next/link'

import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'

/** 403 `SHOP_SUSPENDED` (D96): the shop is suspended by BayFlow, for every member alike. */
export function ShopSuspendedState() {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-danger-subtle text-danger-ink">
          <Ban aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          This shop is suspended
        </h1>
        <EmptyDescription className="text-base">
          BayFlow has suspended this shop, so its workspace is closed for now. Your records are
          kept. Contact BayFlow support to have it reactivated.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild variant="outline">
          <Link href="/">Back to the website</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
