'use client'

import { Minus, Plus, Trash2 } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode, type Ref } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { formatPKR } from '@/lib/format'
import type { MockEstimateItem } from '@/lib/mock-data'

import { countLabel, type EstimateTotals as Totals } from './job-model'

type LineType = MockEstimateItem['type']

/** Estimate line types (DESIGN.md §6.4): Part = info chip, Labour = neutral chip. */
function LineType({ type }: { type: LineType }) {
  return type === 'PART' ? (
    <Badge variant="info">Part</Badge>
  ) : (
    <Badge variant="neutral">Labour</Badge>
  )
}

function RemoveButton({
  item,
  onRemove,
}: {
  item: MockEstimateItem
  onRemove: (item: MockEstimateItem) => void
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-lg"
      className="text-muted-foreground hover:bg-danger-subtle hover:text-danger-ink"
      aria-label={`Remove ${item.description}`}
      data-line-remove={item.id}
      onClick={() => onRemove(item)}
    >
      <Trash2 aria-hidden="true" />
    </Button>
  )
}

/**
 * The estimate's lines inside a flush card (the card is the `@container`): stacked rows while the
 * card is narrow (phones, tablets, the 1024px two-column layout), the data table once it is wide.
 * `onRemove` makes the lines removable (the technician's editor in `INSPECTING`).
 */
