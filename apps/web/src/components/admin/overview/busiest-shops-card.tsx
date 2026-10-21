import { ChevronRight, Store } from 'lucide-react'
import Link from 'next/link'

import { EmptyState } from '@/components/layout/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import type { AdminShop } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import { plural } from './overview-data'

/** A-01 "top shops" (spec 19 §5): the shops with the most bookings, each opening A-03. */
export function BusiestShopsCard({
  shops,
  className,
}: {
  shops: ReadonlyArray<AdminShop>
  className?: string
}) {
  return (
    <Card className={cn('gap-0 py-0', className)}>
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Busiest shops</CardHeading>
        <CardDescription>Ranked by bookings, all time</CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/admin/shops">All shops</Link>
          </Button>
        </CardAction>
      </CardHeader>
      {shops.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={Store}
          title="No shops yet"
          description="Shops appear here as soon as an owner creates one."
          className="p-6 sm:p-8"
        />
      ) : (
        <ol className="divide-y divide-border-faint">
          {shops.map((tenant, index) => (
            <li key={tenant.shop.id}>
              <Link
                href={`/admin/shops/${encodeURIComponent(tenant.shop.id)}`}
                className="group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:px-6"
              >
                <span
                  aria-hidden="true"
                  className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-sm font-semibold text-muted-foreground tabular-nums"
                >
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 space-y-0.5">
                  <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="min-w-0 truncate text-sm font-medium text-foreground">
                      {tenant.shop.name}
                    </span>
                    {tenant.suspension ? <Badge variant="destructive">Suspended</Badge> : null}
                  </span>
                  <span className="block truncate text-xs text-helper">
                    {tenant.shop.city} · {plural(tenant.activeMembers, 'member')}
                  </span>
                </span>
                <span
                  className={cn(
                    'shrink-0 text-right text-base font-bold tabular-nums',
                    tenant.bookingsTotal > 0 ? 'text-foreground' : 'text-helper',
                  )}
                >
                  {tenant.bookingsTotal}
                  <span className="sr-only">
                    {' '}
                    {tenant.bookingsTotal === 1 ? 'booking' : 'bookings'}
                  </span>
                </span>
                <ChevronRight
                  className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
