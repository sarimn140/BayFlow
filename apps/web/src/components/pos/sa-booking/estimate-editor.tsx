'use client'

import { CircleAlert, Plus, Trash2 } from 'lucide-react'
import { useId, useRef, useState, type FormEvent, type RefObject } from 'react'

import { Alert, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { formatPKR } from '@/lib/format'
import type { MockBooking, MockEstimateItem, MockPart } from '@/lib/mock-data'

import { ActionErrorAlert, type ActionError } from './action-dialogs'
import {
  draftLineTotal,
  estimateTotals,
  MAX_DESCRIPTION,
  MAX_LINES,
  toDraftLines,
  validateDraft,
  type DraftLine,
  type LineErrors,
} from './estimate-math'

/** The inventory part a line refers to: the parts screen matches by name the same way (PP-02). */
function matchPart(inventory: ReadonlyArray<MockPart>, description: string): MockPart | undefined {
  const wanted = description.toLowerCase()
  return inventory.find((part) => {
    const name = part.name.toLowerCase()
    return name.includes(wanted) || wanted.includes(name)
  })
}

const available = (part: MockPart) => Math.max(0, part.on_hand - part.reserved)

/** Live availability for a part line (spec 09 §4.5): in stock, short or out of stock. */
function StockHint({ part, needed }: { part: MockPart; needed: number }) {
  const free = available(part)
  if (free <= 0) return <Badge variant="destructive">Out of stock, will be ordered</Badge>
  if (free < needed) return <Badge variant="warning">Only {free} in stock</Badge>
  return <Badge variant="success">{free} in stock</Badge>
}

export interface EstimateEditorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  booking: MockBooking
  version: number
  saDraftOpen: boolean
  technician?: string
  inventory: ReadonlyArray<MockPart>
  /** Saves the lines; returns an error to show, or `null` once saved (the page closes it). */
  onSave: (items: MockEstimateItem[]) => ActionError | null
  onCloseAutoFocus?: (event: Event) => void
}

/**
 * `edit-estimate` for the SA in `ESTIMATE_REVIEW` (spec 08 O1, spec 09 §4.5 `EstimateEditor`):
 * change quantities and prices, remove lines, add labour or a part from stock. The first save
 * creates a new version (D39). Clicking outside never discards the edits; Cancel and Esc do.
 */
export function EstimateEditorSheet({
  open,
  onOpenChange,
  onCloseAutoFocus,
  ...props
}: EstimateEditorProps) {
  const titleRef = useRef<HTMLHeadingElement>(null)
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        // A wider form than the 448px default (DESIGN.md §6.10): the lines need the room.
        className="gap-0 data-[side=right]:sm:max-w-xl"
        // A long form: start at its title (WAI-ARIA dialog pattern), not on a line's Remove button.
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          titleRef.current?.focus()
        }}
        onInteractOutside={(event) => event.preventDefault()}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <EditorBody {...props} titleRef={titleRef} onCancel={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}

