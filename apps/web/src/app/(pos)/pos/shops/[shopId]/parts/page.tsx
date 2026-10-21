import type { Metadata } from 'next'

import { PartsQueue } from '@/components/pos/parts/parts-queue'

export const metadata: Metadata = { title: 'Parts queue' }

/**
 * PP-01 Jobs awaiting parts (spec 10): the Parts Person's queue — to check against stock, on order
 * from a supplier, ready to allocate. The Owner opens it read-only (D16).
 */
export default async function PartsQueuePage({ params }: PageProps<'/pos/shops/[shopId]/parts'>) {
  const { shopId } = await params

  return <PartsQueue shopId={shopId} />
}
