'use client'

import { Car, Clock, MapPin, MessageSquareText, Phone, Wrench, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { useNowMinute } from '@/hooks/use-now'
import type { MockBooking, MockShop } from '@/lib/mock-data'

import { telHref, todaysHours } from './format'

/** One fact with an icon tile, as in the booking flow's summary ("Your booking"). */
function DetailRow({
  icon: Icon,
  label,
  children,
}: {
  icon: LucideIcon
  label: string
  children: ReactNode
}) {
  return (
    <div className="flex gap-3 py-3.5 first:pt-0 last:pb-0">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-muted-foreground">{label}</p>
        <div className="mt-0.5 text-sm text-foreground">{children}</div>
      </div>
    </div>
  )
}

const KM = new Intl.NumberFormat('en-PK')

/** C-02 "Vehicle and services": the car, what was booked and the customer's own notes. */
export function VehicleCard({
  booking,
}: {
  booking: Pick<
    MockBooking,
    | 'vehicleYear'
    | 'vehicleMake'
    | 'vehicleModel'
    | 'licensePlate'
    | 'vehicleColor'
    | 'mileageKm'
    | 'services'
    | 'customerNotes'
  >
}) {
  const extras = [
    booking.vehicleColor,
    booking.mileageKm ? `${KM.format(booking.mileageKm)} km` : undefined,
  ].filter(Boolean)
  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg leading-7 font-semibold text-foreground">Vehicle and services</h2>
      </CardHeader>
      <CardContent className="gap-0 divide-y divide-border-faint">
        <DetailRow icon={Car} label="Vehicle">
          <p className="font-semibold">
            {booking.vehicleYear} {booking.vehicleMake} {booking.vehicleModel}
          </p>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground">
            <span className="rounded-md border border-border bg-secondary px-2 py-0.5 font-mono text-sm font-semibold text-foreground">
              {booking.licensePlate}
            </span>
            {extras.length > 0 ? <span>{extras.join(' · ')}</span> : null}
          </p>
        </DetailRow>
        <DetailRow icon={Wrench} label="Services booked">
          {booking.services.length > 0 ? (
            <ul className="space-y-1">
              {booking.services.map((service) => (
                <li key={service} className="font-medium">
                  {service}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No services listed</p>
          )}
        </DetailRow>
        {booking.customerNotes ? (
          <DetailRow icon={MessageSquareText} label="Your notes">
            <p className="whitespace-pre-line">{booking.customerNotes}</p>
          </DetailRow>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** C-02 "Shop": where the car is, how to call, and today's opening hours (shop time). */
export function ShopCard({ shop, shopName }: { shop: MockShop | undefined; shopName: string }) {
  const now = useNowMinute()
  const hours = shop && now ? todaysHours(shop, now) : null
  return (
    <Card>
      <CardHeader>
        <h2 className="text-lg leading-7 font-semibold text-foreground">
          {shop?.name ?? shopName}
        </h2>
        <CardDescription>Your workshop for this booking</CardDescription>
      </CardHeader>
      {shop ? (
        <CardContent className="gap-0 divide-y divide-border-faint">
          <DetailRow icon={MapPin} label="Address">
            <p>
              {shop.address}, {shop.city}
            </p>
          </DetailRow>
          <DetailRow icon={Phone} label="Phone">
            <a
              href={telHref(shop.phone)}
              className="-my-2.5 inline-flex min-h-10 items-center rounded-md font-semibold whitespace-nowrap text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
            >
              {shop.phone}
            </a>
          </DetailRow>
          {hours ? (
            <DetailRow icon={Clock} label="Opening hours">
              <p className={hours.closed ? 'font-medium text-danger-ink' : 'font-medium'}>
                {hours.label}
              </p>
            </DetailRow>
          ) : null}
        </CardContent>
      ) : null}
    </Card>
  )
}
