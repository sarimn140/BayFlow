import { formatDateTime } from '@/lib/format'
import type { MockBooking, MockEstimateItem, MockPart } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/**
 * PP-01 Parts queue and PP-02 Parts job (spec 10). While the screens run on mock data, a job's
 * required parts are the PART lines of its estimate, matched to the shop's inventory by name and
 * compared with the stock on hand. The live screens read the same figures from E-40
 * (`BookingPartsRead`) and E-33 (`parts_summary`).
 */

/** The SKU a required part gets when no inventory part matches it; it is ordered under it. */
export const UNMATCHED_SKU = 'PRT-GEN'

/** One required part of the approved estimate, compared with stock (a PP-02 table row). */
export interface PartRequirement {
  /** The estimate line's id. */
  id: string
  /** The estimate line's description. */
  description: string
  /** The matching inventory part's SKU, or `UNMATCHED_SKU`. */
  sku: string
  /** Whether a part of the shop's inventory matched the line. */
  inInventory: boolean
  /** The estimate line's unit price, used as the purchase order's unit cost. */
  unitCost: number
  required: number
  /** On hand for the matched part; 0 when nothing matched. */
  onHand: number
  /** What stock can't cover: max(0, required − on hand). */
  shortage: number
}

/** The estimate's PART lines against the inventory: a part matches when either name contains the other. */
export function partRequirements(
  estimateItems: ReadonlyArray<MockEstimateItem>,
  inventory: ReadonlyArray<MockPart>,
): PartRequirement[] {
  return estimateItems
    .filter((item) => item.type === 'PART')
    .map((item) => {
      const match = inventory.find(
        (p) =>
          p.name.toLowerCase().includes(item.description.toLowerCase()) ||
          item.description.toLowerCase().includes(p.name.toLowerCase()),
      )
      const onHand = match ? match.on_hand : 0
      const required = item.quantity
      return {
        id: item.id,
        description: item.description,
        sku: match ? match.sku : UNMATCHED_SKU,
        inInventory: Boolean(match),
        unitCost: item.unit_price,
        required,
        onHand,
        shortage: Math.max(0, required - onHand),
      }
    })
}

/** E-33 `parts_summary`: how many of the job's parts stock covers. */
export interface PartsSummary {
  /** Part lines on the estimate. */
  requiredCount: number
  /** Lines that stock on hand covers. */
  availableCount: number
  /** Lines short of stock, in estimate order. */
  short: PartRequirement[]
  /** Nothing is short; also true for a labour-only job (D31). */
  allAvailable: boolean
}

export function partsSummary(rows: ReadonlyArray<PartRequirement>): PartsSummary {
  const short = rows.filter((row) => row.shortage > 0)
  return {
    requiredCount: rows.length,
    availableCount: rows.length - short.length,
    short,
    allAvailable: short.length === 0,
  }
}

/** The share of the job's parts that stock covers, 0–100 (100 when there are none). */
export function availablePercent(summary: PartsSummary): number {
  if (summary.requiredCount === 0) return 100
  return Math.round((summary.availableCount / summary.requiredCount) * 100)
}

/** "1 part", "3 parts". */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

/** "a, b and c". */
export function listOf(items: ReadonlyArray<string>): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/** "2 of 3 parts in stock" (spec 10 PP-01 progress label). */
export function availabilityLabel(summary: PartsSummary): string {
  if (summary.requiredCount === 0) return 'No parts on the estimate'
  return `${summary.availableCount} of ${plural(summary.requiredCount, 'part')} in stock`
}

/** "Ignition coil × 1, Brake rotors × 2": what is short and by how much. */
export function shortList(short: ReadonlyArray<PartRequirement>): string {
  return short.map((row) => `${row.description} × ${row.shortage}`).join(', ')
}

/** A purchase order's total for the short parts: shortage × unit cost, summed. */
export function orderTotal(short: ReadonlyArray<PartRequirement>): number {
  return short.reduce((sum, row) => sum + row.shortage * row.unitCost, 0)
}

/** The queue's three stages, in workflow order (spec 10 PP-01). */
export const QUEUE_STAGES = [
  'PARTS_PENDING',
  'PARTS_ORDERED',
  'PARTS_READY',
] as const satisfies ReadonlyArray<BookingStatus>

export type QueueStage = (typeof QUEUE_STAGES)[number]

export function isQueueStage(status: BookingStatus): status is QueueStage {
  return (QUEUE_STAGES as ReadonlyArray<BookingStatus>).includes(status)
}

function timeOf(iso: string): number {
  const ms = Date.parse(iso)
  return Number.isNaN(ms) ? 0 : ms
}