export function EstimateLines({
  items,
  onRemove,
}: {
  items: ReadonlyArray<MockEstimateItem>
  onRemove?: (item: MockEstimateItem) => void
}) {
  return (
    <>
      <ul className="divide-y divide-border-faint @2xl:hidden" aria-label="Estimate lines">
        {items.map((item) => (
          <li key={item.id} className="flex items-start gap-3 px-5 py-4 sm:px-6">
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-base leading-6 font-medium text-foreground">{item.description}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">
                <LineType type={item.type} />
                <span className="tabular-nums">
                  {item.quantity} × {formatPKR(item.unit_price)}
                </span>
              </div>
            </div>
            <p className="shrink-0 pt-0.5 text-base font-semibold text-foreground tabular-nums">
              {formatPKR(item.total)}
            </p>
            {onRemove ? (
              <div className="-my-1.5 -mr-2 shrink-0">
                <RemoveButton item={item} onRemove={onRemove} />
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      <div className="hidden @2xl:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Item</TableHead>
              <TableHead>Type</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Unit price</TableHead>
              <TableHead className="text-right">Total</TableHead>
              {onRemove ? (
                <TableHead className="w-0">
                  <span className="sr-only">Remove</span>
                </TableHead>
              ) : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="min-w-48 font-medium whitespace-normal">
                  {item.description}
                </TableCell>
                <TableCell>
                  <LineType type={item.type} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{item.quantity}</TableCell>
                <TableCell className="text-right text-muted-foreground tabular-nums">
                  {formatPKR(item.unit_price)}
                </TableCell>
                <TableCell className="text-right font-semibold tabular-nums">
                  {formatPKR(item.total)}
                </TableCell>
                {onRemove ? (
                  <TableCell className="py-1 pr-3 last:pr-3">
                    <RemoveButton item={item} onRemove={onRemove} />
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  )
}

/** The totals well under the lines (DESIGN.md §6.5): parts, labour and the total. */
export function EstimateTotalsWell({ totals }: { totals: Totals }) {
  return (
    <div className="space-y-2 rounded-xl bg-layer p-4 text-sm">
      {totals.partLines > 0 ? (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">
            Parts · {countLabel(totals.partLines, 'line', 'lines')}
          </span>
          <span className="font-medium text-foreground tabular-nums">
            {formatPKR(totals.parts)}
          </span>
        </div>
      ) : null}
      {totals.labourLines > 0 ? (
        <div className="flex justify-between gap-4">
          <span className="text-muted-foreground">
            Labour · {countLabel(totals.labourLines, 'line', 'lines')}
          </span>
          <span className="font-medium text-foreground tabular-nums">
            {formatPKR(totals.labour)}
          </span>
        </div>
      ) : null}
      <div className="flex items-baseline justify-between gap-4 border-t border-border pt-3">
        <span className="text-base font-semibold text-foreground">Total</span>
        <span className="text-xl font-bold text-foreground tabular-nums">
          {formatPKR(totals.total)}
        </span>
      </div>
    </div>
  )
}

export interface NewLine {
  description: string
  type: LineType
  quantity: string
  unitPrice: string
}

/**
 * "Add a line" (spec 10 T-02 editor; rows become cards on phones): type as two 48px toggles, a
 * description, a quantity stepper and a unit price in rupees. Starts as a 1 × Rs 2,500 part, as
 * before. An empty description is not added (same rule as before) and now says so.
 */
export function AddLineForm({
  onAdd,
  descriptionRef,
  notice,
}: {
  onAdd: (line: NewLine) => void
  /** The description field, so the page can focus it ("Add at least one … line first"). */
  descriptionRef?: Ref<HTMLInputElement>
  /** A message above the fields (the page's empty-estimate error). */
  notice?: ReactNode
}) {
  const id = useId()
  const [description, setDescription] = useState('')
  const [type, setType] = useState<LineType>('PART')
  const [quantity, setQuantity] = useState('1')
  const [unitPrice, setUnitPrice] = useState('2500')
  const [error, setError] = useState<string | null>(null)

  const step = (delta: number) =>
    setQuantity((current) => String(Math.max(1, (Number(current) || 1) + delta)))

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!description.trim()) {
      setError('Enter what the part or the labour is.')
      document.getElementById(`${id}-description`)?.focus()
      return
    }
    onAdd({ description, type, quantity, unitPrice })
    setDescription('')
    setError(null)
  }

  return (
    <form
      noValidate
      onSubmit={submit}
      aria-labelledby={`${id}-title`}
      className="@container space-y-5 border-t border-border-faint bg-muted px-5 py-5 sm:px-6 sm:py-6"
    >
      <div className="space-y-1">
        <h3 id={`${id}-title`} className="text-base leading-6 font-semibold text-foreground">
          Add a line
        </h3>
        <p className="text-sm text-muted-foreground">
          A part from the shelf or a labour operation. Totals update as you add lines.
        </p>
      </div>

      {notice}

      {/* One grid so the columns line up: type | description, then quantity | price | add. */}
      <div className="grid gap-5 @lg:grid-cols-[auto_minmax(0,1fr)] @xl:grid-cols-[auto_minmax(0,1fr)_auto]">
        <div className="flex flex-col gap-2">
          <span id={`${id}-type`} className="text-sm leading-5 font-medium text-foreground">
            Type
          </span>
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={type}
            onValueChange={(value) => {
              if (value === 'PART' || value === 'LABOR') setType(value)
            }}
            aria-labelledby={`${id}-type`}
            className="w-full"
          >
            <ToggleGroupItem value="PART" className="h-12 flex-1 px-5">
              Part
            </ToggleGroupItem>
            <ToggleGroupItem value="LABOR" className="h-12 flex-1 px-5">
              Labour
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        <Field data-invalid={error ? true : undefined} className="@xl:col-span-2">
          <FieldLabel htmlFor={`${id}-description`}>Description</FieldLabel>
          <Input
            id={`${id}-description`}
            ref={descriptionRef}
            value={description}
            onChange={(event) => {
              setDescription(event.target.value)
              if (error) setError(null)
            }}
            placeholder="For example, front brake pad set"
            autoComplete="off"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${id}-description-error` : undefined}
            className="h-12"
          />
          {error ? <FieldError id={`${id}-description-error`}>{error}</FieldError> : null}
        </Field>

        <div className="flex flex-col gap-2">
          <FieldLabel htmlFor={`${id}-quantity`}>Quantity</FieldLabel>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon-lg"
              aria-label="Decrease quantity"
              onClick={() => step(-1)}
            >
              <Minus aria-hidden="true" />
            </Button>
            <Input
              id={`${id}-quantity`}
              type="number"
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className="h-12 w-20 text-center tabular-nums"
            />
            <Button
              type="button"
              variant="outline"
              size="icon-lg"
              aria-label="Increase quantity"
              onClick={() => step(1)}
            >
              <Plus aria-hidden="true" />
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <FieldLabel htmlFor={`${id}-price`}>Unit price</FieldLabel>
          <InputGroup className="h-12">
            <InputGroupAddon>
              <InputGroupText>Rs</InputGroupText>
            </InputGroupAddon>
            <InputGroupInput
              id={`${id}-price`}
              type="number"
              inputMode="numeric"
              value={unitPrice}
              onChange={(event) => setUnitPrice(event.target.value)}
              className="tabular-nums"
            />
          </InputGroup>
        </div>

        <Button
          type="submit"
          size="lg"
          variant="outline"
          className="w-full @lg:col-span-2 @xl:col-span-1 @xl:w-auto @xl:self-end"
        >
          <Plus aria-hidden="true" data-icon="inline-start" />
          Add line
        </Button>
      </div>
    </form>
  )
}
