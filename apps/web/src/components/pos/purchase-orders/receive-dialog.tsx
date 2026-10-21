'use client'

import { PackageCheck } from 'lucide-react'
import type { ComponentProps } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { MockPurchaseOrder } from '@/lib/mock-data'

import { formatCount, plural, unitsAdded, type ReceiptLine } from './po-model'

/**
 * "Receive into stock" confirmation (spec 10 PP-05 "Confirm receipt"): every line with the units
 * it adds and its on-hand count before → after, from `receiptPreview` (the receive action's own
 * arithmetic), so the Parts Person checks the delivery before stock changes.
 */
export function ReceiveDialog({
  open,
  onOpenChange,
  po,
  preview,
  onConfirm,
  onCloseAutoFocus,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  po: MockPurchaseOrder
  preview: ReadonlyArray<ReceiptLine>
  onConfirm: () => void
  onCloseAutoFocus?: ComponentProps<typeof DialogContent>['onCloseAutoFocus']
}) {
  const adding = unitsAdded(preview)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>
            Receive <span className="font-mono whitespace-nowrap">{po.po_number}</span> into stock?
          </DialogTitle>
          <DialogDescription>
            Check the delivery from {po.supplier} against this order.{' '}
            {adding > 0
              ? `Confirming adds ${plural(adding, 'unit')} to inventory.`
              : 'None of its parts are in inventory, so stock stays the same.'}
          </DialogDescription>
        </DialogHeader>

        <ul
          className="divide-y divide-border-faint rounded-xl border border-border"
          aria-label="Stock after receipt"
        >
          {preview.map(({ line, part, before, after }, index) => (
            <li
              key={`${line.part_sku}-${index}`}
              className="flex items-start justify-between gap-4 px-4 py-3"
            >
              <div className="min-w-0 space-y-0.5">
                <p className="text-sm font-medium text-foreground">{line.part_name}</p>
                <p className="text-sm text-muted-foreground tabular-nums">
                  <span className="font-mono">{line.part_sku}</span> ·{' '}
                  {part && before !== null && after !== null ? (
                    <>
                      On hand {formatCount(before)} <span aria-hidden="true">→</span>
                      <span className="sr-only">becomes</span>{' '}
                      <span className="font-semibold text-foreground">{formatCount(after)}</span>
                    </>
                  ) : (
                    'Not in inventory, stock unchanged'
                  )}
                </p>
              </div>
              <p className="shrink-0 text-sm font-semibold text-success-ink tabular-nums">
                +{formatCount(line.quantity)}{' '}
                <span className="sr-only">{line.quantity === 1 ? 'unit' : 'units'}</span>
              </p>
            </li>
          ))}
        </ul>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <Button type="button" onClick={onConfirm}>
            <PackageCheck aria-hidden="true" data-icon="inline-start" />
            Confirm receipt
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
