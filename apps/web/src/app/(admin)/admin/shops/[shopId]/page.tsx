import type { Metadata } from 'next'

import { ShopDetail } from '@/components/admin/shops/shop-detail'

export const metadata: Metadata = { title: { absolute: 'Shop details · Platform admin · BayFlow' } }

/** A-03 Shop detail (spec 19 §5; E-63…E-65 once wired). */
export default async function AdminShopPage({ params }: PageProps<'/admin/shops/[shopId]'>) {
  const { shopId } = await params
  return <ShopDetail shopId={shopId} />
}
