import type { Metadata } from 'next'

import { ShopSettings } from '@/components/pos/settings/shop-settings'

export const metadata: Metadata = { title: 'Shop settings' }

/**
 * O-04 Shop settings (spec 10): profile, directory listing, slots and capacity, opening hours.
 * Owner only (`shop.manage`); the shop layout's section gate enforces it.
 */
export default async function ShopSettingsPage({
  params,
}: PageProps<'/pos/shops/[shopId]/settings'>) {
  const { shopId } = await params

  return <ShopSettings shopId={shopId} />
}
