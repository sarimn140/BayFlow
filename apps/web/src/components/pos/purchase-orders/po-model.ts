import { isLowStock } from '@/lib/kpis'
import type { CurrentUserSession, MockBooking, MockPart, MockPurchaseOrder } from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

export type PoStatus = MockPurchaseOrder['status']
export type PoLine = MockPurchaseOrder['items'][number]

/** The job a purchase order was raised for, as the PO screens show it (PP-04, PP-05). */
export interface PoJob {
  bookingId: string
  /** "BF-2026-001" */
  reference: string
  /** "2022 Honda Civic Oriel" */
  vehicle: string
  /** Where the reference opens for the viewer (`jobHref`). */
  href: string
}

/**
 * Where a job opens for this role: the parts job (PP-02) for Parts staff; the booking (SA-02) for
 * the Owner, who acts on bookings there and only reads the parts screens (D16).
 */
export function jobHref(base: string, bookingId: string, role: CurrentUserSession['role']): string {
  const id = encodeURIComponent(bookingId)
  return sectionAccess(role, 'parts') !== 'manage' && sectionAccess(role, 'bookings') === 'manage'
    ? `${base}/bookings/${id}`
    : `${base}/parts/${id}`
}

/**
 * The job an order belongs to (`bookingId`, set by `order-parts` on PP-02, D43), looked up in this
 * shop's bookings only (D20). Undefined for a general restock, or a booking the shop doesn't have.
 */
export function poJob(
  po: Pick<MockPurchaseOrder, 'bookingId'>,
  bookings: ReadonlyArray<MockBooking>,
  base: string,
  role: CurrentUserSession['role'],
): PoJob | undefined {
  if (!po.bookingId) return undefined
  const booking = bookings.find((b) => b.id === po.bookingId)
  if (!booking) return undefined
  return {
    bookingId: booking.id,
    reference: booking.reference,
    vehicle: [booking.vehicleYear, booking.vehicleMake, booking.vehicleModel]
      .filter(Boolean)
      .join(' '),
    href: jobHref(base, booking.id, role),
  }
}

/** The list's status filter (spec 10 PP-04): open orders by default, then received, then all. */
export type PoFilter = 'open' | 'received' | 'all'

export const PO_FILTERS: ReadonlyArray<{ value: PoFilter; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'received', label: 'Received' },
  { value: 'all', label: 'All' },
]

const COUNT = new Intl.NumberFormat('en-PK')

/** A quantity with thousands separators, like the money beside it: 1730 → "1,730". */
export function formatCount(count: number): string {
  return COUNT.format(count)
}

/** "1 part", "21 units", "1,730 units". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`
}

/** Still waiting for (some of) its delivery: `ORDERED` or `PARTIALLY_RECEIVED`. */
export function isOpen(po: Pick<MockPurchaseOrder, 'status'>): boolean {
  return po.status === 'ORDERED' || po.status === 'PARTIALLY_RECEIVED'
}

/** Quantity × unit cost, as the order total adds it up. */
export function lineTotal(line: Pick<PoLine, 'quantity' | 'unit_price'>): number {
  return line.quantity * line.unit_price
}

/** Every unit on the order, across its lines. */
export function unitCount(po: Pick<MockPurchaseOrder, 'items'>): number {
  return po.items.reduce((sum, line) => sum + line.quantity, 0)
}

/**
 * The purchase order a job waits on (PP-01 "On order"): its newest open order, else its newest
 * received one; undefined when no order names the job (`bookingId`, D43).
 */
export function orderForJob<
  T extends Pick<MockPurchaseOrder, 'bookingId' | 'status' | 'created_at'>,
>(bookingId: string, orders: ReadonlyArray<T>): T | undefined {
  const linked = sortForList(orders.filter((po) => po.bookingId === bookingId))
  return linked[0]
}

/** "2 parts · 21 units". */
export function contentsLabel(po: Pick<MockPurchaseOrder, 'items'>): string {
  return `${plural(po.items.length, 'part')} · ${plural(unitCount(po), 'unit')}`
}

export function matchesFilter(po: Pick<MockPurchaseOrder, 'status'>, filter: PoFilter): boolean {
  if (filter === 'all') return true
  return filter === 'open' ? isOpen(po) : po.status === 'RECEIVED'
}

/** Case-insensitive match on the PO number, the supplier, and each line's part name or SKU. */
export function matchesQuery(
  po: Pick<MockPurchaseOrder, 'po_number' | 'supplier' | 'items'>,
  query: string,
): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return [
    po.po_number,
    po.supplier,
    ...po.items.flatMap((line) => [line.part_name, line.part_sku]),
  ].some((text) => text.toLowerCase().includes(needle))
}

/** Open orders first, then the newest (spec 03 E-48). */
export function sortForList<T extends Pick<MockPurchaseOrder, 'status' | 'created_at'>>(
  pos: ReadonlyArray<T>,
): T[] {
  return [...pos].sort(
    (a, b) =>
      Number(isOpen(b)) - Number(isOpen(a)) || Date.parse(b.created_at) - Date.parse(a.created_at),
  )
}

