'use client'

import {
  ClipboardList,
  Package,
  PencilLine,
  ScanSearch,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

import { DataTableCard } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatPKR } from '@/lib/format'
import type { MockBooking, MockEstimateItem } from '@/lib/mock-data'
import { BOOKING_STATUS_META, type BookingStatus } from '@/lib/status'

import { estimateTotals } from './estimate-math'

/** The page returns focus here when the estimate editor closes. */
export const EDIT_ESTIMATE_BUTTON_ID = 'sa-edit-estimate'

type BadgeVariant = 'success' | 'warning' | 'info' | 'neutral' | 'destructive'

/** When the estimate was submitted, sent and decided, already formatted in shop time. */
export interface EstimateTimes {
  submitted?: string
  sent?: string
  approved?: string
  declined?: string
}

const on = (when?: string) => (when ? ` on ${when}` : '')

/**
 * The estimate's own state (spec 09 §4.5 `EstimateStatus` badge), read from the booking, with a
 * timestamped decision ("Approved by Ahmed on …").
 */
function estimateState(
  booking: MockBooking,
  context: { technician?: string; saDraftOpen: boolean; times: EstimateTimes },
): { badge?: { label: string; variant: BadgeVariant }; description: string } {
  const customer = booking.customerName
  const { times } = context
  const approved: ReadonlyArray<BookingStatus> = [
    'ESTIMATE_APPROVED',
    'PARTS_PENDING',
    'PARTS_ORDERED',
    'PARTS_READY',
    'IN_REPAIR',
    'QC_PENDING',
    'QC_IN_PROGRESS',
    'READY_FOR_PICKUP',
    'COMPLETED',
  ]
  if (
    approved.includes(booking.status) ||
    (booking.status === 'CANCELLED' && booking.estimateApproved)
  ) {
    return {
      badge: { label: 'Approved', variant: 'success' },
      description: `Approved by ${customer}${on(times.approved)}`,
    }
  }
  switch (booking.status) {
    case 'INSPECTING':
      return {
        badge: { label: 'Draft', variant: 'neutral' },
        description: `${context.technician ?? 'The technician'} is updating it`,
      }
    case 'ESTIMATE_REVIEW':
      return context.saDraftOpen
        ? { badge: { label: 'Draft', variant: 'neutral' }, description: 'Your draft, not sent yet' }
        : {
            badge: { label: 'Submitted', variant: 'info' },
            description: times.submitted
              ? `Submitted by ${context.technician ?? 'the technician'} on ${times.submitted}`
              : `Submitted by ${context.technician ?? 'the technician'} for your review`,
          }
    case 'AWAITING_CUSTOMER':
      return {
        badge: { label: 'Awaiting approval', variant: 'warning' },
        description: `Sent to ${customer}${on(times.sent)}`,
      }
    case 'ESTIMATE_REJECTED':
      return {
        badge: { label: 'Declined', variant: 'destructive' },
        description: `Declined by ${customer}${on(times.declined)}`,
      }
    case 'CANCELLED':
      return { description: 'The booking was cancelled before this estimate was approved' }
    default:
      return { description: 'Parts and labour for this visit' }
  }
}

function emptyCopy(status: BookingStatus, technician?: string): string {
  switch (status) {
    case 'PENDING':
      return 'Once you confirm the booking and assign a technician, they inspect the car and write the estimate.'
    case 'CONFIRMED':
      return 'The technician you assign inspects the car and writes the estimate.'
    case 'ASSIGNED':
    case 'INSPECTING':
      return `${technician ?? 'The technician'} writes it during the inspection.`
    case 'ESTIMATE_REVIEW':
      return 'It has no lines yet. Add parts and labour before you send it to the customer.'
    default:
      return 'No estimate was written for this booking.'
  }
}

const GROUPS: ReadonlyArray<{ type: MockEstimateItem['type']; label: string; icon: LucideIcon }> = [
  { type: 'PART', label: 'Parts', icon: Package },
  { type: 'LABOR', label: 'Labour', icon: Wrench },
]

const quantityText = (quantity: number) => String(quantity)

/**
 * SA-02's estimate panel (spec 10 SA-02, spec 09 §4.5 `EstimateView`): version and state, the
 * technician's findings, the lines grouped as parts and labour, and the totals. "Edit estimate"
 * sits in its header when `edit-estimate` is allowed.
 */
