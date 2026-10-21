import type { Metadata } from 'next'

import { QcInspection } from '@/components/pos/qc/qc-inspection'

export const metadata: Metadata = { title: 'QC inspection' }

/**
 * QI-02 Inspection (spec 10): the D46 checklist, then Pass QC (ready for pick-up) or Fail QC (an
 * issue that returns the job to its technician). Read-only for the Owner (D16).
 */
export default async function QcInspectionPage({
  params,
}: PageProps<'/pos/shops/[shopId]/qc/[bookingId]'>) {
  const { shopId, bookingId } = await params

  return <QcInspection shopId={shopId} bookingId={bookingId} />
}
