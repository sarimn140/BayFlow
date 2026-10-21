import type { Metadata } from 'next'

import { MyBookings } from '@/components/customer/bookings-list/my-bookings'

export const metadata: Metadata = { title: 'My bookings' }

/** C-01 My bookings (spec 10): the signed-in customer's bookings, Active and Past. */
export default function CustomerBookingsPage() {
  return <MyBookings />
}
