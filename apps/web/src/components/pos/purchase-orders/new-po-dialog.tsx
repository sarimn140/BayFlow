'use client'

import { CircleAlert, Plus } from 'lucide-react'
import { useId, useState, type ComponentProps, type FormEvent } from 'react'

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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import { formatPKR } from '@/lib/format'
import {
  getPurchaseOrders,
  savePurchaseOrder,
  type MockPart,
  type MockPurchaseOrder,
} from '@/lib/mock-data'

import { PartPicker } from './part-picker'
import {
  MAX_QUANTITY,
  formatCount,
  newPurchaseOrderIdentity,
  validateNewPo,
  type NewPoErrors,
  type NewPoInput,
} from './po-model'

const FIELD_ORDER: ReadonlyArray<keyof NewPoInput> = ['supplier', 'quantity', 'unitCost']

/**
 * "New purchase order" (spec 10 PP-04, general restock): a supplier, a part from the shop's
 * inventory, a quantity and the unit cost (the part's cost until changed). Creates one `ORDERED`
 * order with that line, exactly as before; stock only changes when the delivery is received.
 */
export function NewPurchaseOrderDialog({
  open,
  onOpenChange,
  shopId,
  inventory,
  onCreated,
  onCloseAutoFocus,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  shopId: string
  inventory: ReadonlyArray<MockPart>
  onCreated: (po: MockPurchaseOrder) => void
  /** Where focus goes when the dialog closes (it is not opened by a `DialogTrigger`). */
  onCloseAutoFocus?: ComponentProps<typeof DialogContent>['onCloseAutoFocus']
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>New purchase order</DialogTitle>
          <DialogDescription>
            Restock a part from a supplier. Stock goes up when you receive the delivery.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while the dialog is open, so every order starts from the defaults. */}
        <NewPurchaseOrderForm shopId={shopId} inventory={inventory} onCreated={onCreated} />
      </DialogContent>
    </Dialog>
  )
}

