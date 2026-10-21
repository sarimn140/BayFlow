import type { Metadata } from 'next'

import { QcQueue } from '@/components/pos/qc/qc-queue'

export const metadata: Metadata = { title: 'QC queue' }

/**
 * QI-01 QC queue (spec 10), shared by the shop's QC inspectors: pick a repaired car to inspect.
 * The Owner opens it read-only (spec 10 S-01, D16).
 */
export default async function QcQueuePage({ params }: PageProps<'/pos/shops/[shopId]/qc'>) {
  const { shopId } = await params

  return <QcQueue shopId={shopId} />
}
