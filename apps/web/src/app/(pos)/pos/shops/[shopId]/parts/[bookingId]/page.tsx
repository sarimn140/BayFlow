import type { Metadata } from 'next'

import { PartsJob } from '@/components/pos/parts/parts-job'

export const metadata: Metadata = { title: 'Parts job' }

/**
 * PP-02 Parts job detail (spec 10): required parts against stock, then order the missing parts,
 * mark the parts ready or allocate them to the technician. The Owner opens it read-only (D16).
 */
export default async function PartsJobPage({
  params,
}: PageProps<'/pos/shops/[shopId]/parts/[bookingId]'>) {
  const { shopId, bookingId } = await params

  // Keyed by booking, so an outcome notice never carries over to another job.
  return <PartsJob key={bookingId} shopId={shopId} bookingId={bookingId} />
}
