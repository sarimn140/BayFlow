import { Ban, ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Card, CardDescription, CardHeader } from '@/components/ui/card'
import { formatDateTime } from '@/lib/format'
import type { AdminShop } from '@/lib/mock-admin'

import { CardHeading } from './card-heading'

/** A-01 "suspended shops needing attention" (spec 19 §5): each opens A-03 to reactivate it. */
export function SuspendedShopsCard({ shops }: { shops: ReadonlyArray<AdminShop> }) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>
          Suspended shops
          <Badge variant="destructive" className="tabular-nums">
            {shops.length}
          </Badge>
        </CardHeading>
        <CardDescription>
          Hidden from customers and closed to their staff. Open a shop to reactivate it once the
          issue is resolved.
        </CardDescription>
      </CardHeader>
      <ul className="divide-y divide-border-faint">
        {shops.map((tenant) => (
          <li key={tenant.shop.id}>
            <Link
              href={`/admin/shops/${encodeURIComponent(tenant.shop.id)}`}
              className="group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-danger-subtle text-danger-ink">
                <Ban className="size-5" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="block truncate text-sm font-medium text-foreground">
                  {tenant.shop.name}
                  <span className="font-normal text-muted-foreground"> · {tenant.shop.city}</span>
                </span>
                {tenant.suspension ? (
                  <>
                    <span className="line-clamp-2 text-sm text-muted-foreground">
                      {tenant.suspension.reason}
                    </span>
                    <span className="block truncate text-xs text-helper">
                      Suspended {formatDateTime(tenant.suspension.at)} by {tenant.suspension.byName}
                    </span>
                  </>
                ) : null}
              </span>
              <ChevronRight
                className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  )
}
