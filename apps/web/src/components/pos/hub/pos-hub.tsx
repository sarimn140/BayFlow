'use client'

import { ChevronRight, LayoutGrid, Plus, Store } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

import { OnboardingSteps } from '@/components/auth/onboarding-steps'
import { Handwritten } from '@/components/booking/booking-hero'
import { ROLE_NAME } from '@/components/layout/account-menu'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { getCurrentUser, getShops, getTeamMembers } from '@/lib/mock-data'

import { ownedShopIds, plural, workspaceHref, workspacesOf, type Workspace } from './hub-data'

/**
 * S-02 POS hub `/pos` (spec 10): a signed-in member with a current shop goes straight to their
 * role's home in it (Owner → overview, Service Advisor → bookings, Technician → jobs, Parts Person
 * → parts, QC Inspector → qc; anyone else → overview, where the section gate answers), behind a
 * skeleton. Without a current shop it lists the shops the person works in, or — when there are
 * none — the first-run welcome that leads to creating a shop (UX rule R12).
 */
export function PosHub() {
  const router = useRouter()
  const user = useMockStore(getCurrentUser)
  const shops = useMockStore(getShops)
  const team = useMockStore(getTeamMembers)
  const storeReady = useMockStoreReady()

  useEffect(() => {
    // If user has an active shop, redirect immediately to their role home
    if (storeReady && user?.shopId) {
      let targetSegment = 'overview'
      if (user.role === 'SERVICE_ADVISOR') targetSegment = 'bookings'
      else if (user.role === 'TECHNICIAN') targetSegment = 'jobs'
      else if (user.role === 'PARTS_PERSON') targetSegment = 'parts'
      else if (user.role === 'QC_INSPECTOR') targetSegment = 'qc'

      router.replace(`/pos/shops/${user.shopId}/${targetSegment}`)
    }
  }, [storeReady, user, router])

  // Until this browser's session is read, and while it redirects, a page-shaped skeleton shows.
  if (!storeReady || user?.shopId) return <HubSkeleton />

  const workspaces = workspacesOf(user.email, team, shops)
  if (workspaces.length === 0) {
    return <FirstRun name={user.name} isCustomer={user.role === 'CUSTOMER'} />
  }

  // O-07 is for owners of two or more shops (the switcher's "All shops summary" rule).
  const canSummarise = user.role === 'OWNER' && ownedShopIds(user.email, team).size >= 2

  return (
    <>
      <PageHeader
        eyebrow="Workshop hub"
        title="Your shops"
        description={`You work in ${plural(workspaces.length, 'shop')}. Open one to get to work, or create another.`}
        actions={
          <>
            {canSummarise ? (
              <Button asChild variant="outline">
                <Link href="/pos/summary">
                  <LayoutGrid data-icon="inline-start" aria-hidden="true" />
                  All shops summary
                </Link>
              </Button>
            ) : null}
            <Button asChild>
              <Link href="/pos/shops/new">
                <Plus data-icon="inline-start" aria-hidden="true" />
                Create shop
              </Link>
            </Button>
          </>
        }
      />

      <ul aria-label="Your shops" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {workspaces.map((workspace) => (
          <li key={workspace.shop.id}>
            <WorkspaceCard workspace={workspace} />
          </li>
        ))}
      </ul>
    </>
  )
}

/** One shop the person works in: opens their role's home there (spec 10 S-04). */
function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const { shop, role } = workspace
  return (
    <Link
      href={workspaceHref(workspace)}
      className="group flex h-full items-center gap-4 rounded-2xl border border-border bg-card p-5 shadow-xs transition-[border-color,box-shadow] duration-150 outline-none hover:border-brand-blue/40 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
    >
      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
        <Store className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <h2 className="truncate text-base font-semibold text-foreground">{shop.name}</h2>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          {shop.address}, {shop.city}
        </p>
        <Badge variant="brand">{ROLE_NAME[role]}</Badge>
      </div>
      <ChevronRight
        className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
        aria-hidden="true"
      />
    </Link>
  )
}

/** No shop yet (UX rule R12): a welcome, the onboarding steps and "Create your first shop". */
function FirstRun({ name, isCustomer }: { name: string; isCustomer: boolean }) {
  const firstName = name.trim().split(/\s+/)[0] || 'there'
  return (
    <section
      aria-labelledby="hub-welcome"
      className="bg-hero rounded-3xl border border-border px-5 py-8 sm:px-8 sm:py-12"
    >
      <div className="max-w-3xl space-y-8">
        <div className="space-y-3">
          <p className="text-sm font-semibold text-brand-blue-ink">Workshop hub</p>
          <h1
            id="hub-welcome"
            className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl lg:text-5xl"
          >
            Welcome, <Handwritten>{firstName}</Handwritten>
          </h1>
          <p className="max-w-2xl text-base text-muted-foreground">
            You’re not part of a shop on BayFlow yet. Create your shop to take bookings online, then
            add your team, services and parts.
          </p>
        </div>
        <div className="max-w-xl">
          <OnboardingSteps current={1} />
        </div>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
          <Button asChild size="lg" className="w-full sm:w-auto">
            <Link href="/pos/shops/new">
              <Plus data-icon="inline-start" aria-hidden="true" />
              Create your first shop
            </Link>
          </Button>
          {isCustomer ? (
            <p className="text-sm text-muted-foreground">
              Looking for your bookings?{' '}
              <Link
                href="/bookings"
                className="rounded-sm font-semibold text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
              >
                Go to My bookings
              </Link>
            </p>
          ) : null}
        </div>
      </div>
    </section>
  )
}

/** While the session is read or the redirect runs: shaped like the shop list (DESIGN.md §6.9). */
function HubSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <h1 className="sr-only">Opening your workspace</h1>
      <div className="space-y-3 pb-2">
        <Skeleton className="h-4 w-28 rounded-full" />
        <Skeleton className="h-10 w-64 max-w-full" />
        <Skeleton className="h-5 w-full max-w-md" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((index) => (
          <Skeleton key={index} className="h-28 rounded-2xl" />
        ))}
      </div>
    </div>
  )
}
