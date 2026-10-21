'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { useForm, type FieldErrors } from 'react-hook-form'

import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import type { MockPart } from '@/lib/mock-data'

import { FormErrorSummary, type FormErrorItem } from './form-error-summary'
import { partSchema, type PartFormValues } from './inventory-schemas'
import { StockFigures } from './stock-figures'

/** What the sheet hands back: trimmed, the SKU upper-cased, the numbers converted. */
export interface PartDraft {
  sku: string
  name: string
  category: string
  unitCost: number
  reorderLevel: number
}

type FieldName = keyof PartFormValues

const FIELDS: ReadonlyArray<{ name: FieldName; id: string; label: string }> = [
  { name: 'sku', id: 'part-sku', label: 'SKU' },
  { name: 'name', id: 'part-name', label: 'Part name' },
  { name: 'category', id: 'part-category', label: 'Category' },
  { name: 'unit_cost', id: 'part-unit-cost', label: 'Unit cost' },
  { name: 'reorder_level', id: 'part-reorder-level', label: 'Reorder level' },
]

const ID = Object.fromEntries(FIELDS.map((field) => [field.name, field.id])) as Record<
  FieldName,
  string
>

/** At most this many category suggestions (the most used) under the field. */
const MAX_SUGGESTIONS = 4

/**
 * PP-03 part create / edit `Sheet` (spec 10): SKU, name, category, unit cost and reorder level.
 * There is no on-hand field (D44): a new part starts at 0 and stock changes only through Adjust
 * stock. `onSave` returns a message for the SKU field (another part uses it) or `null` once saved.
 */