function NewPurchaseOrderForm({
  shopId,
  inventory,
  onCreated,
}: {
  shopId: string
  inventory: ReadonlyArray<MockPart>
  onCreated: (po: MockPurchaseOrder) => void
}) {
  const id = useId()
  const fieldId = (field: keyof NewPoInput | 'part') => `${id}-${field}`
  const errorId = (field: keyof NewPoInput) => `${id}-${field}-error`

  const [supplier, setSupplier] = useState('Shell Lubricants Direct')
  const [partSku, setPartSku] = useState(inventory[0]?.sku || 'OIL-5W30-SYN')
  const [qty, setQty] = useState('10')
  // The unit cost starts at the chosen part's catalogue cost (spec 10 PP-04).
  const [price, setPrice] = useState(inventory[0] ? String(inventory[0].unit_price) : '6500')
  const [errors, setErrors] = useState<NewPoErrors>({})

  const part = inventory.find((p) => p.sku === partSku) || inventory[0]
  const live = validateNewPo({ supplier, quantity: qty, unitCost: price })
  const showTotal = !live.quantity && !live.unitCost

  const clearError = (field: keyof NewPoInput) =>
    setErrors((current) => (current[field] ? { ...current, [field]: undefined } : current))

  const choosePart = (sku: string) => {
    setPartSku(sku)
    const chosen = inventory.find((p) => p.sku === sku)
    if (chosen) {
      setPrice(String(chosen.unit_price))
      clearError('unitCost')
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const found = validateNewPo({ supplier, quantity: qty, unitCost: price })
    const firstInvalid = FIELD_ORDER.find((field) => found[field])
    setErrors(found)
    if (firstInvalid) {
      document.getElementById(fieldId(firstInvalid))?.focus()
      return
    }

    // The same order as before: one restock line, total = quantity × unit cost.
    const orderedPart = inventory.find((p) => p.sku === partSku) || inventory[0]
    const quantity = Number(qty) || 1
    const unitPrice = Number(price) || orderedPart?.unit_price || 3000

    const newPo: MockPurchaseOrder = {
      ...newPurchaseOrderIdentity(getPurchaseOrders()),
      shopId,
      supplier: supplier.trim(),
      created_at: new Date().toISOString(),
      status: 'ORDERED',
      items: [
        {
          part_sku: orderedPart?.sku || 'SKU-GEN',
          part_name: orderedPart?.name || 'General Component',
          quantity,
          unit_price: unitPrice,
        },
      ],
      total_amount: quantity * unitPrice,
    }

    savePurchaseOrder(newPo)
    onCreated(newPo)
  }

  const describedBy = (field: keyof NewPoInput, description?: string) =>
    errors[field] ? errorId(field) : description

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-6">
      {inventory.length === 0 ? (
        <Alert variant="warning">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>No parts to order yet</AlertTitle>
          <AlertDescription>Add the part in Inventory first, then order it here.</AlertDescription>
        </Alert>
      ) : null}

      <FieldGroup>
        <Field data-invalid={errors.supplier ? true : undefined}>
          <FieldLabel htmlFor={fieldId('supplier')}>Supplier</FieldLabel>
          <Input
            id={fieldId('supplier')}
            value={supplier}
            onChange={(event) => {
              setSupplier(event.target.value)
              clearError('supplier')
            }}
            maxLength={120}
            autoComplete="organization"
            aria-invalid={errors.supplier ? true : undefined}
            aria-describedby={describedBy('supplier')}
          />
          {errors.supplier ? (
            <FieldError id={errorId('supplier')}>{errors.supplier}</FieldError>
          ) : null}
        </Field>

        <Field>
          <FieldLabel id={`${fieldId('part')}-label`} htmlFor={fieldId('part')}>
            Part
          </FieldLabel>
          <PartPicker
            id={fieldId('part')}
            labelId={`${fieldId('part')}-label`}
            parts={inventory}
            value={partSku}
            onChange={choosePart}
          />
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field data-invalid={errors.quantity ? true : undefined}>
            <FieldLabel htmlFor={fieldId('quantity')}>Quantity</FieldLabel>
            <Input
              id={fieldId('quantity')}
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_QUANTITY}
              step={1}
              value={qty}
              onChange={(event) => {
                setQty(event.target.value)
                clearError('quantity')
              }}
              aria-invalid={errors.quantity ? true : undefined}
              aria-describedby={describedBy('quantity')}
              className="tabular-nums"
            />
            {errors.quantity ? (
              <FieldError id={errorId('quantity')}>{errors.quantity}</FieldError>
            ) : null}
          </Field>

          <Field data-invalid={errors.unitCost ? true : undefined}>
            <FieldLabel htmlFor={fieldId('unitCost')}>Unit cost</FieldLabel>
            <InputGroup>
              <InputGroupAddon>
                <InputGroupText>Rs</InputGroupText>
              </InputGroupAddon>
              <InputGroupInput
                id={fieldId('unitCost')}
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={price}
                onChange={(event) => {
                  setPrice(event.target.value)
                  clearError('unitCost')
                }}
                aria-invalid={errors.unitCost ? true : undefined}
                aria-describedby={describedBy(
                  'unitCost',
                  part ? `${fieldId('unitCost')}-hint` : undefined,
                )}
                className="tabular-nums"
              />
            </InputGroup>
            {errors.unitCost ? (
              <FieldError id={errorId('unitCost')}>{errors.unitCost}</FieldError>
            ) : part ? (
              <FieldDescription id={`${fieldId('unitCost')}-hint`}>
                Catalogue cost {formatPKR(part.unit_price)}
              </FieldDescription>
            ) : null}
          </Field>
        </div>
      </FieldGroup>

      <div className="rounded-xl bg-layer p-4 text-sm">
        <div className="flex items-start justify-between gap-4 text-muted-foreground">
          <span className="min-w-0 truncate">{part ? part.name : 'No part chosen'}</span>
          <span className="shrink-0 tabular-nums">
            {showTotal ? `${formatCount(Number(qty))} × ${formatPKR(Number(price))}` : '—'}
          </span>
        </div>
        <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-border pt-3">
          <span className="text-base font-semibold text-foreground">Order total</span>
          <span className="text-xl font-bold text-foreground tabular-nums">
            {showTotal ? formatPKR(Number(qty) * Number(price)) : '—'}
          </span>
        </div>
      </div>

      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={inventory.length === 0}>
          <Plus aria-hidden="true" data-icon="inline-start" />
          Create purchase order
        </Button>
      </DialogFooter>
    </form>
  )
}
