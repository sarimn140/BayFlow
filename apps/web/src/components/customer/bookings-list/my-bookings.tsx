'use client'

import { CalendarPlus, CircleAlert, History, Plus } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { getShopSuspensions } from '@/lib/mock-admin'
import { getCurrentUser, getCustomerBookings, getShops } from '@/lib/mock-data'

import { BookingCard } from './booking-card'
import {
  compareActive,
  comparePast,
  joinNames,
  suspendedShopNames,
  toListItems,
  type BookingListItem,
} from './bookings-list-data'

type BookingsTab = 'active' | 'past'

function BookingList({ items, label }: { items: BookingListItem[]; label: string }) {
  return (
    <ul aria-label={label} className="space-y-4">
      {items.map((item) => (
        <li key={item.booking.id}>
          <BookingCard item={item} />
        </li>
      ))}
    </ul>
  )
}

/** Loading (DESIGN.md §6.9): shaped like the tabs and the first cards. */
function BookingsListSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true">
      <Skeleton className="h-10.5 w-44 rounded-full" />
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-64 rounded-2xl" />
        ))}
      </div>
      <span className="sr-only">Loading your bookings…</span>
    </div>
  )
}

/**
 * C-01 My bookings (spec 10): the signed-in person's own bookings (D21: E-11 returns only the
 * caller's; staff see only bookings they made as customers), in two tabs, Active and Past.
 * Bookings that wait on the customer come first, each with its action-needed callout; decisions
 * are taken on the booking itself (C-02).
 */
export function MyBookings() {
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const allBookings = useMockStore(() => getCustomerBookings(user.email))
  const shops = useMockStore(getShops)
  const suspensions = useMockStore(getShopSuspensions)
  const now = useNowMinute()
  const [activeTab, setActiveTab] = useState<BookingsTab>('active')

  const activeBookings = allBookings.filter(
    (b) => b.status !== 'COMPLETED' && b.status !== 'CANCELLED',
  )
  const pastBookings = allBookings.filter(
    (b) => b.status === 'COMPLETED' || b.status === 'CANCELLED',
  )

  const context = { shops, suspensions, nowIso: now }
  const activeItems = toListItems(activeBookings, context).sort(compareActive)
  const pastItems = toListItems(pastBookings, context).sort(comparePast)
  const noBookingsYet = activeItems.length === 0 && pastItems.length === 0
  const suspendedShops = suspendedShopNames(activeItems)

  return (
    <div className="space-y-6">
      <PageHeader
        title="My bookings"
        description={
          <>
            Follow every repair, approve estimates and see when your car is ready.
            <span className="mt-1 block text-sm text-helper">Times are shop local time.</span>
          </>
        }
        actions={
          <Button asChild>
            <Link href="/book">
              <Plus aria-hidden="true" />
              Book a service
            </Link>
          </Button>
        }
      />

      {/* D96: a suspended shop's bookings can only be read and cancelled (as on C-02). */}
      {ready && suspendedShops.length > 0 ? (
        <Alert variant="warning">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>
            {joinNames(suspendedShops)} {suspendedShops.length === 1 ? 'is' : 'are'} temporarily
            unavailable on BayFlow
          </AlertTitle>
          <AlertDescription>
            For now you can&apos;t approve or decline an estimate or confirm a pick-up for your
            bookings there. You can still cancel a booking until its repair starts.
          </AlertDescription>
        </Alert>
      ) : null}

      {ready ? (
        <Tabs
          value={activeTab}
          onValueChange={(value) => setActiveTab(value === 'past' ? 'past' : 'active')}
          className="gap-5"
        >
          <TabsList aria-label="Bookings">
            <TabsTrigger value="active">
              Active
              <Badge variant="outline" className="tabular-nums">
                {activeItems.length}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="past">
              Past
              <Badge variant="outline" className="tabular-nums">
                {pastItems.length}
              </Badge>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="active">
            {activeItems.length === 0 ? (
              <EmptyState
                icon={CalendarPlus}
                title={noBookingsYet ? 'No bookings yet' : 'No active bookings'}
                description={
                  noBookingsYet
                    ? 'Book a service and follow every step here, from inspection to pick-up.'
                    : 'Nothing is in progress right now. Your earlier bookings are under Past.'
                }
                action={
                  <Button asChild variant="outline">
                    <Link href="/book">Find a shop</Link>
                  </Button>
                }
              />
            ) : (
              <BookingList items={activeItems} label="Active bookings" />
            )}
          </TabsContent>

          <TabsContent value="past">
            {pastItems.length === 0 ? (
              <EmptyState
                tone="neutral"
                icon={History}
                title="No past bookings yet"
                description="Completed and cancelled bookings appear here."
              />
            ) : (
              <BookingList items={pastItems} label="Past bookings" />
            )}
          </TabsContent>
        </Tabs>
      ) : (
        <BookingsListSkeleton />
      )}
    </div>
  )
}