export function EstimateCard({
  booking,
  version,
  technician,
  saDraftOpen,
  times = {},
  onEdit,
}: {
  booking: MockBooking
  version: number
  technician?: string
  saDraftOpen: boolean
  times?: EstimateTimes
  /** Set when `allowed_actions` has `edit-estimate`. */
  onEdit?: () => void
}) {
  const items = booking.estimateItems
  const totals = estimateTotals(items)
  const state = estimateState(booking, { technician, saDraftOpen, times })
  const groups = GROUPS.map((group) => ({
    ...group,
    items: items.filter((item) => item.type === group.type),
  })).filter((group) => group.items.length > 0)
  const editButton = onEdit ? (
    <Button id={EDIT_ESTIMATE_BUTTON_ID} type="button" variant="outline" onClick={onEdit}>
      <PencilLine data-icon="inline-start" aria-hidden="true" />
      Edit estimate
    </Button>
  ) : null

  return (
    <DataTableCard
      title={
        <span className="flex flex-wrap items-center gap-2">
          Estimate
          {items.length > 0 ? (
            <Badge variant="secondary" className="tabular-nums">
              v{version}
            </Badge>
          ) : null}
          {items.length > 0 && state.badge ? (
            <Badge variant={state.badge.variant}>{state.badge.label}</Badge>
          ) : null}
        </span>
      }
      description={items.length > 0 ? state.description : undefined}
      actions={items.length > 0 ? editButton : undefined}
    >
      {booking.inspectionNotes ? (
        <div className="px-5 pb-5">
          <figure className="rounded-xl bg-layer px-4 py-3">
            <figcaption className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <ScanSearch className="size-4 text-muted-foreground" aria-hidden="true" />
              {technician ? `${technician}'s findings` : 'Inspection findings'}
            </figcaption>
            <blockquote className="mt-1 text-sm text-muted-foreground">
              {booking.inspectionNotes}
            </blockquote>
          </figure>
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="border-t border-border-faint">
          <EmptyState
            variant="inline"
            tone="neutral"
            icon={ClipboardList}
            title={BOOKING_STATUS_META[booking.status].terminal ? 'No estimate' : 'No estimate yet'}
            description={emptyCopy(booking.status, technician)}
            action={editButton ?? undefined}
          />
        </div>
      ) : (
        <>
          <div className="@container border-t border-border-faint">
            {/* A narrow column (phones, tablets, lg's two columns): the lines stacked */}
            <div className="@lg:hidden">
              {groups.map((group) => (
                <div key={group.type}>
                  <h3 className="flex items-center gap-2 px-5 pt-4 pb-1 text-sm font-semibold text-foreground">
                    <group.icon className="size-4 text-muted-foreground" aria-hidden="true" />
                    {group.label}
                  </h3>
                  <ul className="divide-y divide-border-faint">
                    {group.items.map((item) => (
                      <li
                        key={item.id}
                        className="flex items-start justify-between gap-4 px-5 py-3"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium wrap-break-word text-foreground">
                            {item.description}
                          </p>
                          <p className="text-xs text-helper tabular-nums">
                            {quantityText(item.quantity)} × {formatPKR(item.unit_price)}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-semibold text-foreground tabular-nums">
                          {formatPKR(item.total)}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            {/* A wide column (≥ 512px): the table */}
            <div className="hidden @lg:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-full">Item</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                {/* One row group per line type, labelled by its first row (scope="rowgroup"). */}
                {groups.map((group) => (
                  <TableBody
                    key={group.type}
                    className="border-b border-border-faint last:border-0"
                  >
                    <TableRow className="hover:bg-transparent">
                      <TableHead scope="rowgroup" colSpan={4} className="h-10 pt-3 text-foreground">
                        <span className="flex items-center gap-2 font-semibold">
                          <group.icon className="size-4 text-muted-foreground" aria-hidden="true" />
                          {group.label}
                        </span>
                      </TableHead>
                    </TableRow>
                    {group.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="whitespace-normal">{item.description}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {quantityText(item.quantity)}
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground tabular-nums">
                          {formatPKR(item.unit_price)}
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">
                          {formatPKR(item.total)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                ))}
              </Table>
            </div>
          </div>

          <div className="border-t border-border-faint p-5">
            <div className="rounded-xl bg-layer p-4">
              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Parts</dt>
                  <dd className="text-foreground tabular-nums">{formatPKR(totals.parts)}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Labour</dt>
                  <dd className="text-foreground tabular-nums">{formatPKR(totals.labour)}</dd>
                </div>
                <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-border pt-3">
                  <dt className="text-base font-semibold text-foreground">Grand total</dt>
                  <dd className="text-xl font-bold text-foreground tabular-nums">
                    {formatPKR(booking.estimateTotal)}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}
    </DataTableCard>
  )
}
