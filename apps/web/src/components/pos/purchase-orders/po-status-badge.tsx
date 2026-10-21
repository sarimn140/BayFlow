import { PackageCheck, PackageOpen, Truck, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { PoStatus } from './po-model'

/** Spec 09 §3.4 `PurchaseOrderStatus`: Ordered (info), Partially received (warning), Received (success). */
export const PO_STATUS_META = {
  ORDERED: { label: 'Ordered', variant: 'info', icon: Truck },
  PARTIALLY_RECEIVED: { label: 'Partially received', variant: 'warning', icon: PackageOpen },
  RECEIVED: { label: 'Received', variant: 'success', icon: PackageCheck },
} as const satisfies Record<
  PoStatus,
  { label: string; variant: 'info' | 'warning' | 'success'; icon: LucideIcon }
>

/**
 * Purchase order status chip, built like `StatusBadge`: soft fill, icon and label, an `sr-only`
 * "Status:" prefix. `sm` (24px) in lists and tables; `md` (28px) beside the page title.
 */
export function PoStatusBadge({
  status,
  size = 'sm',
  className,
}: {
  status: PoStatus
  size?: 'sm' | 'md'
  className?: string
}) {
  const meta = PO_STATUS_META[status]
  const Icon = meta.icon
  return (
    <Badge
      variant={meta.variant}
      data-status={status}
      className={cn(
        size === 'md' &&
          'h-7 gap-1.5 px-3 text-sm has-data-[icon=inline-start]:pl-2.5 [&>svg]:size-4',
        className,
      )}
    >
      <Icon aria-hidden="true" data-icon="inline-start" />
      <span className="sr-only">Status: </span>
      {meta.label}
    </Badge>
  )
}
