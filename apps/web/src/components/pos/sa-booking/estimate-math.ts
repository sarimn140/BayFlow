import type { MockEstimateItem } from '@/lib/mock-data'

/**
 * Estimate arithmetic and the editor's line rules (spec 08 O1, spec 09 §4.5, D41): whole-rupee
 * prices, line total = quantity × unit price rounded half-up to whole rupees, computed in
 * integers (quantity in hundredths).
 */

export const MAX_LINES = 50
export const MAX_DESCRIPTION = 200
export const MAX_PART_QUANTITY = 10_000
export const MAX_UNIT_PRICE = 10_000_000

export function lineTotal(quantity: number, unitPrice: number): number {
  const hundredths = Math.round(quantity * 100)
  return Math.floor((hundredths * unitPrice + 50) / 100)
}

export interface EstimateTotals {
  parts: number
  labour: number
  total: number
}

export function estimateTotals(
  items: ReadonlyArray<Pick<MockEstimateItem, 'type' | 'total'>>,
): EstimateTotals {
  let parts = 0
  let labour = 0
  for (const item of items) {
    if (item.type === 'PART') parts += item.total
    else labour += item.total
  }
  return { parts, labour, total: parts + labour }
}

/** One editable line: the inputs keep what was typed until the estimate is saved. */
export interface DraftLine {
  key: string
  /** The saved line's id; new lines get one on save. */
  id?: string
  type: MockEstimateItem['type']
  description: string
  quantity: string
  unitPrice: string
}

export interface LineErrors {
  description?: string
  quantity?: string
  unitPrice?: string
}

export function toDraftLines(items: ReadonlyArray<MockEstimateItem>): DraftLine[] {
  return items.map((item) => ({
    key: item.id,
    id: item.id,
    type: item.type,
    description: item.description,
    quantity: String(item.quantity),
    unitPrice: String(item.unit_price),
  }))
}

const WHOLE = /^\d+$/
const HOURS = /^\d{1,3}(\.\d{1,2})?$/

/** "Rs 3,500", "3,500" and " 3500 " all read as 3500. */
function parseRupees(value: string): number | null {
  const cleaned = value.replace(/^\s*rs\.?\s*/i, '').replace(/[,\s]/g, '')
  return WHOLE.test(cleaned) ? Number(cleaned) : null
}

export function parseQuantity(type: DraftLine['type'], value: string): number | null {
  const cleaned = value.trim()
  if (type === 'PART') {
    if (!WHOLE.test(cleaned)) return null
    const quantity = Number(cleaned)
    return quantity >= 1 && quantity <= MAX_PART_QUANTITY ? quantity : null
  }
  if (!HOURS.test(cleaned)) return null
  const quantity = Number(cleaned)
  return quantity >= 0.01 && quantity <= 999.99 ? quantity : null
}

export function parseUnitPrice(value: string): number | null {
  const price = parseRupees(value)
  return price !== null && price <= MAX_UNIT_PRICE ? price : null
}

/** The line total while typing, or `null` until both numbers are valid. */
export function draftLineTotal(line: DraftLine): number | null {
  const quantity = parseQuantity(line.type, line.quantity)
  const price = parseUnitPrice(line.unitPrice)
  return quantity === null || price === null ? null : lineTotal(quantity, price)
}

export type DraftResult =
  | { ok: true; items: MockEstimateItem[] }
  | { ok: false; formError?: string; errors: Record<string, LineErrors> }

/**
 * Checks every line (spec 08 O1: 1–50 lines; parts in whole numbers from 1; labour 0.01–999.99;
 * prices in whole rupees from 0) and builds the saved lines. `newId` names lines added in the
 * editor.
 */
export function validateDraft(
  lines: ReadonlyArray<DraftLine>,
  newId: (index: number) => string,
): DraftResult {
  if (lines.length === 0) {
    return { ok: false, formError: 'Add at least one part or labour line first.', errors: {} }
  }
  if (lines.length > MAX_LINES) {
    return {
      ok: false,
      formError: `An estimate can have at most ${MAX_LINES} lines.`,
      errors: {},
    }
  }
  const errors: Record<string, LineErrors> = {}
  const items: MockEstimateItem[] = []
  lines.forEach((line, index) => {
    const lineErrors: LineErrors = {}
    const description = line.description.trim()
    if (!description) lineErrors.description = 'Describe the work.'
    else if (description.length > MAX_DESCRIPTION)
      lineErrors.description = `Use at most ${MAX_DESCRIPTION} characters.`
    const quantity = parseQuantity(line.type, line.quantity)
    if (quantity === null) {
      lineErrors.quantity =
        line.type === 'PART'
          ? `Enter a whole number from 1 to ${MAX_PART_QUANTITY.toLocaleString('en-PK')}.`
          : 'Enter 0.01 to 999.99, with up to two decimals.'
    }
    const unitPrice = parseUnitPrice(line.unitPrice)
    if (unitPrice === null) lineErrors.unitPrice = 'Enter whole rupees, 0 or more.'
    if (Object.keys(lineErrors).length > 0 || quantity === null || unitPrice === null) {
      errors[line.key] = lineErrors
      return
    }
    items.push({
      id: line.id ?? newId(index),
      description,
      type: line.type,
      quantity,
      unit_price: unitPrice,
      total: lineTotal(quantity, unitPrice),
    })
  })
  if (Object.keys(errors).length > 0) return { ok: false, errors }
  return { ok: true, items }
}

/** True when the saved lines would equal `items` (same order, text and numbers). */
export function sameItems(
  a: ReadonlyArray<MockEstimateItem>,
  b: ReadonlyArray<MockEstimateItem>,
): boolean {
  return (
    a.length === b.length &&
    a.every((item, index) => {
      const other = b[index]
      return (
        other !== undefined &&
        item.id === other.id &&
        item.description === other.description &&
        item.type === other.type &&
        item.quantity === other.quantity &&
        item.unit_price === other.unit_price &&
        item.total === other.total
      )
    })
  )
}
