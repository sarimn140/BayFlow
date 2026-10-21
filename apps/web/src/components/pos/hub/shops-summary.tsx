'use client'

import {
  ArrowLeft,
  ArrowRight,
  Ban,
  CalendarDays,
  CarFront,
  Clock,
  PackageX,
  Store,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo } from 'react'

import { ForbiddenState } from '@/components/feedback/forbidden-state'
import { DataTableCard } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { StatCard, type StatTone } from '@/components/layout/stat-card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { formatDate } from '@/lib/format'
import { getShopSuspensions } from '@/lib/mock-admin'
import { homePathFor } from '@/lib/mock-auth'
import {
  getBookings,
  getCurrentUser,
  getInventory,
  getShops,
  getTeamMembers,
  setCurrentUser,
  type MockShop,
} from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import {
  listOf,
  ownedShopIds,
  ownerSummary,
  plural,
  summaryTotals,
  type SummaryMetric,
} from './hub-data'

const METRICS: ReadonlyArray<{
  key: SummaryMetric
  label: string
  icon: LucideIcon
  hint: string
}> = [
  {
    key: 'today',
    label: "Today's bookings",
    icon: CalendarDays,
    hint: 'Booked for today, not cancelled',
  },
  {
    key: 'needsAction',
    label: 'Needs action',
    icon: Clock,
    hint: 'Intake, estimates and pick-up calls',
  },
  { key: 'inProgress', label: 'In progress', icon: Wrench, hint: 'With technicians, parts or QC' },
  {
    key: 'ready',
    label: 'Ready for pick-up',
    icon: CarFront,
    hint: 'Passed QC, waiting for the customer',
  },
  {
    key: 'lowStock',
    label: 'Low stock',
    icon: PackageX,
    hint: 'Parts at or below their reorder level',
  },
]

/** Phones: today's bookings on its own row, then pairs; tablets 2 + 3; wide screens one row. */
const TILE_SPAN = [
  'col-span-2 md:col-span-3 xl:col-span-1',
  'md:col-span-3 xl:col-span-1',
  'md:col-span-2 xl:col-span-1',
  'md:col-span-2 xl:col-span-1',
  'md:col-span-2 xl:col-span-1',
] as const

const TILE_GRID = 'grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-6 xl:grid-cols-5'

function toneOf(metric: SummaryMetric, value: number): StatTone {
  if (metric === 'needsAction' || metric === 'lowStock') return value > 0 ? 'warning' : 'default'
  if (metric === 'inProgress') return 'brand'
  if (metric === 'ready') return 'success'
  return 'default'
}

/** A count in the table: work waiting and low stock stand out as chips; zeros recede. */
function MetricValue({ metric, value }: { metric: SummaryMetric; value: number }) {
  if (value > 0 && metric === 'needsAction') {
    return (
      <Badge variant="attention" className="tabular-nums">
        {value}
      </Badge>
    )
  }
  if (value > 0 && metric === 'lowStock') {
    return (
      <Badge variant="warning" className="tabular-nums">
        {value}
      </Badge>
    )
  }
  return <span className={value === 0 ? 'text-helper' : 'text-foreground'}>{value}</span>
}

function BackToHub() {
  return (
    <Link
      href="/pos"
      className="-ml-1 inline-flex w-fit items-center gap-1.5 rounded-full px-1 py-0.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      Workshop hub
    </Link>
  )
}

/**
 * O-07 Multi-shop summary (spec 10, P1; E-32): today across every shop the owner runs — KPI totals
 * on top, then one row per shop (stacked cards below `lg`) with an "Open" that switches to that
 * shop's overview. For owners of two or more shops; suspended shops are left out (D99).
 */
