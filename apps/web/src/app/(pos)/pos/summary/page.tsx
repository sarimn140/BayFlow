import type { Metadata } from 'next'

import { HubMain } from '@/components/pos/hub/hub-main'
import { ShopsSummary } from '@/components/pos/hub/shops-summary'

export const metadata: Metadata = { title: 'All shops summary' }

/** O-07 Multi-shop summary (spec 10, P1): one row per owned shop, linking to its overview. */
export default function ShopsSummaryPage() {
  return (
    <HubMain>
      <ShopsSummary />
    </HubMain>
  )
}
