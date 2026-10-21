import type { Metadata } from 'next'

import { CreateShopForm } from '@/components/pos/hub/create-shop-form'
import { HubMain } from '@/components/pos/hub/hub-main'

export const metadata: Metadata = { title: 'Create a shop' }

/**
 * S-03 Create shop / first-run onboarding and O-05 Create an additional shop (spec 10). The new
 * shop's overview opens with `?welcome=1` (the setup checklist, UX rule R12).
 */
export default function CreateShopPage() {
  return (
    <HubMain>
      <CreateShopForm />
    </HubMain>
  )
}
