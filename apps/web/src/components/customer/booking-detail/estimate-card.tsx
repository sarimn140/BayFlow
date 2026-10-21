import { CarFront, CircleCheck, FileX, PackageCheck, ScanSearch, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardDescription, CardHeader } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { EstimateDecision } from '@/components/customer/estimate-decision'
import { formatDateTime, formatPKR } from '@/lib/format'
import type { MockBooking, MockEstimateItem } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { formatShortDateTime } from './format'

const DECISION_BADGE = {
  pending: { variant: 'warning', label: 'Awaiting approval' },
  approved: { variant: 'success', label: 'Approved' },
  declined: { variant: 'destructive', label: 'Declined' },
} as const satisfies Record<EstimateDecision, { variant: string; label: string }>

/** Table cells line up with the card's own padding (20px on phones, 24px from `sm`). */
const EDGE = 'first:pl-(--card-spacing) last:pr-(--card-spacing)'

const AFTER_APPROVAL = [
  { icon: PackageCheck, title: 'Parts', text: 'The shop gets the parts ready.' },
  {
    icon: Wrench,
    title: 'Repair and check',
    text: 'A technician repairs your car, then an inspector checks the work.',
  },
  {
    icon: CarFront,
    title: 'Pick-up',
    text: "We'll let you know when your car is ready to collect.",
  },
] as const

function sum(lines: ReadonlyArray<MockEstimateItem>): number {
  return lines.reduce((total, line) => total + line.total, 0)
}

