import type { Metadata } from 'next'

import { BookingDetail } from '@/components/admin/bookings/booking-detail'

export const metadata: Metadata = {
  title: { absolute: 'Booking details · Platform admin · BayFlow' },
}

/** A-07 Booking detail, read-only (spec 19 §5; E-73 once wired). */
export default async function AdminBookingPage({
  params,
}: PageProps<'/admin/bookings/[bookingId]'>) {
  const { bookingId } = await params
  return <BookingDetail bookingId={bookingId} />
}
