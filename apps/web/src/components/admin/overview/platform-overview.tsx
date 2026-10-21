'use client'

import { CalendarCheck, ShieldAlert, Store, Timer, Users } from 'lucide-react'
import { useMemo } from 'react'

import { useAdminActor } from '@/components/admin/admin-shell'
import { StatCard } from '@/components/layout/stat-card'
import { useMockStore } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { getAdminShops, getAdminUsers, getAuditEvents } from '@/lib/mock-admin'
import { getBookings } from '@/lib/mock-data'

import { ActivityChartCard } from './activity-chart-card'
import { BusiestShopsCard } from './busiest-shops-card'
import { OpenPhasesCard } from './open-phases-card'
import {
  dailyActivity,
  firstName,
  greetingAt,
  longDate,
  overviewSummary,
  platformStats,
  plural,
} from './overview-data'
import { OverviewHero } from './overview-hero'
import { OverviewSkeleton } from './overview-skeleton'
import { RecentActivityCard } from './recent-activity-card'
import { SuspendedShopsCard } from './suspended-shops-card'

/**
 * A-01 Platform overview (spec 19 §5; E-61 once wired): the admin's greeting, the platform KPIs,
 * suspended shops needing attention, bookings per day, open bookings by phase, the busiest shops
 * and the latest audit events.
 */
export function PlatformOverview() {
  const { user } = useAdminActor()
  const users = useMockStore(getAdminUsers)
  const tenants = useMockStore(getAdminShops)
  const bookings = useMockStore(getBookings)
  const audit = useMockStore(getAuditEvents)
  const nowIso = useNowMinute()

  const overview = useMemo(() => {
    if (!nowIso) return null
    const now = new Date(nowIso)
    return {
      stats: platformStats({ users, tenants, bookings, audit, now }),
      days: dailyActivity(bookings, audit, now),
    }
  }, [users, tenants, bookings, audit, nowIso])

  if (!nowIso || !overview) return <OverviewSkeleton />
  const { stats, days } = overview

  return (
    <div className="@container/admin space-y-6">
      <OverviewHero
        greeting={greetingAt(nowIso)}
        firstName={firstName(user.name)}
        dateLabel={longDate(nowIso)}
        summary={overviewSummary(stats)}
      />

      <section aria-labelledby="platform-kpis">
        <h2 id="platform-kpis" className="sr-only">
          Platform at a glance
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 @2xl/admin:grid-cols-6 @5xl/admin:grid-cols-5">
          <StatCard
            className="@2xl/admin:col-span-2 @5xl/admin:col-span-1"
            label="Shops"
            value={stats.shops}
            icon={Store}
            tone="brand"
            hint={`${stats.activeShops} active · ${stats.suspended.length} suspended`}
            href="/admin/shops"
          />
          <StatCard
            className="@2xl/admin:col-span-2 @5xl/admin:col-span-1"
            label="Accounts"
            value={stats.accounts}
            icon={Users}
            tone="brand"
            hint={`${plural(stats.customers, 'customer')} · ${stats.staff} staff · ${plural(stats.admins, 'admin')}`}
            href="/admin/users"
          />
          <StatCard
            className="@2xl/admin:col-span-2 @5xl/admin:col-span-1"
            label="Bookings today"
            value={stats.bookingsToday}
            icon={CalendarCheck}
            tone="brand"
            hint="Today's slots, not cancelled"
          />
          <StatCard
            className="@2xl/admin:col-span-3 @5xl/admin:col-span-1"
            label="Open bookings"
            value={stats.open}
            icon={Timer}
            tone="brand"
            hint="Not completed or cancelled"
          />
          <StatCard
            className="col-span-2 @2xl/admin:col-span-3 @5xl/admin:col-span-1"
            label="Failed sign-ins"
            value={stats.failedSignIns}
            icon={ShieldAlert}
            tone={stats.failedSignIns > 0 ? 'danger' : 'success'}
            hint="Last 24 hours"
          />
        </div>
      </section>

      {stats.suspended.length > 0 ? <SuspendedShopsCard shops={stats.suspended} /> : null}

      <div className="grid gap-6 @4xl/admin:grid-cols-3">
        <ActivityChartCard days={days} className="min-w-0 @4xl/admin:col-span-2" />
        <OpenPhasesCard phases={stats.openByPhase} open={stats.open} className="min-w-0" />
      </div>

      <div className="grid items-start gap-6 @4xl/admin:grid-cols-3">
        <BusiestShopsCard shops={stats.busiest} className="min-w-0" />
        <RecentActivityCard events={audit.slice(0, 8)} className="min-w-0 @4xl/admin:col-span-2" />
      </div>
    </div>
  )
}