/** How many orders each filter shows. */
export function filterCounts(
  pos: ReadonlyArray<Pick<MockPurchaseOrder, 'status'>>,
): Record<PoFilter, number> {
  return {
    open: pos.filter(isOpen).length,
    received: pos.filter((po) => po.status === 'RECEIVED').length,
    all: pos.length,
  }
}

/** Available to use: on hand minus what is reserved for jobs (D45). */
export function availableStock(part: Pick<MockPart, 'on_hand' | 'reserved'>): number {
  return part.on_hand - part.reserved
}

export type StockState = 'ok' | 'low' | 'out'

/** D45: "out" when nothing is available, "low" at or under the reorder level. */
export function stockState(
  part: Pick<MockPart, 'on_hand' | 'reserved' | 'reorder_level'>,
): StockState {
  if (availableStock(part) <= 0) return 'out'
  return isLowStock(part) ? 'low' : 'ok'
}

export interface ReceiptLine {
  line: PoLine
  /** The inventory part receiving this line updates (matched on id or SKU); none for a free-text line. */
  part: MockPart | undefined
  /** On hand before and after this line is received; `null` when no part matches. */
  before: number | null
  after: number | null
}

/**
 * What receiving `po` does to stock, line by line, worked out exactly as the receive action applies
 * it: `adjustPartStock(line.part_sku, line.quantity, po.shopId)` for each line in order, on the
 * part whose id or SKU matches, never below 0. `parts` must be the order's shop's inventory
 * (`getInventory(shopId)`): a SKU names a part inside one shop only.
 */
export function receiptPreview(
  po: Pick<MockPurchaseOrder, 'items'>,
  parts: ReadonlyArray<MockPart>,
): ReceiptLine[] {
  const onHand = new Map<string, number>()
  return po.items.map((line) => {
    const part = parts.find((p) => p.id === line.part_sku || p.sku === line.part_sku)
    if (!part) return { line, part: undefined, before: null, after: null }
    const before = onHand.get(part.id) ?? part.on_hand
    const after = Math.max(0, before + line.quantity)
    onHand.set(part.id, after)
    return { line, part, before, after }
  })
}

/** Units that reach inventory on receipt: lines without a matching part change no stock. */
export function unitsAdded(preview: ReadonlyArray<Pick<ReceiptLine, 'line' | 'part'>>): number {
  return preview.reduce((sum, { line, part }) => sum + (part ? line.quantity : 0), 0)
}

/**
 * A fresh id and number for a new purchase order: `po-<ms>` and `PO-2026-<3 digits>` as before, but
 * never one already in use — `savePurchaseOrder` replaces the order with the same id or number, so
 * a repeated random number used to overwrite an earlier order. Impure (clock and random) on
 * purpose: only the create handler calls it.
 */
export function newPurchaseOrderIdentity(
  existing: ReadonlyArray<Pick<MockPurchaseOrder, 'id' | 'po_number'>>,
  now: number = Date.now(),
  random: () => number = Math.random,
): Pick<MockPurchaseOrder, 'id' | 'po_number'> {
  const ids = new Set(existing.map((po) => po.id))
  const numbers = new Set(existing.map((po) => po.po_number))

  let id = `po-${now}`
  for (let n = 2; ids.has(id); n += 1) id = `po-${now}-${n}`

  const start = Math.floor(random() * 900)
  for (let i = 0; i < 900; i += 1) {
    const candidate = `PO-2026-${100 + ((start + i) % 900)}`
    if (!numbers.has(candidate)) return { id, po_number: candidate }
  }
  let next = 1000
  while (numbers.has(`PO-2026-${next}`)) next += 1
  return { id, po_number: `PO-2026-${next}` }
}

export const MAX_QUANTITY = 10_000
export const MAX_UNIT_COST = 9_999_999_999

export interface NewPoInput {
  supplier: string
  quantity: string
  unitCost: string
}

export type NewPoErrors = Partial<Record<keyof NewPoInput, string>>

/** Digits only: no sign, decimal point or exponent. */
function wholeNumber(text: string): number | null {
  const trimmed = text.trim()
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null
}

/**
 * The new-order form's rules (spec 09 §2.10 "New purchase order"): a supplier, a whole quantity
 * from 1 to 10,000 and a unit cost in whole rupees. A cost of 0 is refused because the order would
 * silently fall back to the part's own cost.
 */
export function validateNewPo(input: NewPoInput): NewPoErrors {
  const errors: NewPoErrors = {}
  if (!input.supplier.trim()) errors.supplier = 'Enter the supplier’s name.'
  const quantity = wholeNumber(input.quantity)
  if (quantity === null || quantity < 1 || quantity > MAX_QUANTITY) {
    errors.quantity = 'Enter a whole number from 1 to 10,000.'
  }
  const unitCost = wholeNumber(input.unitCost)
  if (unitCost === null || unitCost < 1 || unitCost > MAX_UNIT_COST) {
    errors.unitCost = 'Enter the cost of one unit in whole rupees, Rs 1 or more.'
  }
  return errors
}
