import type { Metadata } from 'next'
import { Suspense } from 'react'

import { BookingWizard, WizardSkeleton } from '@/components/booking/booking-wizard'
import { INITIAL_SHOPS } from '@/lib/mock-data'

type Props = { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params
  const shop = INITIAL_SHOPS.find((candidate) => candidate.slug === slug)
  return { title: shop ? `Book at ${shop.name}` : 'Book a service' }
}

/**
 * `/book/<slug>?step=&service=`: wizard steps 2–5 (spec 10 P-03, D68). The server page awaits
 * `params`; the client wizard reads `step` and `service` from the URL inside `<Suspense>`.
 */
export default async function BookingWizardPage({ params }: Props) {
  const { slug } = await params
  return (
    <Suspense fallback={<WizardSkeleton />}>
      <BookingWizard slug={slug} />
    </Suspense>
  )
}
