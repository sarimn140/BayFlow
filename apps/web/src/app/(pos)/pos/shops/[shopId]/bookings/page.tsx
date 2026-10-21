'use client'

import { Plus } from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { Suspense } from 'react'

import { PageHeader } from '@/components/layout/page-header'
import { BookingsQueue } from '@/components/pos/sa-bookings/bookings-queue'
import { QueueSkeleton } from '@/components/pos/sa-bookings/queue-skeleton'
import { Button } from '@/components/ui/button'
import { useMockStore } from '@/hooks/use-mock-store'
import { getShopById } from '@/lib/mock-data'

/** SA-01 · Bookings list (spec 10): the Service Advisor's queue; the Owner sees it too (D16). */
export default function ServiceAdvisorBookingsPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const shop = useMockStore(() => getShopById(shopId))

  // A walk-in goes straight to this shop's booking form.
  const walkInHref = shop ? `/book/${encodeURIComponent(shop.slug)}` : '/book'

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Service advisor"
        title="Bookings"
        description="Confirm new bookings, assign technicians, send estimates and hand finished cars back."
        actions={
          <Button asChild>
            <Link href={walkInHref}>
              <Plus aria-hidden="true" />
              New walk-in booking
            </Link>
          </Button>
        }
      />
      {/* The queue reads its filters from the URL (spec 09 §4.7). */}
      <Suspense fallback={<QueueSkeleton />}>
        <BookingsQueue shopId={shopId} walkInHref={walkInHref} />
      </Suspense>
    </div>
  )
}
