import type { Metadata } from 'next'

import { ServicesCatalogue } from '@/components/pos/catalogue/services-catalogue'

export const metadata: Metadata = { title: 'Services' }

/**
 * O-03 Services catalogue (spec 10): what customers can book, with its duration and base price.
 * Owner only (`services.manage`); the shop layout's section gate enforces it.
 */
export default async function ServicesPage({ params }: PageProps<'/pos/shops/[shopId]/services'>) {
  const { shopId } = await params

  return <ServicesCatalogue shopId={shopId} />
}
