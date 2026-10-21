'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowRight, Minus, Plus } from 'lucide-react'
import { Controller, useForm, useWatch, type FieldErrors } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { MockPart } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { FormErrorSummary, type FormErrorItem } from './form-error-summary'
import { adjustmentError, availableOf, countLabel } from './inventory-model'
import { adjustSchemaFor, signedDelta, type AdjustFormValues } from './inventory-schemas'
import { StockFigures } from './stock-figures'

const QUANTITY_ID = 'adjust-quantity'
const REASON_ID = 'adjust-reason'
const MAX_QUANTITY = 100_000

/** One tap fills the reason; it can still be edited or typed from scratch. */
const REASONS: Record<AdjustFormValues['direction'], ReadonlyArray<string>> = {
  add: ['Opening stock', 'Delivery received', 'Stock count correction'],
  remove: ['Damaged or faulty', 'Lost or missing', 'Stock count correction'],
}

/**
 * PP-03 Adjust stock (spec 10, D82): a signed change, entered as Add / Remove and a quantity, and
 * a required reason. A live line shows the result; a change that would leave less on hand than is
 * reserved for jobs, or below zero, is refused with the API's 409 message and the sheet stays open.
 * `onApply` returns that message, or `null` once the stock is updated.
 */
export function AdjustStockSheet({
  open,
  onOpenChange,
  onCloseAutoFocus,
  part,
  formKey,
  onApply,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Puts focus back on what opened the sheet (it has no `SheetTrigger`). */
  onCloseAutoFocus: (event: Event) => void
  part: MockPart | null
  /** Changes on every opening, so the form starts empty. */
  formKey: string
  onApply: (delta: number, reason: string) => string | null
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="gap-0"
        onOpenAutoFocus={(event) => {
          // Start in the quantity field: the change already defaults to "Add stock".
          event.preventDefault()
          document.getElementById(QUANTITY_ID)?.focus()
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <SheetHeader className="border-b border-border-faint">
          <SheetTitle>Adjust stock</SheetTitle>
          <SheetDescription>
            {part ? `${part.name} · ${part.sku}` : 'Opening stock and count corrections.'}
          </SheetDescription>
        </SheetHeader>
        {part ? <AdjustForm key={formKey} part={part} onApply={onApply} /> : null}
      </SheetContent>
    </Sheet>
  )
}

function AdjustForm({
  part,
  onApply,
}: {
  part: MockPart
  onApply: (delta: number, reason: string) => string | null
}) {
  const form = useForm<AdjustFormValues>({
    // Checked against the part's current stock on every render (RHF reads the latest resolver).
    resolver: zodResolver(adjustSchemaFor(part)),
    mode: 'onTouched',
    defaultValues: { direction: 'add', quantity: '', reason: '' },
  })
  const {
    control,
    register,
    setError,
    setFocus,
    setValue,
    formState: { errors, isSubmitted },
  } = form
  const [direction, quantity] = useWatch({ control, name: ['direction', 'quantity'] })

  const delta = signedDelta({ direction, quantity })
  const amount = Math.abs(delta)
  /** The change the preview and the button describe, once the quantity is a valid number. */
  const change = amount > 0 && amount <= MAX_QUANTITY ? delta : null
  const after = change === null ? null : part.on_hand + change
  const refused = change !== null && adjustmentError(part, change) !== null
  const available = Math.max(availableOf(part), 0)

  const submit = form.handleSubmit((values) => {
    const problem = onApply(signedDelta(values), values.reason)
    if (problem) setError('quantity', { type: 'stock', message: problem }, { shouldFocus: true })
  })

  const describedBy = (id: string, hasError: boolean) =>
    [`${id}-hint`, hasError ? `${id}-error` : null].filter(Boolean).join(' ')

  return (
    <form noValidate onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {isSubmitted ? (
          <FormErrorSummary
            errors={errorItems(errors)}
            onFocusField={(id) => setFocus(id === REASON_ID ? 'reason' : 'quantity')}
          />
        ) : null}

        <StockFigures part={part} />

        <FieldGroup>
          <FieldSet className="gap-0">
            <FieldLegend id="adjust-direction" variant="label">
              Change
            </FieldLegend>
            <Controller
              control={control}
              name="direction"
              render={({ field }) => (
                <ToggleGroup
                  type="single"
                  variant="outline"
                  spacing={0}
                  value={field.value}
                  onValueChange={(value) => {
                    if (value === 'add' || value === 'remove') field.onChange(value)
                  }}
                  aria-labelledby="adjust-direction"
                  className="w-full"
                >
                  <ToggleGroupItem value="add" className="h-10.5 flex-1">
                    <Plus aria-hidden="true" />
                    Add stock
                  </ToggleGroupItem>
                  <ToggleGroupItem value="remove" className="h-10.5 flex-1">
                    <Minus aria-hidden="true" />
                    Remove stock
                  </ToggleGroupItem>
                </ToggleGroup>
              )}
            />
          </FieldSet>

          <Field data-invalid={Boolean(errors.quantity)}>
            <FieldLabel htmlFor={QUANTITY_ID}>Quantity</FieldLabel>
            <Input
              id={QUANTITY_ID}
              inputMode="numeric"
              autoComplete="off"
              className="tabular-nums sm:max-w-56"
              aria-invalid={Boolean(errors.quantity)}
              aria-describedby={describedBy(QUANTITY_ID, Boolean(errors.quantity))}
              {...register('quantity')}
            />
            <FieldDescription id={`${QUANTITY_ID}-hint`}>
              {quantityHint(direction, part, available)}
            </FieldDescription>
            {errors.quantity?.message ? (
              <FieldError id={`${QUANTITY_ID}-error`}>{errors.quantity.message}</FieldError>
            ) : null}
          </Field>

          <div aria-live="polite">
            {after !== null ? (
              <p
                className={cn(
                  'flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border px-4 py-3 text-sm',
                  refused
                    ? 'border-status-estimate-rejected-border bg-danger-subtle text-danger-ink'
                    : 'border-status-intake-border bg-info-subtle text-foreground',
                )}
              >
                <span>On hand after this change:</span>
                <span className="inline-flex items-center gap-1.5 font-semibold tabular-nums">
                  <span className="sr-only">from</span>
                  {part.on_hand}
                  <ArrowRight className="size-4" aria-hidden="true" />
                  <span className="sr-only">to</span>
                  {after}
                </span>
                {refused && !errors.quantity ? (
                  // Before submitting; afterwards the quantity's own error says it.
                  <span className="basis-full">
                    {after < 0
                      ? 'That’s below zero.'
                      : `That’s less than the ${countLabel(part.reserved, 'unit')} reserved for jobs.`}
                  </span>
                ) : null}
              </p>
            ) : null}
          </div>

          <Field data-invalid={Boolean(errors.reason)}>
            <FieldLabel htmlFor={REASON_ID}>Reason</FieldLabel>
            <Input
              id={REASON_ID}
              autoComplete="off"
              maxLength={500}
              aria-invalid={Boolean(errors.reason)}
              aria-describedby={describedBy(REASON_ID, Boolean(errors.reason))}
              {...register('reason')}
            />
            <FieldDescription id={`${REASON_ID}-hint`}>
              Type it, or pick a common one.
            </FieldDescription>
            <div role="group" aria-label="Common reasons" className="flex flex-wrap gap-2">
              {REASONS[direction].map((reason) => (
                <Button
                  key={reason}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setValue('reason', reason, { shouldDirty: true, shouldValidate: true })
                  }
                >
                  {reason}
                </Button>
              ))}
            </div>
            {errors.reason?.message ? (
              <FieldError id={`${REASON_ID}-error`}>{errors.reason.message}</FieldError>
            ) : null}
          </Field>
        </FieldGroup>
      </div>

      <SheetFooter className="flex-col-reverse sm:flex-row sm:justify-end">
        <SheetClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </SheetClose>
        <Button type="submit">
          {change === null
            ? 'Apply adjustment'
            : `${change > 0 ? 'Add' : 'Remove'} ${countLabel(amount, 'unit')}`}
        </Button>
      </SheetFooter>
    </form>
  )
}

function quantityHint(
  direction: AdjustFormValues['direction'],
  part: Pick<MockPart, 'on_hand' | 'reserved'>,
  available: number,
): string {
  if (direction === 'add') return 'Units coming in, e.g. opening stock or a recount.'
  if (available === 0) {
    return part.reserved > 0
      ? 'Nothing can be removed: everything on hand is reserved for jobs.'
      : 'There’s nothing on hand to remove.'
  }
  if (part.reserved > 0) {
    return `You can remove up to ${available}; ${countLabel(part.reserved, 'unit')} ${
      part.reserved === 1 ? 'is' : 'are'
    } reserved for jobs.`
  }
  return `You can remove up to ${available}.`
}

function errorItems(errors: FieldErrors<AdjustFormValues>): FormErrorItem[] {
  const items: FormErrorItem[] = []
  if (errors.quantity?.message) {
    items.push({ id: QUANTITY_ID, label: 'Quantity', message: errors.quantity.message })
  }
  if (errors.reason?.message) {
    items.push({ id: REASON_ID, label: 'Reason', message: errors.reason.message })
  }
  return items
}
