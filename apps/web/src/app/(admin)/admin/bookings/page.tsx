import type { Metadata } from 'next'

import { BookingsDirectory } from '@/components/admin/bookings/bookings-directory'

export const metadata: Metadata = { title: { absolute: 'Bookings · Platform admin · BayFlow' } }

/** A-06 Bookings across every shop (spec 19 §5; E-72 once wired). Read-only. */
export default function AdminBookingsPage() {
  return <BookingsDirectory />
}
