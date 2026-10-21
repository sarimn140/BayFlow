import type { Metadata } from 'next'

import { HubMain } from '@/components/pos/hub/hub-main'
import { PosHub } from '@/components/pos/hub/pos-hub'

export const metadata: Metadata = { title: 'Your shops' }

/**
 * S-02 POS hub (spec 10): redirects a member with a current shop to their role's home; otherwise
 * lists their shops, or welcomes someone without one to create their first shop.
 */
export default function PosHubPage() {
  return (
    <HubMain>
      <PosHub />
    </HubMain>
  )
}
