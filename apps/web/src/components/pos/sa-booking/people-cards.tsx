import { Car, Mail, Phone } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { initials } from './detail-bits'

const CONTACT_LINK =
  '-mx-2 flex min-h-10 min-w-0 items-center gap-2.5 rounded-lg px-2 text-sm font-medium text-brand-blue-ink transition-colors hover:bg-brand-blue-subtle/50 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

export interface Assignee {
  role: string
  name?: string
  /** D19: a deactivated member keeps the job but gets a warning chip. */
  inactive?: boolean
}

/** One titled part of the details card; the titles are `<h2>`s, so the outline stays flat. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3 border-border-faint not-first:border-t not-first:pt-5">
      <h2 className="text-sm font-semibold text-muted-foreground">{title}</h2>
      {children}
    </div>
  )
}

/**
 * The side column's reference card (spec 10 SA-02: customer with `tel:` and `mailto:`, vehicle,
 * assignments), in one card so the sticky side column stays short.
 */
export function BookingDetailsCard({
  booking,
  assignees,
}: {
  booking: MockBooking
  assignees: ReadonlyArray<Assignee>
}) {
  const phoneHref = `tel:${booking.customerPhone.replace(/[^\d+]/g, '')}`
  const extras = [
    booking.vehicleColor,
    booking.mileageKm !== undefined ? `${booking.mileageKm.toLocaleString('en-PK')} km` : null,
  ].filter(Boolean)

  return (
    <Card>
      <CardContent className="gap-5">
        <Section title="Customer">
          <div className="space-y-1">
            <div className="flex items-center gap-3 pb-1">
              <span
                aria-hidden="true"
                className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-blue-subtle text-sm font-semibold text-brand-blue-ink"
              >
                {initials(booking.customerName)}
              </span>
              <p className="min-w-0 truncate text-base font-semibold text-foreground">
                {booking.customerName}
              </p>
            </div>
            <a href={phoneHref} className={CONTACT_LINK}>
              <Phone className="size-4 shrink-0" aria-hidden="true" />
              <span className="sr-only">Call </span>
              <span className="tabular-nums">{booking.customerPhone}</span>
            </a>
            <a href={`mailto:${booking.customerEmail}`} className={CONTACT_LINK}>
              <Mail className="size-4 shrink-0" aria-hidden="true" />
              <span className="sr-only">E-mail </span>
              <span className="min-w-0 break-all">{booking.customerEmail}</span>
            </a>
          </div>
        </Section>

        <Section title="Vehicle">
          <div className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-muted-foreground"
            >
              <Car className="size-5" />
            </span>
            <div className="min-w-0 space-y-1.5">
              <p className="text-sm font-semibold text-foreground">
                {booking.vehicleYear} {booking.vehicleMake} {booking.vehicleModel}
              </p>
              <p>
                <span className="sr-only">Registration </span>
                <span className="inline-flex rounded-md border border-border bg-muted px-2 py-0.5 font-mono text-sm font-medium text-foreground">
                  {booking.licensePlate}
                </span>
              </p>
              {extras.length > 0 ? (
                <p className="text-sm text-muted-foreground">{extras.join(' · ')}</p>
              ) : null}
            </div>
          </div>
        </Section>

        <Section title="Team on this job">
          <ul className="-my-2 divide-y divide-border-faint">
            {assignees.map((person) => (
              <li key={person.role} className="flex items-center justify-between gap-3 py-2">
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={cn(
                      'flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
                      person.name
                        ? 'bg-secondary text-muted-foreground'
                        : 'border border-dashed border-border-medium text-helper',
                    )}
                  >
                    {person.name ? initials(person.name) : '–'}
                  </span>
                  <div className="min-w-0">
                    <p
                      className={cn(
                        'truncate text-sm',
                        person.name ? 'font-medium text-foreground' : 'text-helper',
                      )}
                    >
                      {person.name ?? 'Not assigned'}
                    </p>
                    <p className="text-xs text-helper">{person.role}</p>
                  </div>
                </div>
                {person.inactive ? <Badge variant="warning">Inactive</Badge> : null}
              </li>
            ))}
          </ul>
        </Section>
      </CardContent>
    </Card>
  )
}
