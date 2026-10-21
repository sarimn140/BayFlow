'use client'

import { useState } from 'react'

import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import {
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import { dayLabel, shortDayLabel, type DayActivity } from './overview-data'

type Series = 'bookings' | 'events'

const SERIES = {
  bookings: {
    title: 'Bookings, last 14 days',
    description: 'New bookings per day across all shops, in Pakistan time.',
    one: 'new booking',
    many: 'new bookings',
  },
  events: {
    title: 'Activity, last 14 days',
    description: 'Audit events per day across BayFlow, in Pakistan time.',
    one: 'audit event',
    many: 'audit events',
  },
} as const satisfies Record<
  Series,
  { title: string; description: string; one: string; many: string }
>

/**
 * A-01 "bookings per day (14 days)" (spec 19 §5), with the audit log's daily activity as a second
 * view. One series at a time in brand blue: every non-zero day carries its value on the cap and the
 * axis names the days, so nothing depends on hover; a hidden table holds both series for screen
 * readers.
 */
export function ActivityChartCard({
  days,
  className,
}: {
  days: ReadonlyArray<DayActivity>
  className?: string
}) {
  const [series, setSeries] = useState<Series>('bookings')
  const meta = SERIES[series]
  const values = days.map((d) => (series === 'bookings' ? d.bookings : d.events))
  const total = values.reduce((sum, value) => sum + value, 0)
  const max = Math.max(0, ...values)
  const peak = max > 0 ? days[values.indexOf(max)] : undefined
  const last = days.length - 1

  return (
    <Card className={className}>
      <CardHeader>
        <CardHeading>{meta.title}</CardHeading>
        <CardDescription>{meta.description}</CardDescription>
      </CardHeader>
      <CardContent className="@container/chart gap-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="text-2xl font-bold tracking-tight text-foreground">{total}</span>
            <span className="text-sm text-muted-foreground">
              {total === 1 ? meta.one : meta.many} in {days.length} days
              {peak ? ` · busiest ${dayLabel(peak.day)} with ${max}` : ''}
            </span>
          </p>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={0}
            value={series}
            onValueChange={(value) => {
              if (value) setSeries(value as Series)
            }}
            aria-label="Chart data"
          >
            <ToggleGroupItem value="bookings">Bookings</ToggleGroupItem>
            <ToggleGroupItem value="events">Activity</ToggleGroupItem>
          </ToggleGroup>
        </div>

        <div aria-hidden="true">
          <div className="relative h-44">
            <div className="absolute inset-x-0 top-6 bottom-0 flex items-end gap-1 border-b border-border @lg/chart:gap-2">
              {days.map((d, index) => {
                const value = values[index] ?? 0
                const height = `${(value / Math.max(1, max)) * 100}%`
                return (
                  <div
                    key={d.day}
                    className="relative flex h-full min-w-0 flex-1 items-end justify-center"
                  >
                    {value > 0 ? (
                      <>
                        <span
                          className="absolute left-1/2 -translate-x-1/2 text-xs font-semibold text-foreground tabular-nums"
                          style={{ bottom: `calc(${height} + 4px)` }}
                        >
                          {value}
                        </span>
                        <span
                          className="block w-full max-w-6 rounded-t-sm bg-brand-blue"
                          style={{ height }}
                        />
                      </>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="mt-2 flex gap-1 @lg/chart:gap-2">
            {days.map((d, index) => (
              <span key={d.day} className="flex min-w-0 flex-1 justify-center">
                <span
                  className={cn(
                    'text-xs whitespace-nowrap text-helper',
                    index % 6 === 1 ? null : index % 2 === 1 ? 'hidden @lg/chart:inline' : 'hidden',
                  )}
                >
                  {index === last ? 'Today' : shortDayLabel(d.day)}
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* The chart's numbers for screen readers. A bare `<table>` in the clipped `sr-only`
            box: the `Table` primitive's horizontal scroll box would be a scroll region that no
            keyboard can reach (axe `scrollable-region-focusable`), and nothing here is seen. */}
        <div className="sr-only">
          <table>
            <TableCaption>
              New bookings and audit events per day, last {days.length} days
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Day</TableHead>
                <TableHead scope="col">New bookings</TableHead>
                <TableHead scope="col">Audit events</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {days.map((d) => (
                <TableRow key={d.day}>
                  <TableHead scope="row">{dayLabel(d.day)}</TableHead>
                  <TableCell>{d.bookings}</TableCell>
                  <TableCell>{d.events}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
