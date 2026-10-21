'use client'

import {
  CalendarCheck,
  ChevronRight,
  ClipboardCheck,
  LayoutDashboard,
  PackageSearch,
  Wrench,
} from 'lucide-react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { PageHeader } from '@/components/layout/page-header'
import { OverviewSkeleton } from '@/components/pos/overview/overview-skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { getCurrentUser } from '@/lib/mock-data'

const ROLE_HOMES = [
  {
    role: 'Owner',
    segment: 'overview',
    label: 'Shop overview',
    description: 'Bookings, team and stock at a glance',
    icon: LayoutDashboard,
  },
  {
    role: 'Service Advisor',
    segment: 'bookings',
    label: 'Bookings',
    description: 'Confirm intakes, assign work, send estimates',
    icon: CalendarCheck,
  },
  {
    role: 'Technician',
    segment: 'jobs',
    label: 'Assigned jobs',
    description: 'Inspect, estimate and repair',
    icon: Wrench,
  },
  {
    role: 'Parts Person',
    segment: 'parts',
    label: 'Parts queue',
    description: 'Reserve, order and hand out parts',
    icon: PackageSearch,
  },
  {
    role: 'QC Inspector',
    segment: 'qc',
    label: 'QC queue',
    description: 'Check repairs before hand-over',
    icon: ClipboardCheck,
  },
]

/**
 * S-04 Role home `/pos/shops/:shopId` (spec 10): sends each member to their role's home — Owner
 * → overview, Service Advisor → bookings, Technician → jobs, Parts Person → parts, QC Inspector
 * → qc (any other role → overview, where the section gate answers). A page-shaped skeleton shows
 * while it does; the list of workspaces only appears when the session carries no role.
 */
export default function ShopHomePage() {
  const router = useRouter()
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const user = useMockStore(() => getCurrentUser())
  const storeReady = useMockStoreReady()

  useEffect(() => {
    if (storeReady && user?.role) {
      let target = 'overview'
      if (user.role === 'SERVICE_ADVISOR') target = 'bookings'
      else if (user.role === 'TECHNICIAN') target = 'jobs'
      else if (user.role === 'PARTS_PERSON') target = 'parts'
      else if (user.role === 'QC_INSPECTOR') target = 'qc'

      router.replace(`/pos/shops/${shopId}/${target}`)
    }
  }, [storeReady, user, shopId, router])

  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  if (!storeReady || user?.role) {
    return (
      <>
        <h1 className="sr-only">Opening your workspace</h1>
        <OverviewSkeleton label="Opening your workspace…" />
      </>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Choose a workspace" description="Open the part of the shop you work in." />
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {ROLE_HOMES.map((home) => (
          <li key={home.segment}>
            <Link
              href={`${base}/${home.segment}`}
              className="group flex h-full items-center gap-4 rounded-2xl border border-border bg-card p-5 shadow-xs transition-[border-color,box-shadow] duration-150 outline-none hover:border-brand-blue/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
            >
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
                <home.icon className="size-5" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="text-sm text-muted-foreground">{home.role}</p>
                <h2 className="text-base font-semibold text-foreground">{home.label}</h2>
                <p className="text-sm text-muted-foreground">{home.description}</p>
              </div>
              <ChevronRight
                className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
