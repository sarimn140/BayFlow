import type { Metadata } from 'next'

import { ShopOverview } from '@/components/pos/overview/shop-overview'

export const metadata: Metadata = { title: 'Shop overview' }

/**
 * O-01 Shop overview (spec 10), the Owner's home. `?welcome=1` (after S-03 creates the shop)
 * keeps the setup checklist on screen (UX rule R12).
 */
export default async function ShopOverviewPage({
  params,
  searchParams,
}: PageProps<'/pos/shops/[shopId]/overview'>) {
  const { shopId } = await params
  const { welcome } = await searchParams
  const welcomeFlag = Array.isArray(welcome) ? welcome[0] : welcome

  return <ShopOverview shopId={shopId} isWelcome={welcomeFlag === '1'} />
}
