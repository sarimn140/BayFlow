import type { Metadata } from 'next'

import { ShopProfile } from '@/components/booking/shop-profile'
import { INITIAL_SHOPS } from '@/lib/mock-data'

export async function generateMetadata({ params }: PageProps<'/shops/[slug]'>): Promise<Metadata> {
  const { slug } = await params
  const shop = INITIAL_SHOPS.find((candidate) => candidate.slug === slug)
  return shop
    ? {
        title: shop.name,
        description: `Services, prices and opening hours at ${shop.name}, ${shop.city}. Book a service online in about two minutes.`,
      }
    : { title: 'Workshop' }
}

/**
 * `/shops/<slug>`: P-02 shop detail (spec 10). The server page awaits `params` and sets the title
 * ("{Shop} · BayFlow"); the client profile reads the shop, its services and hours from the store.
 */
export default async function ShopDetailPage({ params }: PageProps<'/shops/[slug]'>) {
  const { slug } = await params
  return <ShopProfile slug={slug} />
}
