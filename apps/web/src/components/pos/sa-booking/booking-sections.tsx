'use client'

import { MessageSquareText } from 'lucide-react'
import { useState } from 'react'

import { serviceIcon } from '@/components/booking/service-icon'
import { Timeline } from '@/components/layout/timeline'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { formatPKR } from '@/lib/format'
import type { MockBooking, MockService } from '@/lib/mock-data'

import type { ActivityEntry } from './activity'
import { CardHeading } from './detail-bits'
import { dateTimeText, slotText } from './next-step'

/** The concern (DESIGN.md §5 DetailLayout): the services booked and the customer's own words. */
export function RequestCard({
  booking,
  services,
  timeZone,
}: {
  booking: MockBooking
  /** The shop's catalogue, for each booked service's starting price. */
  services: ReadonlyArray<MockService>
  timeZone: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>Customer&apos;s request</CardHeading>
        <CardDescription>
          For {slotText(booking, ' at ')} · booked{' '}
          {dateTimeText(booking.createdAt, timeZone, ' at ')}
        </CardDescription>
      </CardHeader>
      <CardContent className="gap-4">
        <ul className="-my-2 divide-y divide-border-faint">
          {booking.services.map((name, index) => {
            const Icon = serviceIcon(name)
            const service = services.find((candidate) => candidate.name === name)
            return (
              <li key={`${name}-${index}`} className="flex items-center gap-3 py-2.5">
                <span
                  aria-hidden="true"
                  className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink"
                >
                  <Icon className="size-[18px]" />
                </span>
                <p className="min-w-0 flex-1 text-sm font-medium text-foreground">{name}</p>
                {service ? (
                  <p className="shrink-0 text-sm text-muted-foreground tabular-nums">
                    {service.base_price !== null
                      ? `from ${formatPKR(service.base_price)}`
                      : 'Priced after inspection'}
                  </p>
                ) : null}
              </li>
            )
          })}
        </ul>
        {booking.customerNotes ? (
          <figure className="rounded-xl bg-layer px-4 py-3">
            <figcaption className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <MessageSquareText className="size-4 text-muted-foreground" aria-hidden="true" />
              In {booking.customerName}&apos;s words
            </figcaption>
            <blockquote className="mt-1 text-sm whitespace-pre-line text-muted-foreground">
              {booking.customerNotes}
            </blockquote>
          </figure>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** The QC result (spec 10 SA-02 "QC panel"), once an inspector has checked the repair. */
export function QualityCheckCard({
  passed,
  notes,
  inspector,
}: {
  passed?: boolean
  notes?: string
  inspector?: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>Quality check</CardHeading>
        <CardDescription>
          {inspector ? `Checked by ${inspector}` : 'Checked by a QC inspector'}
        </CardDescription>
        {passed !== undefined ? (
          <CardAction>
            <Badge variant={passed ? 'success' : 'destructive'}>
              {passed ? 'Passed' : 'Failed'}
            </Badge>
          </CardAction>
        ) : null}
      </CardHeader>
      {notes ? (
        <CardContent>
          <p className="text-sm text-muted-foreground">{notes}</p>
        </CardContent>
      ) : null}
    </Card>
  )
}

/** Staff see the newest 8 events, then "Show all" (spec 09 §4.4). */
const VISIBLE_EVENTS = 8

export function ActivityCard({
  entries,
  timeZone,
}: {
  entries: ReadonlyArray<ActivityEntry>
  timeZone: string
}) {
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? entries : entries.slice(0, VISIBLE_EVENTS)
  const hidden = entries.length - VISIBLE_EVENTS

  return (
    <Card>
      <CardHeader>
        <CardHeading>Activity</CardHeading>
        <CardDescription>Every step on this booking, newest first</CardDescription>
      </CardHeader>
      <CardContent className="gap-4">
        <Timeline
          aria-label="Booking activity"
          items={visible.map((entry) => ({
            id: entry.id,
            title: entry.title,
            description: (
              <>
                <p>{entry.actor}</p>
                {entry.note ? (
                  <blockquote className="mt-1.5 rounded-lg bg-layer px-3 py-2 text-foreground">
                    {entry.note}
                  </blockquote>
                ) : null}
              </>
            ),
            time: <time dateTime={entry.at}>{dateTimeText(entry.at, timeZone)}</time>,
            icon: entry.icon,
            tone: entry.tone,
          }))}
        />
        {hidden > 0 ? (
          <Button
            type="button"
            variant="ghost"
            className="self-start"
            aria-expanded={showAll}
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? 'Show fewer' : `Show all ${entries.length} events`}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  )
}
