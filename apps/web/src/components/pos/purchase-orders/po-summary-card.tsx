import { PackageCheck, PackageOpen, Truck, type LucideIcon } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { formatDateTime, formatPKR } from '@/lib/format'
import type { MockPurchaseOrder } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { contentsLabel, type PoJob, type PoStatus } from './po-model'

type Tone = 'brand' | 'warning' | 'success'

const TONE: Record<Tone, { tile: string; ink: string }> = {
  brand: { tile: 'bg-brand-blue-subtle text-brand-blue-ink', ink: 'text-brand-blue-ink' },
  warning: { tile: 'bg-warning-subtle text-warning-ink', ink: 'text-warning-ink' },
  success: { tile: 'bg-success-subtle text-success-ink', ink: 'text-success-ink' },
}

interface StateCopy {
  tone: Tone
  icon: LucideIcon
  eyebrow: string
  title: string
  description: string
}

/** What the card leads with: the next step for Parts staff, the state for everyone else. */
function stateCopy(status: PoStatus, canReceive: boolean): StateCopy {
  if (status === 'RECEIVED') {
    return {
      tone: 'success',
      icon: PackageCheck,
      eyebrow: 'Status',
      title: 'Received into stock',
      description: 'The delivery was counted into inventory.',
    }
  }
  const partly = status === 'PARTIALLY_RECEIVED'
  if (canReceive) {
    return {
      tone: partly ? 'warning' : 'brand',
      icon: partly ? PackageOpen : Truck,
      eyebrow: 'Next step',
      title: 'Receive the delivery',
      description: 'Check the delivery against this order, then receive it into stock.',
    }
  }
  return {
    tone: partly ? 'warning' : 'brand',
    icon: partly ? PackageOpen : Truck,
    eyebrow: 'Status',
    title: partly ? 'Partly delivered' : 'Awaiting delivery',
    description: 'Parts staff receive it into stock when it arrives.',
  }
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right font-medium break-words text-foreground">{children}</dd>
    </div>
  )
}

/**
 * The PO's side card (spec 10 PP-05, DESIGN.md §6.5): where the order stands (or the next step),
 * supplier, order date, contents, the job it was raised for (D43) or a general restock, the order
 * total, and `action` — the "Receive into stock" button for Parts staff while the order is open.
 */
export function PoSummaryCard({
  po,
  job,
  timeZone,
  canReceive,
  action,
}: {
  po: MockPurchaseOrder
  /** The job behind `po.bookingId` (`poJob`), when this shop has it. */
  job: PoJob | undefined
  timeZone: string
  canReceive: boolean
  action?: ReactNode
}) {
  const state = stateCopy(po.status, canReceive)
  const Icon = state.icon

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-xl',
              TONE[state.tone].tile,
            )}
          >
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 space-y-1">
            <p className={cn('text-sm font-semibold', TONE[state.tone].ink)}>{state.eyebrow}</p>
            <h2 className="text-lg leading-6 font-semibold text-foreground">{state.title}</h2>
            <p className="text-sm text-muted-foreground">{state.description}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="gap-5">
        <dl className="divide-y divide-border-faint border-y border-border-faint text-sm">
          <DetailRow label="Supplier">{po.supplier}</DetailRow>
          <DetailRow label="Ordered">
            <time dateTime={po.created_at}>{formatDateTime(po.created_at, timeZone)}</time>
          </DetailRow>
          <DetailRow label="Items">{contentsLabel(po)}</DetailRow>
          <DetailRow label="Ordered for">
            {job ? (
              <>
                <Link
                  href={job.href}
                  className="rounded-sm font-mono font-semibold text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {job.reference}
                </Link>
                <span className="block text-sm font-normal text-muted-foreground">
                  {job.vehicle}
                </span>
              </>
            ) : po.bookingId ? (
              'Unknown job'
            ) : (
              'General restock'
            )}
          </DetailRow>
        </dl>
        <div className="flex items-baseline justify-between gap-4 rounded-xl bg-layer p-4">
          <span className="text-base font-semibold text-foreground">Order total</span>
          <span className="text-xl font-bold text-foreground tabular-nums">
            {formatPKR(po.total_amount)}
          </span>
        </div>
        {action}
      </CardContent>
    </Card>
  )
}
