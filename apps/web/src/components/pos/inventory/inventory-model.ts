import { isLowStock } from '@/lib/kpis'
import type { CurrentUserSession, MockPart, MockPurchaseOrder } from '@/lib/mock-data'

/**
 * PP-03 Inventory (spec 10): the stock rules and the list's search and filters, kept apart from
 * the screen so they can be tested on their own.
 */

/**
 * D44: stock operations (opening stock, adjustments: `stock.manage`) belong to the Parts Person.
 * The Owner edits the parts catalogue only (`parts.manage`); the API answers 403 otherwise.
 */
export function canManageStock(role: CurrentUserSession['role']): boolean {
  return role === 'PARTS_PERSON'
}

/** D45 stock state, as the API's `stock_state`: `OUT` wins over `LOW`. */
export type StockState = 'OK' | 'LOW' | 'OUT'

/** The list's stock filter pills: All, Low stock (`LOW` only) and Out of stock (`OUT`). */
export type StockFilter = 'all' | 'low' | 'out'

/** Search boxes take at most 100 characters (spec 09 §2.10, `q`). */
export const SEARCH_MAX_LENGTH = 100

type StockFields = Pick<MockPart, 'on_hand' | 'reserved' | 'reorder_level'>

/** What is free to use: on hand minus what is reserved for jobs (D45). */
export function availableOf(part: Pick<MockPart, 'on_hand' | 'reserved'>): number {
  return part.on_hand - part.reserved
}

/**
 * `OUT` when nothing is available, `LOW` when what is available is at or below the reorder level
 * (`isLowStock`, the rule the overview and the owner summary count with), otherwise `OK`.
 */
export function stockState(part: StockFields): StockState {
  if (availableOf(part) <= 0) return 'OUT'
  return isLowStock(part) ? 'LOW' : 'OK'
}

export interface InventorySummary {
  partCount: number
  unitsOnHand: number
  /** On hand × unit cost, summed (the overview's "Stock value"). */
  stockValue: number
  /** `LOW` parts (something is available, but at or below the reorder level). */
  lowCount: number
  /** `OUT` parts (nothing available). */
  outCount: number
  /** Purchase orders still `ORDERED` or `PARTIALLY_RECEIVED`. */
  openOrders: number
}

export function inventorySummary(
  parts: ReadonlyArray<MockPart>,
  purchaseOrders: ReadonlyArray<MockPurchaseOrder>,
): InventorySummary {
  let unitsOnHand = 0
  let stockValue = 0
  let lowCount = 0
  let outCount = 0
  for (const part of parts) {
    unitsOnHand += part.on_hand
    stockValue += part.on_hand * part.unit_price
    const state = stockState(part)
    if (state === 'LOW') lowCount += 1
    if (state === 'OUT') outCount += 1
  }
  return {
    partCount: parts.length,
    unitsOnHand,
    stockValue,
    lowCount,
    outCount,
    openOrders: purchaseOrders.filter(
      (po) => po.status === 'ORDERED' || po.status === 'PARTIALLY_RECEIVED',
    ).length,
  }
}

/** Case-insensitive match on SKU, name or category; an empty query matches every part. */
export function matchesQuery(part: MockPart, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [part.sku, part.name, part.category].some((value) => value.toLowerCase().includes(q))
}

export function filterParts(
  parts: ReadonlyArray<MockPart>,
  filter: StockFilter,
  query: string,
): MockPart[] {
  return parts.filter((part) => {
    if (filter === 'low' && stockState(part) !== 'LOW') return false
    if (filter === 'out' && stockState(part) !== 'OUT') return false
    return matchesQuery(part, query)
  })
}

/** "1 part", "6 parts". */
export function countLabel(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString('en-PK')} ${count === 1 ? one : many}`
}

/** The categories in use, most used first (then A–Z), for the part form's suggestions. */
export function categoriesOf(parts: ReadonlyArray<MockPart>): string[] {
  const counts = new Map<string, number>()
  for (const part of parts) {
    const name = part.category.trim()
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort(([a, countA], [b, countB]) => countB - countA || a.localeCompare(b))
    .map(([name]) => name)
}

/**
 * Another part already using `sku`. Pass one shop's parts: a SKU is unique inside its shop
 * (`uq_parts_shop_id_sku`, spec 02), and other shops' catalogues are none of this shop's
 * business (D20). `exceptId` is the part being edited.
 */
export function skuTakenBy(
  parts: ReadonlyArray<MockPart>,
  sku: string,
  exceptId?: string,
): MockPart | undefined {
  const wanted = sku.trim().toUpperCase()
  return parts.find((part) => part.id !== exceptId && part.sku.toUpperCase() === wanted)
}

/**
 * The 409 `INSUFFICIENT_STOCK` rule of a stock adjustment (spec 10 PP-03, D82): the result may
 * not leave less on hand than is reserved for jobs, or go below zero.
 */
export function adjustmentError(
  part: Pick<MockPart, 'on_hand' | 'reserved'>,
  delta: number,
): string | null {
  const after = part.on_hand + delta
  if (after < 0 || after < part.reserved) {
    return 'That adjustment would leave less stock on hand than is reserved for jobs, or below zero.'
  }
  return null
}
