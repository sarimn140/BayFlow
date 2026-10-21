import type { Metadata } from 'next'

import { BookingConfirmation } from '@/components/booking/booking-confirmation'

type Props = PageProps<'/book/confirmed/[bookingId]'>

/**
 * The server can't tell whose booking this is (the session lives in the browser), so the title
 * never names the booking: putting a reference in it would tell anyone with the link that the
 * booking exists (D21: someone else's booking reads as not found). The page shows the reference.
 */
export const metadata: Metadata = { title: 'Booking received' }

/**
 * `/book/confirmed/<bookingId>?new_account=1`: C-03, the wizard's success page (spec 10). The
 * server page reads the params; the client view finds the booking in this browser's store, for
 * its own customer only.
 */
export default async function BookingConfirmedPage({ params, searchParams }: Props) {
  const [{ bookingId }, query] = await Promise.all([params, searchParams])
  return <BookingConfirmation bookingId={bookingId} newAccount={query.new_account === '1'} />
}
