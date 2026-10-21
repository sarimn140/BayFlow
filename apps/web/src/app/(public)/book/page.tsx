import { BadgeCheck, CalendarCheck, Smartphone } from 'lucide-react'
import type { Metadata } from 'next'

import { BookingHero, Eyebrow, Handwritten } from '@/components/booking/booking-hero'
import { BookingSteps } from '@/components/booking/booking-steps'
import { ShopDirectory } from '@/components/booking/shop-directory'

export const metadata: Metadata = { title: 'Book a service' }

const PROMISES = [
  { icon: CalendarCheck, text: 'Only free times are shown' },
  { icon: BadgeCheck, text: 'No work until you approve the estimate' },
  { icon: Smartphone, text: 'Follow every step from your phone' },
]

/** `/book`: wizard step 1, choose a workshop (spec 10 P-03 W1). */
export default function BookChooseShopPage() {
  return (
    <div className="marketing bg-background pb-20">
      <BookingHero
        eyebrow={<Eyebrow icon={<CalendarCheck />}>Online booking · about 2 minutes</Eyebrow>}
        title={
          <>
            Book your car in for a <Handwritten>service</Handwritten>
          </>
        }
        description="Pick a workshop, choose what your car needs and a time that suits you. The shop confirms your booking and you approve the price before any work starts."
      >
        <BookingSteps current="shop" />
        <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          {PROMISES.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-center gap-2">
              <Icon className="size-4 text-brand-green" aria-hidden />
              {text}
            </li>
          ))}
        </ul>
      </BookingHero>

      <section aria-labelledby="workshops" className="mx-auto max-w-6xl px-4 pt-10 sm:px-6 lg:px-8">
        <h2 id="workshops" className="sr-only">
          Workshops
        </h2>
        <ShopDirectory />
      </section>
    </div>
  )
}