/** Each stage's bookings, the longest wait first (`updatedAt` stands in for `status_changed_at`). */
export function queueByStage(
  bookings: ReadonlyArray<MockBooking>,
): Record<QueueStage, MockBooking[]> {
  const byStage: Record<QueueStage, MockBooking[]> = {
    PARTS_PENDING: [],
    PARTS_ORDERED: [],
    PARTS_READY: [],
  }
  for (const booking of bookings) {
    if (isQueueStage(booking.status)) byStage[booking.status].push(booking)
  }
  for (const stage of QUEUE_STAGES) {
    byStage[stage].sort(
      (a, b) => timeOf(a.updatedAt) - timeOf(b.updatedAt) || a.reference.localeCompare(b.reference),
    )
  }
  return byStage
}

/**
 * The page description: "3 jobs waiting for parts: 2 to check and 1 ready to allocate.", or what
 * the queue is for while it is empty.
 */
export function queueSummary(counts: Record<QueueStage, number>): string {
  const total = QUEUE_STAGES.reduce((sum, stage) => sum + counts[stage], 0)
  if (total === 0) {
    return 'Check approved jobs against stock, order what is missing and hand the parts to technicians.'
  }
  const clauses = [
    counts.PARTS_PENDING > 0 ? `${counts.PARTS_PENDING} to check` : null,
    counts.PARTS_ORDERED > 0 ? `${counts.PARTS_ORDERED} on order` : null,
    counts.PARTS_READY > 0 ? `${counts.PARTS_READY} ready to allocate` : null,
  ].filter((clause): clause is string => clause !== null)
  return `${plural(total, 'job')} waiting for parts: ${listOf(clauses)}.`
}

/** "Waiting 3 hours" since the last status change; `null` when the timestamp is not a date. */
export function waitingFor(iso: string, now: Date): string | null {
  const since = Date.parse(iso)
  if (Number.isNaN(since)) return null
  const minutes = Math.floor((now.getTime() - since) / 60_000)
  if (minutes < 1) return 'Just arrived'
  if (minutes < 60) return `Waiting ${plural(minutes, 'minute')}`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Waiting ${plural(hours, 'hour')}`
  return `Waiting ${plural(Math.floor(hours / 24), 'day')}`
}

/** "Fri, 9 Oct 2026 · 10:30 am" in the shop's time zone; `null` for a bad date or zone. */
export function shopDateTime(iso: string, timeZone: string | undefined): string | null {
  try {
    return formatDateTime(iso, timeZone)
  } catch {
    return null
  }
}

/** Where a job stands for the parts person (spec 08: parts statuses, then allocation). */
export type JobStage = 'not-yet' | 'check' | 'ordered' | 'ready' | 'allocated' | 'cancelled'

/** Statuses after `allocate-parts`: the parts went to the technician. */
const AFTER_ALLOCATION: ReadonlySet<BookingStatus> = new Set<BookingStatus>([
  'IN_REPAIR',
  'QC_PENDING',
  'QC_IN_PROGRESS',
  'READY_FOR_PICKUP',
  'COMPLETED',
])

export function jobStage(status: BookingStatus): JobStage {
  if (status === 'PARTS_PENDING') return 'check'
  if (status === 'PARTS_ORDERED') return 'ordered'
  if (status === 'PARTS_READY') return 'ready'
  if (status === 'CANCELLED') return 'cancelled'
  return AFTER_ALLOCATION.has(status) ? 'allocated' : 'not-yet'
}

/** One part line's stock chip (spec 10 PP-02 state chip). */
export type LineState = 'in-stock' | 'short' | 'on-order' | 'allocated'

export function lineState(row: Pick<PartRequirement, 'shortage'>, stage: JobStage): LineState {
  if (stage === 'allocated') return 'allocated'
  if (row.shortage === 0) return 'in-stock'
  return stage === 'ordered' ? 'on-order' : 'short'
}

/** A queue row's stock chip: the whole job at a glance. */
export type JobHealth = 'no-parts' | 'in-stock' | 'short' | 'on-order'

export function jobHealth(summary: PartsSummary, status: BookingStatus): JobHealth {
  if (summary.requiredCount === 0) return 'no-parts'
  if (summary.allAvailable) return 'in-stock'
  return status === 'PARTS_ORDERED' ? 'on-order' : 'short'
}

/** "2022 Honda Civic Oriel". */
export function vehicleLabel(
  booking: Pick<MockBooking, 'vehicleYear' | 'vehicleMake' | 'vehicleModel'>,
): string {
  return [booking.vehicleYear, booking.vehicleMake, booking.vehicleModel].filter(Boolean).join(' ')
}
