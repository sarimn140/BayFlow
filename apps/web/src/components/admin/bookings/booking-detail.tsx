'use client'

import { Eye } from 'lucide-react'
import { useEffect, useMemo } from 'react'

import { useAdminActor } from '@/components/admin/admin-shell'
import {
  BookingDetailsCard,
  BookingTimelineCard,
  EstimateCard,
  ShopNotesCard,
  VehicleCard,
} from '@/components/admin/bookings/booking-cards'
import { slotLabel, vehicleLabel } from '@/components/admin/bookings/slot'
import { NotFoundPanel } from '@/components/admin/not-found-panel'
import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useMockStore } from '@/hooks/use-mock-store'
import { DEFAULT_SHOP_TZ } from '@/lib/format'
import { getAdminUsers, recordAdminView } from '@/lib/mock-admin'
import { bookingHistory } from '@/lib/mock-booking-history'
import { getBookings, getShops } from '@/lib/mock-data'

/** A-07 Booking detail, read-only (spec 19 §5; E-73 once wired). */
export function BookingDetail({ bookingId }: { bookingId: string }) {
  const { user: me } = useAdminActor()
  const bookings = useMockStore(getBookings)
  const users = useMockStore(getAdminUsers)
  const shops = useMockStore(getShops)
  const booking = bookings.find((b) => b.id === bookingId)
  const actor = useMemo(() => ({ name: me.name, email: me.email }), [me.name, me.email])

  // E-73 records that an admin opened this booking (D95).
  const reference = booking?.reference
  const shopId = booking?.shopId
  const shopName = booking?.shopName
  const shopSlug = booking?.shopSlug
  useEffect(() => {
    if (!bookingId || !reference || !shopId || !shopName || !shopSlug) return
    recordAdminView(
      'booking',
      { id: bookingId, label: reference, shop: { id: shopId, name: shopName, slug: shopSlug } },
      actor,
    )
  }, [bookingId, reference, shopId, shopName, shopSlug, actor])

  if (!booking) return <NotFoundPanel backHref="/admin/bookings" backLabel="All bookings" />

  const customer = users.find((u) => u.email === booking.customerEmail.toLowerCase())
  const shop = shops.find((s) => s.id === booking.shopId)
  const timeZone = shop?.timezone ?? DEFAULT_SHOP_TZ
  const timeline = [...bookingHistory(booking)].reverse()

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: '/admin/bookings', label: 'All bookings' }}
        eyebrow={`Booking at ${booking.shopName}`}
        title={<span className="font-mono">{booking.reference}</span>}
        badges={<StatusBadge status={booking.status} audience="staff" size="md" />}
        description={
          <>
            {vehicleLabel(booking)} · <span className="font-mono">{booking.licensePlate}</span> ·{' '}
            {slotLabel(booking)}
          </>
        }
      />

      <Alert variant="info" role="note">
        <Eye aria-hidden="true" />
        <AlertTitle>Read-only view</AlertTitle>
        <AlertDescription>
          The shop&apos;s staff act on this booking from their POS. Opening it here is recorded in
          the audit log.
        </AlertDescription>
      </Alert>

      <DetailLayout
        aside={
          <>
            <BookingDetailsCard
              booking={booking}
              customer={customer}
              shop={shop}
              timeZone={timeZone}
            />
            <VehicleCard booking={booking} />
          </>
        }
      >
        <EstimateCard booking={booking} />
        <ShopNotesCard booking={booking} />
        <BookingTimelineCard steps={timeline} timeZone={timeZone} />
      </DetailLayout>
    </div>
  )
}