export function PartSheet({
  open,
  onOpenChange,
  onCloseAutoFocus,
  part,
  formKey,
  categories,
  canManageStock,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Puts focus back on what opened the sheet (it has no `SheetTrigger`). */
  onCloseAutoFocus: (event: Event) => void
  /** The part to edit; `null` adds a new one. */
  part: MockPart | null
  /** Changes on every opening, so the form starts again from the part's current values. */
  formKey: string
  categories: ReadonlyArray<string>
  /** D44: the Parts Person sets the opening stock; the Owner's helper says who does. */
  canManageStock: boolean
  onSave: (draft: PartDraft) => string | null
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="gap-0"
        onOpenAutoFocus={(event) => {
          // Radix would also select the field's text; an edit must not invite overwriting the SKU.
          event.preventDefault()
          document.getElementById(ID.sku)?.focus()
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <SheetHeader className="border-b border-border-faint">
          <SheetTitle>{part ? 'Edit part' : 'Add part'}</SheetTitle>
          <SheetDescription>
            {part
              ? part.name
              : canManageStock
                ? 'New parts start at 0 on hand. Set the opening stock with Adjust stock once the part is added.'
                : 'New parts start at 0 on hand. Your Parts Person sets the opening stock.'}
          </SheetDescription>
        </SheetHeader>
        <PartForm key={formKey} part={part} categories={categories} onSave={onSave} />
      </SheetContent>
    </Sheet>
  )
}

function PartForm({
  part,
  categories,
  onSave,
}: {
  part: MockPart | null
  categories: ReadonlyArray<string>
  onSave: (draft: PartDraft) => string | null
}) {
  const form = useForm<PartFormValues>({
    resolver: zodResolver(partSchema),
    mode: 'onTouched',
    defaultValues: part
      ? {
          sku: part.sku,
          name: part.name,
          category: part.category,
          unit_cost: String(part.unit_price),
          reorder_level: String(part.reorder_level),
        }
      : { sku: '', name: '', category: '', unit_cost: '', reorder_level: '5' },
  })
  const {
    register,
    setError,
    setFocus,
    setValue,
    formState: { errors, isSubmitted },
  } = form

  const submit = form.handleSubmit((values) => {
    const skuError = onSave({
      sku: values.sku,
      name: values.name,
      category: values.category,
      unitCost: Number(values.unit_cost),
      reorderLevel: Number(values.reorder_level),
    })
    if (skuError) setError('sku', { type: 'duplicate', message: skuError }, { shouldFocus: true })
  })

  const suggestions = categories.slice(0, MAX_SUGGESTIONS)
  /** The hint (when the field has one) and the error, for `aria-describedby`. */
  const describedBy = (name: FieldName, hint = true) =>
    [hint ? `${ID[name]}-hint` : null, errors[name] ? `${ID[name]}-error` : null]
      .filter(Boolean)
      .join(' ') || undefined

  return (
    <form noValidate onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto p-6">
        {isSubmitted ? (
          <FormErrorSummary
            errors={errorItems(errors)}
            onFocusField={(id) => {
              const field = FIELDS.find((f) => f.id === id)
              if (field) setFocus(field.name)
            }}
          />
        ) : null}

        {part ? (
          <StockFigures part={part}>
            <p className="text-sm text-muted-foreground">
              Stock changes go through Adjust stock, so each one has a reason.
            </p>
          </StockFigures>
        ) : null}

        <FieldGroup>
          <Field data-invalid={Boolean(errors.sku)}>
            <FieldLabel htmlFor={ID.sku}>SKU</FieldLabel>
            <Input
              id={ID.sku}
              className="font-mono uppercase"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={40}
              aria-invalid={Boolean(errors.sku)}
              aria-describedby={describedBy('sku')}
              {...register('sku')}
            />
            <FieldDescription id={`${ID.sku}-hint`}>
              Letters, numbers and . _ / - only, e.g. BP-FR-02.
            </FieldDescription>
            <FieldMessage id={`${ID.sku}-error`} message={errors.sku?.message} />
          </Field>

          <Field data-invalid={Boolean(errors.name)}>
            <FieldLabel htmlFor={ID.name}>Part name</FieldLabel>
            <Input
              id={ID.name}
              autoComplete="off"
              maxLength={120}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={describedBy('name', false)}
              {...register('name')}
            />
            <FieldMessage id={`${ID.name}-error`} message={errors.name?.message} />
          </Field>

          <Field data-invalid={Boolean(errors.category)}>
            <FieldLabel htmlFor={ID.category}>
              Category <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id={ID.category}
              autoComplete="off"
              maxLength={60}
              aria-invalid={Boolean(errors.category)}
              aria-describedby={describedBy('category')}
              {...register('category')}
            />
            <FieldDescription id={`${ID.category}-hint`}>
              {suggestions.length > 0
                ? 'Type one, or pick one already in use.'
                : 'Shown under the part name, e.g. Brakes or Filters.'}
            </FieldDescription>
            {suggestions.length > 0 ? (
              <div role="group" aria-label="Categories in use" className="flex flex-wrap gap-2">
                {suggestions.map((name) => (
                  <Button
                    key={name}
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setValue('category', name, { shouldDirty: true, shouldValidate: true })
                    }
                  >
                    {name}
                  </Button>
                ))}
              </div>
            ) : null}
            <FieldMessage id={`${ID.category}-error`} message={errors.category?.message} />
          </Field>

          <Field data-invalid={Boolean(errors.unit_cost)}>
            <FieldLabel htmlFor={ID.unit_cost}>Unit cost</FieldLabel>
            <InputGroup className="sm:max-w-56">
              <InputGroupAddon>
                <InputGroupText>Rs</InputGroupText>
              </InputGroupAddon>
              <InputGroupInput
                id={ID.unit_cost}
                inputMode="numeric"
                autoComplete="off"
                className="tabular-nums"
                aria-invalid={Boolean(errors.unit_cost)}
                aria-describedby={describedBy('unit_cost')}
                {...register('unit_cost')}
              />
            </InputGroup>
            <FieldDescription id={`${ID.unit_cost}-hint`}>
              Whole rupees. Estimates use it as the part’s default price.
            </FieldDescription>
            <FieldMessage id={`${ID.unit_cost}-error`} message={errors.unit_cost?.message} />
          </Field>

          <Field data-invalid={Boolean(errors.reorder_level)}>
            <FieldLabel htmlFor={ID.reorder_level}>Reorder level</FieldLabel>
            <Input
              id={ID.reorder_level}
              inputMode="numeric"
              autoComplete="off"
              className="tabular-nums sm:max-w-56"
              aria-invalid={Boolean(errors.reorder_level)}
              aria-describedby={describedBy('reorder_level')}
              {...register('reorder_level')}
            />
            <FieldDescription id={`${ID.reorder_level}-hint`}>
              The part shows as low stock once what’s available drops to this number.
            </FieldDescription>
            <FieldMessage
              id={`${ID.reorder_level}-error`}
              message={errors.reorder_level?.message}
            />
          </Field>
        </FieldGroup>
      </div>

      <SheetFooter className="flex-col-reverse sm:flex-row sm:justify-end">
        <SheetClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </SheetClose>
        <Button type="submit">{part ? 'Save changes' : 'Add part'}</Button>
      </SheetFooter>
    </form>
  )
}

function FieldMessage({ id, message }: { id: string; message?: string }) {
  return message ? <FieldError id={id}>{message}</FieldError> : null
}

function errorItems(errors: FieldErrors<PartFormValues>): FormErrorItem[] {
  return FIELDS.flatMap(({ name, id, label }) => {
    const message = errors[name]?.message
    return message ? [{ id, label, message }] : []
  })
}
