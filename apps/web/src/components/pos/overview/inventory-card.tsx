import { CircleCheck } from 'lucide-react'
import Link from 'next/link'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { formatPKR } from '@/lib/format'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import { available, plural, type InventoryHealth } from './overview-data'

const TILE =
  'flex h-full flex-col gap-1 rounded-xl bg-layer px-3 py-2.5 transition-colors duration-150 outline-none hover:bg-layer-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

/**
 * Inventory summary (spec 10 O-01 §6): stock value, low and out counts, open purchase orders and
 * the parts to restock first (OUT, then the least available), with "Open inventory".
 */
export function InventoryCard({ health, base }: { health: InventoryHealth; base: string }) {
  const running = health.lowCount - health.outCount
  const tiles = [
    {
      key: 'low',
      label: 'Running low',
      value: running,
      tone: running > 0 ? 'text-warning-ink' : 'text-foreground',
      href: `${base}/inventory`,
    },
    {
      key: 'out',
      label: 'Out of stock',
      value: health.outCount,
      tone: health.outCount > 0 ? 'text-danger-ink' : 'text-foreground',
      href: `${base}/inventory`,
    },
    {
      key: 'orders',
      label: 'On order',
      value: health.openPurchaseOrders,
      tone: 'text-foreground',
      href: `${base}/purchase-orders`,
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardHeading>Inventory health</CardHeading>
        <CardDescription>{plural(health.partsCount, 'part')} in stock</CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href={`${base}/inventory`}>Open inventory</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="gap-4">
        <div className="space-y-0.5">
          <p className="text-sm text-muted-foreground">Stock value</p>
          <p className="text-2xl font-extrabold tracking-tight text-foreground tabular-nums">
            {formatPKR(health.stockValue)}
          </p>
        </div>

        <ul className="grid grid-cols-3 gap-2">
          {tiles.map((tile) => (
            <li key={tile.key}>
              <Link href={tile.href} className={TILE}>
                <span className="text-xs font-medium text-muted-foreground">{tile.label}</span>
                <span className={cn('text-xl font-bold tabular-nums', tile.tone)}>
                  {tile.value}
                  {tile.key === 'orders' ? (
                    <span className="sr-only">
                      {' '}
                      open purchase {tile.value === 1 ? 'order' : 'orders'}
                    </span>
                  ) : (
                    <span className="sr-only"> {tile.value === 1 ? 'part' : 'parts'}</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>

        {health.restock.length > 0 ? (
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-foreground">Restock first</h3>
            <ul className="divide-y divide-border-faint">
              {health.restock.map((part) => {
                const left = available(part)
                const out = left <= 0
                return (
                  <li key={part.id} className="flex items-start justify-between gap-3 py-2.5">
                    <div className="min-w-0 space-y-0.5">
                      <p className="line-clamp-2 text-sm font-medium text-foreground">
                        {part.name}
                      </p>
                      <p className="text-xs text-helper tabular-nums">
                        <span className="font-mono">{part.sku}</span> · {Math.max(left, 0)}{' '}
                        available · reorder at {part.reorder_level}
                      </p>
                    </div>
                    <Badge variant={out ? 'destructive' : 'warning'} className="mt-0.5">
                      {out ? 'Out of stock' : 'Low'}
                    </Badge>
                  </li>
                )
              })}
            </ul>
          </div>
        ) : (
          <p className="flex items-start gap-2 rounded-xl bg-success-subtle px-3.5 py-3 text-sm text-success-ink">
            <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Every part is above its reorder level.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