export function ShopsSummary() {
  const router = useRouter()
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const user = useMockStore(getCurrentUser)
  const shops = useMockStore(getShops)
  const team = useMockStore(getTeamMembers)
  const bookings = useMockStore(getBookings)
  const parts = useMockStore(getInventory)
  const suspensions = useMockStore(getShopSuspensions)

  const ownedIds = useMemo(() => ownedShopIds(user.email, team), [user.email, team])
  const summary = useMemo(
    () =>
      nowIso === null
        ? null
        : ownerSummary({
            shops,
            ownedIds,
            bookings,
            parts,
            suspendedIds: new Set(Object.keys(suspensions)),
            now: new Date(nowIso),
          }),
    [nowIso, shops, ownedIds, bookings, parts, suspensions],
  )

  const openShop = (shop: MockShop) => {
    setCurrentUser({ ...user, shopId: shop.id, shopName: shop.name })
    router.push(`/pos/shops/${shop.id}/overview`)
  }

  // "Today" is read on the client only, so the figures wait for this browser's data and clock.
  if (!ready || nowIso === null || summary === null) return <SummarySkeleton />

  if (user.role !== 'OWNER' || ownedIds.size < 2) {
    return (
      <>
        <BackToHub />
        <ForbiddenState
          message="The all-shops summary is for owners of two or more shops."
          homeHref={homePathFor(user)}
        />
      </>
    )
  }

  const { rows, suspended } = summary
  const totals = summaryTotals(rows)

  return (
    <>
      <PageHeader
        back={{ href: '/pos', label: 'Workshop hub' }}
        eyebrow={`${plural(rows.length, 'shop')} · ${formatDate(nowIso)}`}
        title="All shops"
        description="Today across the shops you own, at a glance. Open a shop to act on it."
      />

      {suspended.length > 0 ? <SuspendedNotice shops={suspended} /> : null}

      {rows.length === 0 ? (
        <EmptyState
          tone="neutral"
          icon={Store}
          title="No shops to summarise"
          description="Every shop you own is suspended, so there are no figures to show."
        />
      ) : (
        <>
          <section aria-labelledby="summary-totals">
            <h2 id="summary-totals" className="sr-only">
              Totals across your shops
            </h2>
            <div className={TILE_GRID}>
              {METRICS.map(({ key, label, icon, hint }, index) => (
                <StatCard
                  key={key}
                  label={label}
                  value={totals[key]}
                  icon={icon}
                  hint={hint}
                  tone={toneOf(key, totals[key])}
                  className={TILE_SPAN[index]}
                />
              ))}
            </div>
          </section>

          <DataTableCard
            title={<span id="summary-by-shop">By shop</span>}
            description="Today's figures for each shop, by name."
          >
            {/* Phones and tablets: one card per shop */}
            <ul
              aria-labelledby="summary-by-shop"
              className="divide-y divide-border-faint lg:hidden"
            >
              {rows.map((row) => (
                <li key={row.shop.id} className="space-y-4 px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-base font-semibold text-foreground">
                        {row.shop.name}
                      </h3>
                      <p className="truncate text-sm text-muted-foreground">{row.shop.city}</p>
                    </div>
                    <OpenShopButton shop={row.shop} onOpen={openShop} />
                  </div>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-3 min-[400px]:grid-cols-3 sm:grid-cols-5">
                    {METRICS.map(({ key, label }) => (
                      <div key={key} className="min-w-0">
                        <dt className="text-xs text-helper">{label}</dt>
                        <dd className="mt-1 text-sm font-semibold tabular-nums">
                          <MetricValue metric={key} value={row[key]} />
                        </dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>

            {/* Desktop: the table, with the all-shops totals as its footer */}
            <div className="hidden lg:block">
              <Table aria-labelledby="summary-by-shop">
                <TableHeader>
                  <TableRow>
                    <TableHead>Shop</TableHead>
                    {METRICS.map(({ key, label }) => (
                      <TableHead key={key} className="text-right">
                        {label}
                      </TableHead>
                    ))}
                    <TableHead className="w-0">
                      <span className="sr-only">Open</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.shop.id}>
                      <TableCell>
                        <p className="font-semibold text-foreground">{row.shop.name}</p>
                        <p className="text-xs text-helper">{row.shop.city}</p>
                      </TableCell>
                      {METRICS.map(({ key }) => (
                        <TableCell key={key} className="text-right tabular-nums">
                          <MetricValue metric={key} value={row[key]} />
                        </TableCell>
                      ))}
                      <TableCell>
                        <OpenShopButton shop={row.shop} onOpen={openShop} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                <TableFooter>
                  <TableRow className="hover:bg-transparent">
                    <TableCell>All shops</TableCell>
                    {METRICS.map(({ key }) => (
                      <TableCell key={key} className="text-right tabular-nums">
                        {totals[key]}
                      </TableCell>
                    ))}
                    <TableCell />
                  </TableRow>
                </TableFooter>
              </Table>
            </div>
          </DataTableCard>
        </>
      )}
    </>
  )
}

function OpenShopButton({ shop, onOpen }: { shop: MockShop; onOpen: (shop: MockShop) => void }) {
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => onOpen(shop)}
      aria-label={`Open ${shop.name}`}
      className="shrink-0"
    >
      Open
      <ArrowRight data-icon="inline-end" aria-hidden="true" />
    </Button>
  )
}

/** D99: suspended shops are left out of the figures; say which, so none goes missing silently. */
function SuspendedNotice({ shops }: { shops: ReadonlyArray<MockShop> }) {
  const one = shops.length === 1
  return (
    <Alert variant="warning">
      <Ban aria-hidden="true" />
      <AlertTitle>
        {listOf(shops.map((shop) => shop.name))} {one ? 'is' : 'are'} suspended
      </AlertTitle>
      <AlertDescription>
        BayFlow has suspended {one ? 'this shop' : 'these shops'}, so {one ? 'its' : 'their'}{' '}
        figures are left out of this summary. Contact BayFlow support to have {one ? 'it' : 'them'}{' '}
        reactivated.
      </AlertDescription>
    </Alert>
  )
}

/** Loading state shaped like the page (DESIGN.md §6.9): header, the five totals, the table card. */
function SummarySkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-5 w-32 rounded-full" />
        <Skeleton className="h-4 w-40 rounded-full" />
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-5 w-full max-w-md" />
      </div>
      <div className={TILE_GRID}>
        {TILE_SPAN.map((span, index) => (
          <Skeleton key={index} className={cn('h-36 rounded-2xl', span)} />
        ))}
      </div>
      <Skeleton className="h-80 rounded-2xl" />
      <span className="sr-only">Loading the summary…</span>
    </div>
  )
}
