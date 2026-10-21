'use client'

import { TriangleAlert } from 'lucide-react'
import type { ComponentProps, FormEvent } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { formatPKR } from '@/lib/format'

import { orderTotal, plural, shortList, type PartRequirement } from './parts-data'

type CloseAutoFocus = ComponentProps<typeof DialogContent>['onCloseAutoFocus']

interface ActionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The booking reference, named in every title (spec 09 §4.6). */
  reference: string
  onConfirm: () => void
  /** Lets the page move focus to the outcome once the dialog has closed. */
  onCloseAutoFocus?: CloseAutoFocus
}

/** The reference never breaks across lines. */
function Ref({ children }: { children: string }) {
  return <span className="font-mono whitespace-nowrap">{children}</span>
}

/**
 * A part line: name over SKU (or "Not in inventory"), the quantity on the right, and with
 * `withCost` the unit cost under it.
 */
function PartLine({
  row,
  quantity,
  withCost = false,
}: {
  row: PartRequirement
  quantity: number
  withCost?: boolean
}) {
  return (
    <li className="flex items-start justify-between gap-4 px-4 py-3">
      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-medium text-foreground">{row.description}</p>
        <p className="text-xs text-helper">
          {row.inInventory ? <span className="font-mono">{row.sku}</span> : 'Not in inventory'}
        </p>
      </div>
      <div className="shrink-0 space-y-0.5 text-right">
        <p className="text-sm font-semibold text-foreground tabular-nums">× {quantity}</p>
        {withCost ? (
          <p className="text-xs text-helper tabular-nums">{formatPKR(row.unitCost)} each</p>
        ) : null}
      </div>
    </li>
  )
}

/**
 * `order-parts` (spec 09 §4.6): a purchase order for every short part, at its shortage, with an
 * optional supplier. The job then moves to Parts ordered.
 */
export function OrderPartsDialog({
  open,
  onOpenChange,
  reference,
  onConfirm,
  onCloseAutoFocus,
  short,
  supplier,
  onSupplierChange,
}: ActionDialogProps & {
  /** The short parts; each is ordered at its shortage. */
  short: ReadonlyArray<PartRequirement>
  supplier: string
  onSupplierChange: (value: string) => void
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onConfirm()
  }

  // The supplier is optional and prefilled, so focus starts on the dialog itself (its title is
  // read out): a phone keeps its keyboard closed and a stray key never replaces the supplier.
  const focusDialog = (event: Event) => {
    event.preventDefault()
    if (event.currentTarget instanceof HTMLElement) event.currentTarget.focus()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg"
        onOpenAutoFocus={focusDialog}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <DialogHeader>
          <DialogTitle>
            Order missing parts for <Ref>{reference}</Ref>
          </DialogTitle>
          <DialogDescription>
            A purchase order goes to the supplier for the parts below, and the job moves to Parts
            ordered until they arrive.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="grid gap-5">
          <Field>
            <FieldLabel htmlFor="po-supplier">Supplier</FieldLabel>
            <Input
              id="po-supplier"
              value={supplier}
              onChange={(event) => onSupplierChange(event.target.value)}
              maxLength={120}
              autoComplete="organization"
            />
            <FieldDescription>Optional. Shown on the purchase order.</FieldDescription>
          </Field>

          <div className="space-y-2">
            <h3 className="text-sm font-medium text-foreground">
              {plural(short.length, 'part')} to order
            </h3>
            <ul className="divide-y divide-border-faint rounded-xl border border-border">
              {short.map((row) => (
                <PartLine key={row.id} row={row} quantity={row.shortage} withCost />
              ))}
            </ul>
            <div className="flex items-baseline justify-between gap-4 rounded-xl bg-layer px-4 py-3">
              <span className="text-sm text-muted-foreground">Order total</span>
              <span className="text-lg font-bold text-foreground tabular-nums">
                {formatPKR(orderTotal(short))}
              </span>
            </div>
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Create purchase order</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * `mark-parts-ready` (spec 09 §4.6): confirm before the job moves to Parts ready. From Parts
 * ordered it warns when stock still doesn't cover a part (receive the delivery first).
 */
export function MarkReadyDialog({
  open,
  onOpenChange,
  reference,
  onConfirm,
  onCloseAutoFocus,
  requiredCount,
  short,
  technician,
}: ActionDialogProps & {
  requiredCount: number
  /** Parts stock still doesn't cover. */
  short: ReadonlyArray<PartRequirement>
  technician: string
}) {
  const description =
    requiredCount === 0
      ? `There are no parts on the estimate. The job moves to Parts ready, so you can release it to ${technician}.`
      : short.length === 0
        ? `${requiredCount === 1 ? 'The part is' : `All ${requiredCount} parts are`} in stock. The job moves to Parts ready, so you can allocate the parts to ${technician}.`
        : `The job moves to Parts ready, so you can allocate the parts to ${technician}.`

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>
            Mark parts ready for <Ref>{reference}</Ref>?
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {short.length > 0 ? (
          <Alert variant="warning" role="note">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Stock doesn&apos;t cover {plural(short.length, 'part')} yet</AlertTitle>
            <AlertDescription>
              Short: {shortList(short)}. Receive the delivery on its purchase order first, so stock
              is up to date.
            </AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={onConfirm}>Mark parts ready</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * `allocate-parts` (spec 09 §4.6): the confirm lists every part and quantity handed to the
 * technician; the job then moves to In repair and leaves the parts queue.
 */
export function AllocateDialog({
  open,
  onOpenChange,
  reference,
  onConfirm,
  onCloseAutoFocus,
  rows,
  technician,
}: ActionDialogProps & { rows: ReadonlyArray<PartRequirement>; technician: string }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>
            Allocate parts for <Ref>{reference}</Ref>?
          </DialogTitle>
          <DialogDescription>
            {rows.length > 0
              ? `Hand these parts to ${technician}. The job moves to In repair and leaves your queue.`
              : `There are no parts to hand over. The job moves to In repair, so ${technician} can start.`}
          </DialogDescription>
        </DialogHeader>

        {rows.length > 0 ? (
          <ul className="divide-y divide-border-faint rounded-xl border border-border">
            {rows.map((row) => (
              <PartLine key={row.id} row={row} quantity={row.required} />
            ))}
          </ul>
        ) : null}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={onConfirm}>Allocate parts</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
