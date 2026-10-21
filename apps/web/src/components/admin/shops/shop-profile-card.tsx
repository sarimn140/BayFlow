import type { ReactNode } from 'react'

import { CardHeading } from '@/components/admin/overview/card-heading'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { formatDate } from '@/lib/format'
import type { AdminShop } from '@/lib/mock-admin'

function plural(count: number, one: string, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`
}

/** A-03 profile (spec 19 §5): who runs the shop, how to reach it and how it takes bookings. */
export function ShopProfileCard({ tenant }: { tenant: AdminShop }) {
  const { shop } = tenant
  const rows: ReadonlyArray<{ label: string; value: ReactNode }> = [
    {
      label: tenant.owners.length > 1 ? 'Owners' : 'Owner',
      value:
        tenant.owners.length > 0 ? (
          tenant.owners.map((owner) => owner.name).join(', ')
        ) : (
          <span className="text-danger-ink">No active owner</span>
        ),
    },
    { label: 'Phone', value: shop.phone },
    { label: 'Address', value: `${shop.address}, ${shop.city}` },
    {
      label: 'Public page',
      value: <span className="font-mono text-xs break-all">/shops/{shop.slug}</span>,
    },
    { label: 'Directory', value: shop.is_listed ? 'Listed' : 'Not listed' },
    {
      label: 'Slots',
      value: `${shop.slot_duration_minutes} min · ${plural(shop.slot_capacity, 'car')} each`,
    },
    {
      label: 'Rating',
      value: shop.rating === null ? 'No ratings yet' : `${shop.rating.toFixed(1)} out of 5`,
    },
    { label: 'Time zone', value: shop.timezone },
    { label: 'Joined', value: formatDate(tenant.createdAt) },
  ]

  return (
    <Card>
      <CardHeader>
        <CardHeading>Profile</CardHeading>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border-faint text-sm">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0"
            >
              <dt className="shrink-0 text-muted-foreground">{row.label}</dt>
              <dd className="min-w-0 text-right font-medium break-words text-foreground">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  )
}