function EditorBody({
  booking,
  version,
  saDraftOpen,
  technician,
  inventory,
  onSave,
  onCancel,
  titleRef,
}: Omit<EstimateEditorProps, 'open' | 'onOpenChange' | 'onCloseAutoFocus'> & {
  onCancel: () => void
  titleRef: RefObject<HTMLHeadingElement | null>
}) {
  const id = useId()
  const added = useRef(0)
  const [lines, setLines] = useState<DraftLine[]>(() => toDraftLines(booking.estimateItems))
  const [errors, setErrors] = useState<Record<string, LineErrors>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<ActionError | null>(null)
  const [partPick, setPartPick] = useState('')

  const totals = estimateTotals(
    lines.map((line) => ({ type: line.type, total: draftLineTotal(line) ?? 0 })),
  )
  const pending = lines.some((line) => draftLineTotal(line) === null)
  const partQuantities = new Map<string, number>()
  for (const line of lines) {
    if (line.type !== 'PART') continue
    const part = matchPart(inventory, line.description)
    if (part) {
      const quantity = Number(line.quantity) || 0
      partQuantities.set(part.id, (partQuantities.get(part.id) ?? 0) + quantity)
    }
  }

  const fieldId = (line: DraftLine, field: keyof LineErrors) => `${id}-${line.key}-${field}`

  const change = (key: string, field: keyof LineErrors, value: string) => {
    setLines((current) =>
      current.map((line) => (line.key === key ? { ...line, [field]: value } : line)),
    )
    setErrors((current) => {
      const lineErrors = current[key]
      if (!lineErrors?.[field]) return current
      return { ...current, [key]: { ...lineErrors, [field]: undefined } }
    })
    setSaveError(null)
  }

  const append = (line: Omit<DraftLine, 'key'>, focusField: keyof LineErrors) => {
    added.current += 1
    const key = `new-${added.current}`
    setLines((current) => [...current, { ...line, key }])
    setFormError(null)
    requestAnimationFrame(() => document.getElementById(`${id}-${key}-${focusField}`)?.focus())
  }

  const addPart = (partId: string) => {
    const part = inventory.find((candidate) => candidate.id === partId)
    if (!part) return
    append(
      { type: 'PART', description: part.name, quantity: '1', unitPrice: String(part.unit_price) },
      'quantity',
    )
  }

  const remove = (key: string) => {
    setLines((current) => current.filter((line) => line.key !== key))
    setErrors((current) => {
      const next = { ...current }
      delete next[key]
      return next
    })
    // The button is gone: keep focus in the form, on the next way to add a line.
    requestAnimationFrame(() => document.getElementById(`${id}-add-labour`)?.focus())
  }

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const stamp = Date.now().toString(36)
    const result = validateDraft(lines, (index) => `est-${stamp}-${index}`)
    if (!result.ok) {
      setErrors(result.errors)
      setFormError(result.formError ?? 'Please check the highlighted fields.')
      requestAnimationFrame(() => form.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus())
      return
    }
    setErrors({})
    setFormError(null)
    setSaveError(onSave(result.items))
  }

  return (
    <form onSubmit={save} noValidate className="flex min-h-0 flex-1 flex-col">
      <SheetHeader className="border-b border-border-faint">
        <SheetTitle ref={titleRef} tabIndex={-1} className="outline-none">
          Edit estimate
        </SheetTitle>
        <SheetDescription>
          {saDraftOpen
            ? `Your draft v${version} for ${booking.reference}. Saving updates it.`
            : `${booking.reference} · v${version}${technician ? ` by ${technician}` : ''}. Saving creates v${version + 1}.`}{' '}
          Nothing goes to {booking.customerName} until you send it.
        </SheetDescription>
      </SheetHeader>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {formError ? (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>{formError}</AlertTitle>
          </Alert>
        ) : null}

        {lines.length > 0 ? (
          <ul className="space-y-3" aria-label="Estimate lines">
            {lines.map((line) => {
              const lineErrors = errors[line.key] ?? {}
              const total = draftLineTotal(line)
              const part = line.type === 'PART' ? matchPart(inventory, line.description) : undefined
              const name = line.description.trim() || 'new labour line'
              return (
                <li
                  key={line.key}
                  className="relative space-y-3 rounded-2xl border border-border bg-card p-4 shadow-xs"
                >
                  <div className="min-w-0 space-y-1.5 pr-10">
                    <Badge variant={line.type === 'PART' ? 'info' : 'neutral'}>
                      {line.type === 'PART' ? 'Part' : 'Labour'}
                    </Badge>
                    {line.type === 'PART' ? (
                      <p className="text-sm font-medium wrap-break-word text-foreground">
                        {line.description}
                      </p>
                    ) : null}
                  </div>

                  {line.type === 'LABOR' ? (
                    <Field data-invalid={Boolean(lineErrors.description)}>
                      <FieldLabel htmlFor={fieldId(line, 'description')}>Work</FieldLabel>
                      <Input
                        id={fieldId(line, 'description')}
                        value={line.description}
                        onChange={(event) => change(line.key, 'description', event.target.value)}
                        maxLength={MAX_DESCRIPTION}
                        placeholder="e.g. Replace ignition coil"
                        aria-invalid={Boolean(lineErrors.description)}
                        aria-describedby={
                          lineErrors.description
                            ? `${fieldId(line, 'description')}-error`
                            : undefined
                        }
                      />
                      {lineErrors.description ? (
                        <FieldError id={`${fieldId(line, 'description')}-error`}>
                          {lineErrors.description}
                        </FieldError>
                      ) : null}
                    </Field>
                  ) : null}

                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)_minmax(0,1fr)]">
                    <Field data-invalid={Boolean(lineErrors.quantity)}>
                      <FieldLabel htmlFor={fieldId(line, 'quantity')}>
                        Qty<span className="sr-only"> for {name}</span>
                      </FieldLabel>
                      <Input
                        id={fieldId(line, 'quantity')}
                        value={line.quantity}
                        onChange={(event) => change(line.key, 'quantity', event.target.value)}
                        inputMode={line.type === 'PART' ? 'numeric' : 'decimal'}
                        autoComplete="off"
                        className="tabular-nums"
                        aria-invalid={Boolean(lineErrors.quantity)}
                        aria-describedby={
                          lineErrors.quantity ? `${fieldId(line, 'quantity')}-error` : undefined
                        }
                      />
                      {lineErrors.quantity ? (
                        <FieldError id={`${fieldId(line, 'quantity')}-error`}>
                          {lineErrors.quantity}
                        </FieldError>
                      ) : null}
                    </Field>
                    <Field data-invalid={Boolean(lineErrors.unitPrice)}>
                      <FieldLabel htmlFor={fieldId(line, 'unitPrice')}>
                        Unit price<span className="sr-only"> for {name}, in rupees</span>
                      </FieldLabel>
                      <InputGroup>
                        <InputGroupAddon>Rs</InputGroupAddon>
                        <InputGroupInput
                          id={fieldId(line, 'unitPrice')}
                          value={line.unitPrice}
                          onChange={(event) => change(line.key, 'unitPrice', event.target.value)}
                          inputMode="numeric"
                          autoComplete="off"
                          className="tabular-nums"
                          aria-invalid={Boolean(lineErrors.unitPrice)}
                          aria-describedby={
                            lineErrors.unitPrice ? `${fieldId(line, 'unitPrice')}-error` : undefined
                          }
                        />
                      </InputGroup>
                      {lineErrors.unitPrice ? (
                        <FieldError id={`${fieldId(line, 'unitPrice')}-error`}>
                          {lineErrors.unitPrice}
                        </FieldError>
                      ) : null}
                    </Field>
                    <div className="col-span-2 flex items-baseline justify-between gap-2 sm:col-span-1 sm:flex-col sm:items-end sm:justify-start sm:gap-2">
                      <p className="text-sm font-medium text-foreground">Line total</p>
                      <p className="text-base font-semibold text-foreground tabular-nums sm:flex sm:h-10.5 sm:items-center">
                        {total === null ? '—' : formatPKR(total)}
                      </p>
                    </div>
                  </div>

                  {part ? (
                    <StockHint part={part} needed={partQuantities.get(part.id) ?? 0} />
                  ) : null}

                  {/* Drawn top-right, but last in the tab order: edit a line before removing it. */}
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute top-2.5 right-2.5 text-muted-foreground hover:text-danger-ink"
                    aria-label={`Remove ${name}`}
                    onClick={() => remove(line.key)}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="rounded-2xl border border-dashed border-border-medium px-4 py-6 text-center text-sm text-muted-foreground">
            No lines yet. Add labour or a part from stock.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            id={`${id}-add-labour`}
            type="button"
            variant="outline"
            disabled={lines.length >= MAX_LINES}
            onClick={() =>
              append(
                { type: 'LABOR', description: '', quantity: '1', unitPrice: '' },
                'description',
              )
            }
          >
            <Plus data-icon="inline-start" aria-hidden="true" />
            Add labour
          </Button>
          <Select
            value={partPick}
            onValueChange={(value) => {
              addPart(value)
              setPartPick('')
            }}
            disabled={lines.length >= MAX_LINES || inventory.length === 0}
          >
            <SelectTrigger aria-label="Add a part from stock" className="rounded-full">
              <Plus aria-hidden="true" />
              <SelectValue placeholder="Add a part" />
            </SelectTrigger>
            <SelectContent>
              {inventory.map((part) => (
                <SelectItem key={part.id} value={part.id}>
                  {part.name} · {formatPKR(part.unit_price)} · {available(part)} in stock
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {lines.length >= MAX_LINES ? (
          <p className="text-sm text-muted-foreground">
            An estimate can have at most {MAX_LINES} lines.
          </p>
        ) : null}

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
                {formatPKR(totals.total)}
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-helper">
            {pending
              ? 'Lines with a missing or invalid number count as Rs 0 until you fix them.'
              : 'Totals update as you type.'}
          </p>
        </div>

        {saveError ? <ActionErrorAlert error={saveError} /> : null}
      </div>

      <SheetFooter className="flex-row justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">Save estimate</Button>
      </SheetFooter>
    </form>
  )
}