/** "1" for parts, "1.5 h" for labour (labour quantities are hours, spec 02 §3.12). */
function quantity(line: MockEstimateItem): string {
  return line.type === 'LABOR' ? `${line.quantity} h` : String(line.quantity)
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

interface LineGroup {
  key: 'parts' | 'labour'
  label: string
  count: string
  lines: ReadonlyArray<MockEstimateItem>
}

/** md and up: one flush table, parts then labour, with the grand total in the footer. */
function LineTable({ groups, total }: { groups: ReadonlyArray<LineGroup>; total: number }) {
  return (
    <Table aria-label="Estimate lines">
      <TableHeader>
        <TableRow>
          <TableHead className={EDGE}>Item</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="text-right">Unit price</TableHead>
          <TableHead className={cn('text-right', EDGE)}>Total</TableHead>
        </TableRow>
      </TableHeader>
      {groups.map((group) => (
        <TableBody key={group.key}>
          <TableRow className="border-0 hover:bg-transparent">
            <TableHead
              scope="rowgroup"
              colSpan={4}
              className={cn('h-auto pt-5 pb-1 font-semibold text-foreground', EDGE)}
            >
              {group.label} <span className="font-normal text-helper">· {group.count}</span>
            </TableHead>
          </TableRow>
          {group.lines.map((line) => (
            <TableRow key={line.id}>
              <TableCell className={cn('font-medium whitespace-normal', EDGE)}>
                {line.description}
              </TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">
                {quantity(line)}
              </TableCell>
              <TableCell className="text-right text-muted-foreground tabular-nums">
                {formatPKR(line.unit_price)}
              </TableCell>
              <TableCell className={cn('text-right font-semibold tabular-nums', EDGE)}>
                {formatPKR(line.total)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      ))}
      <TableFooter>
        <TableRow className="hover:bg-transparent">
          <TableHead scope="row" colSpan={3} className={cn('text-foreground', EDGE)}>
            Total
          </TableHead>
          <TableCell className={cn('text-right text-lg font-bold tabular-nums', EDGE)}>
            {formatPKR(total)}
          </TableCell>
        </TableRow>
      </TableFooter>
    </Table>
  )
}

/** Phones: each line stacked as "name · qty × price = total" (spec 10 C-02 Mobile). */
function LineList({ groups, total }: { groups: ReadonlyArray<LineGroup>; total: number }) {
  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <div key={group.key}>
          <h3 className="flex items-baseline justify-between gap-3 text-base font-semibold text-foreground">
            {group.label}
            <span className="text-sm font-normal text-helper">{group.count}</span>
          </h3>
          <ul className="mt-1 divide-y divide-border-faint">
            {group.lines.map((line) => (
              <li key={line.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{line.description}</p>
                  <p className="mt-0.5 text-sm text-muted-foreground tabular-nums">
                    {quantity(line)} × {formatPKR(line.unit_price)}
                  </p>
                </div>
                <p className="shrink-0 text-sm font-semibold text-foreground tabular-nums">
                  {formatPKR(line.total)}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="flex items-baseline justify-between gap-4 border-t border-border pt-4">
        <span className="text-base font-semibold text-foreground">Total</span>
        <span className="text-lg font-bold text-foreground tabular-nums">{formatPKR(total)}</span>
      </p>
    </div>
  )
}

export interface EstimateCardProps {
  booking: Pick<MockBooking, 'estimateItems' | 'estimateTotal' | 'inspectionNotes'>
  decision: EstimateDecision
  /** When the shop sent it (the `AWAITING_CUSTOMER` step). */
  sentAt?: string
  /** When the customer approved or declined it. */
  decidedAt?: string
  timeZone: string
  /** The decision buttons, shown in the card footer from `md` (phones get the sticky bar). */
  actions?: ReactNode
}

/**
 * C-02 `EstimateView` for the customer (spec 09 §4.5, after Shop-Ware's DVX): the total first,
 * what the technician found, the parts and labour lines, what happens after approval, and the
 * decision or its outcome.
 */
export function EstimateCard({
  booking,
  decision,
  sentAt,
  decidedAt,
  timeZone,
  actions,
}: EstimateCardProps) {
  const parts = booking.estimateItems.filter((line) => line.type === 'PART')
  const labour = booking.estimateItems.filter((line) => line.type === 'LABOR')
  const total = booking.estimateTotal
  const groups: LineGroup[] = []
  if (parts.length > 0) {
    groups.push({
      key: 'parts',
      label: 'Parts',
      count: plural(parts.length, 'item', 'items'),
      lines: parts,
    })
  }
  if (labour.length > 0) {
    groups.push({
      key: 'labour',
      label: 'Labour',
      count: plural(labour.length, 'item', 'items'),
      lines: labour,
    })
  }
  const badge = DECISION_BADGE[decision]
  const decidedOn = decidedAt ? ` on ${formatDateTime(decidedAt, timeZone)}` : ''

  return (
    <Card id="estimate" role="region" aria-labelledby="estimate-title" className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h2 id="estimate-title" className="text-lg leading-7 font-semibold text-foreground">
            Your estimate
          </h2>
          <Badge variant={badge.variant}>{badge.label}</Badge>
        </div>
        <CardDescription>
          Version 1{sentAt ? ` · Sent ${formatShortDateTime(sentAt, timeZone)}` : ''}
        </CardDescription>
      </CardHeader>

      <div className="space-y-6 p-(--card-spacing)">
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 rounded-xl bg-layer p-4 sm:p-5">
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              {decision === 'pending' ? 'Total to approve' : 'Estimate total'}
            </p>
            <p className="mt-1 text-3xl font-extrabold tracking-tight text-foreground tabular-nums">
              {formatPKR(total)}
            </p>
          </div>
          {groups.length > 0 ? (
            <dl className="flex gap-8 text-sm">
              {groups.map((group) => (
                <div key={group.key}>
                  <dt className="text-muted-foreground">{group.label}</dt>
                  <dd className="mt-0.5 font-semibold text-foreground tabular-nums">
                    {formatPKR(sum(group.lines))}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>

        {booking.inspectionNotes ? (
          <div className="flex gap-3.5">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
              <ScanSearch className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 space-y-1">
              <h3 className="text-base font-semibold text-foreground">What the technician found</h3>
              <p className="text-base text-muted-foreground">{booking.inspectionNotes}</p>
            </div>
          </div>
        ) : null}

        {groups.length > 0 ? (
          <div className="md:hidden">
            <LineList groups={groups} total={total} />
          </div>
        ) : null}
      </div>

      {groups.length > 0 ? (
        <div className="hidden border-t border-border-faint md:block">
          <LineTable groups={groups} total={total} />
        </div>
      ) : null}

      {decision === 'pending' ? (
        <div className="border-t border-border-faint p-(--card-spacing)">
          <h3 className="text-base font-semibold text-foreground">
            What happens after you approve
          </h3>
          <ol className="mt-4 grid gap-4 sm:grid-cols-3 sm:gap-5">
            {AFTER_APPROVAL.map((step) => (
              <li key={step.title} className="flex gap-3 sm:flex-col sm:gap-2.5">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
                  <step.icon className="size-4.5" aria-hidden="true" />
                </span>
                <div className="space-y-0.5">
                  <p className="text-sm font-semibold text-foreground">{step.title}</p>
                  <p className="text-sm text-muted-foreground">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="mt-5 text-sm text-muted-foreground">
            Not sure about something? Call the shop before you decide, or decline and they&apos;ll
            revise it.
          </p>
        </div>
      ) : null}

      {decision === 'pending' && actions ? (
        <div className="hidden flex-wrap items-center justify-between gap-x-4 gap-y-3 border-t border-border-faint bg-muted px-(--card-spacing) py-4 md:flex">
          <p className="text-sm text-muted-foreground">No work starts until you approve.</p>
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        </div>
      ) : null}

      {decision === 'approved' ? (
        <p className="flex items-start gap-3 border-t border-status-handover-border bg-success-subtle px-(--card-spacing) py-4 text-sm font-semibold text-success-ink">
          <CircleCheck className="mt-px size-5 shrink-0" aria-hidden="true" />
          <span>Approved by you{decidedOn}.</span>
        </p>
      ) : null}

      {decision === 'declined' ? (
        <div className="flex items-start gap-3 border-t border-status-estimate-rejected-border bg-danger-subtle px-(--card-spacing) py-4 text-sm">
          <FileX className="mt-px size-5 shrink-0 text-danger-ink" aria-hidden="true" />
          <p className="text-foreground">
            <span className="font-semibold text-danger-ink">
              You declined this estimate{decidedOn}.
            </span>{' '}
            The shop will contact you to revise it.
          </p>
        </div>
      ) : null}
    </Card>
  )
}
