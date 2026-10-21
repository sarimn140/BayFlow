'use client'

import { CarFront, CircleCheckBig, Clock, Store, Wrench } from 'lucide-react'
import Link from 'next/link'

import { StatCard } from '@/components/layout/stat-card'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { shopDateKey } from '@/lib/format'
import {
  getBookings,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  getServices,
  getShopById,
  getTeamMembers,
} from '@/lib/mock-data'

import { AttentionCard } from './attention-card'
import { BookingsCard } from './bookings-card'
import { InventoryCard } from './inventory-card'
import { OverviewHero } from './overview-hero'
import { OverviewSkeleton } from './overview-skeleton'
import {
  attentionQueue,
  countByPhase,
  greetingAt,
  inventoryHealth,
  longDate,
  openJobs,
  overviewKpis,
  overviewSummary,
  plural,
  recentlyUpdated,
  safeTimeZone,
  scheduledOn,
  setupState,
  sortTeam,
} from './overview-data'
import { SetupChecklist } from './setup-checklist'
import { StatusBreakdownCard } from './status-breakdown-card'
import { TeamCard } from './team-card'

/** D20: an unknown shop reads as "not found", never as someone else's data. */
function ShopNotFound() {
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

export interface ShopOverviewProps {
  shopId: string
  /** `?welcome=1` after S-03: the setup checklist shows even when every step is done. */
  isWelcome: boolean
}

/**
 * O-01 Shop overview (spec 10), the Owner's home: greeting, setup checklist, KPI tiles, what
 * needs attention, bookings (recent and today), bookings by status, team and inventory health.
 * Renders this browser's stored data only (a skeleton until then), so nothing flashes.
 */
export function ShopOverview({ shopId, isWelcome }: ShopOverviewProps) {
  const storeReady = useMockStoreReady()
  const nowIso = useNowMinute()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const bookings = useMockStore(() => getBookings(shopId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const inventory = useMockStore(() => getInventory(shopId))
  const services = useMockStore(() => getServices(shopId))
  const purchaseOrders = useMockStore(() => getPurchaseOrders(shopId))

  if (!storeReady || nowIso === null) return <OverviewSkeleton />
  if (!shop) return <ShopNotFound />

  const base = `/pos/shops/${encodeURIComponent(shopId)}`
  const timeZone = safeTimeZone(shop.timezone)
  const now = new Date(nowIso)
  const todayKey = shopDateKey(now, timeZone)

  const kpis = overviewKpis(bookings, todayKey, timeZone)
  const health = inventoryHealth(inventory, purchaseOrders)
  const setup = setupState(shop, services, team, inventory)
  const showChecklist =
    isWelcome || !(setup.hasServices && setup.hasTeam && setup.hasParts && setup.isListed)
  const members = sortTeam(team).map((member) => ({
    ...member,
    openJobs: openJobs(member.id, bookings),
  }))
  const firstName = (user.name ?? '').trim().split(/\s+/)[0] || 'there'

  return (
    <div className="@container/overview space-y-6">
      <OverviewHero
        shop={shop}
        greeting={greetingAt(nowIso, timeZone)}
        firstName={firstName}
        dateLabel={longDate(nowIso, timeZone)}
        summary={overviewSummary(kpis, bookings.length)}
        base={base}
      />

      {showChecklist ? (
        <SetupChecklist
          shopName={shop.name}
          setup={setup}
          activeServices={services.filter((s) => s.is_active).length}
          staffCount={team.filter((m) => m.role !== 'OWNER' && m.is_active).length}
          partsCount={inventory.length}
          base={base}
        />
      ) : null}

      <div>
        <h2 className="sr-only">Today at a glance</h2>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 @4xl/overview:grid-cols-4">
          <StatCard
            label="Needs action"
            value={kpis.needsSaAction}
            icon={Clock}
            tone={kpis.needsSaAction > 0 ? 'warning' : 'default'}
            hint="Intake, estimates and pick-up calls"
            href={`${base}/bookings?filter=needs_action`}
          />
          <StatCard
            label="In progress"
            value={kpis.inProgress}
            icon={Wrench}
            tone="brand"
            hint="With technicians, parts or QC"
            href={`${base}/jobs`}
          />
          <StatCard
            label="Ready for pick-up"
            value={kpis.readyForPickup}
            icon={CarFront}
            tone="success"
            hint="Passed QC, waiting for the customer"
            href={`${base}/bookings?filter=ready`}
          />
          <StatCard
            label="Completed today"
            value={kpis.completedToday}
            icon={CircleCheckBig}
            hint={`${plural(kpis.completedTotal, 'booking')} completed in total`}
            href={`${base}/bookings?filter=completed`}
          />
        </div>
      </div>

      <div className="grid gap-6 @4xl/overview:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <div className="min-w-0 space-y-6">
          <AttentionCard
            queue={attentionQueue(bookings)}
            restock={health.restock}
            lowCount={health.lowCount}
            now={now}
            base={base}
          />
          <BookingsCard
            recent={recentlyUpdated(bookings)}
            today={scheduledOn(bookings, todayKey)}
            total={bookings.length}
            active={kpis.needsSaAction + kpis.inProgress}
            now={now}
            base={base}
          />
        </div>
        <div className="grid min-w-0 content-start items-start gap-6 @2xl/overview:grid-cols-2 @4xl/overview:grid-cols-1">
          <TeamCard members={members} base={base} />
          <InventoryCard health={health} base={base} />
        </div>
      </div>

      <StatusBreakdownCard phases={countByPhase(bookings)} base={base} />
    </div>
  )
}
