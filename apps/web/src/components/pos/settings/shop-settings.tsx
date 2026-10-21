'use client'

import { ExternalLink } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'

import { PageHeader } from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { getBookings, getServices, getShopById, type MockShop } from '@/lib/mock-data'

import { HoursSection } from './hours-section'
import { ListingSection } from './listing-section'
import { ProfileSection } from './profile-section'
import {
  hoursFromShop,
  profileFromShop,
  safeTimeZone,
  sameHours,
  sameProfile,
  sameSlots,
  slotsFromShop,
  upcomingBookingCount,
} from './settings-data'
import { ShopNotFound } from './shop-not-found'
import { SlotsSection } from './slots-section'
import { UnsavedChangesGuard } from './unsaved-changes-guard'

/**
 * O-04 Shop settings (spec 10): shop profile, directory listing, slots and capacity, and opening
 * hours, each saved on its own. Renders this browser's stored shop only (a skeleton until then),
 * so the forms never start from the seed data.
 */
export function ShopSettings({ shopId }: { shopId: string }) {
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const shop = useMockStore(() => getShopById(shopId))
  const services = useMockStore(() => getServices(shop?.id ?? shopId))
  const bookings = useMockStore(() => getBookings(shop?.id ?? shopId))

  if (!ready || nowIso === null) return <SettingsSkeleton />
  if (!shop) return <ShopNotFound />

  const upcoming = upcomingBookingCount(bookings, new Date(nowIso), safeTimeZone(shop.timezone))
  const activeServices = services.filter((s) => s.is_active).length

  return (
    <SettingsForms key={shop.id} shop={shop} upcoming={upcoming} activeServices={activeServices} />
  )
}

function SettingsForms({
  shop,
  upcoming,
  activeServices,
}: {
  shop: MockShop
  upcoming: number
  activeServices: number
}) {
  // Each section's form starts from the stored shop; saving one section never touches another's
  // fields or unsaved edits.
  const [profile, setProfile] = useState(() => profileFromShop(shop))
  const [slots, setSlots] = useState(() => slotsFromShop(shop))
  const [hours, setHours] = useState(() => hoursFromShop(shop))

  const dirty = {
    profile: !sameProfile(profile, profileFromShop(shop)),
    slots: !sameSlots(slots, slotsFromShop(shop)),
    hours: !sameHours(hours, hoursFromShop(shop)),
  }
  const unsaved = [
    dirty.profile ? 'Shop profile' : null,
    dirty.slots ? 'Slots and capacity' : null,
    dirty.hours ? 'Opening hours' : null,
  ].filter((name): name is string => name !== null)

  const base = `/pos/shops/${encodeURIComponent(shop.id)}`
  const publicHref = `/shops/${encodeURIComponent(shop.slug)}`

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={shop.name}
        title="Shop settings"
        description="Your shop's details, directory listing, booking slots and opening hours. Each section saves on its own."
        actions={
          shop.is_listed ? (
            <Button asChild variant="outline">
              <Link href={publicHref} target="_blank" rel="noreferrer">
                View public page
                <ExternalLink data-icon="inline-end" aria-hidden="true" />
                <span className="sr-only"> (opens in a new tab)</span>
              </Link>
            </Button>
          ) : null
        }
      />

      <ProfileSection shop={shop} value={profile} onChange={setProfile} dirty={dirty.profile} />
      <ListingSection
        shop={shop}
        activeServices={activeServices}
        servicesHref={`${base}/services`}
        publicHref={publicHref}
      />
      <SlotsSection
        shop={shop}
        value={slots}
        onChange={setSlots}
        dirty={dirty.slots}
        upcoming={upcoming}
      />
      <HoursSection shop={shop} value={hours} onChange={setHours} dirty={dirty.hours} />

      <UnsavedChangesGuard sections={unsaved} />
    </div>
  )
}

/** Loading state shaped like the page (DESIGN.md §6.9): header, then four settings sections. */
function SettingsSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-4 w-32 rounded-full" />
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-5 w-full max-w-xl" />
      </div>
      {[18, 10, 14, 26].map((height, i) => (
        <div key={i} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-8">
          <div className="space-y-2 lg:pt-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-full max-w-xs" />
          </div>
          <Skeleton className="rounded-2xl" style={{ height: `${height}rem` }} />
        </div>
      ))}
      <span className="sr-only">Loading shop settings…</span>
    </div>
  )
}
