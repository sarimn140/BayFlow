import type { BookingHistoryStep } from '@/lib/mock-booking-history'
import { getStoredData, setStoredData } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/**
 * What SA-02 shows that `MockBooking` has no field for yet, kept in this browser like the rest of
 * the mock store: the estimate's version (D39), `ready_notified_at` (D27), who declined or
 * cancelled the booking and why (T03, T22), the Service Advisor's own events (estimate edits,
 * revisions, returns to the technician, pick-up notices) and the history before each estimate
 * loop. E-35, E-36 and E-38 replace it once the screen reads the API.
 */

export type SaActorRole = 'OWNER' | 'SERVICE_ADVISOR'

export interface SaActor {
  name: string
  role: SaActorRole
}

export interface SaActivity {
  id: string
  kind: 'estimate-edited' | 'estimate-revised' | 'returned-to-technician' | 'ready-notice'
  at: string
  by: string
  role: SaActorRole
  /** The estimate version the event created. */
  version?: number
  /** The note sent with a return to the technician (≤ 500 characters). */
  note?: string
}

/**
 * A declined estimate sent back round the loop (T10 revise → `ESTIMATE_REVIEW`, T11 return →
 * `INSPECTING`). The shared mock history only knows the happy path, so the steps up to the
 * decline are kept here as they were, and later steps are placed after `at`.
 */
export interface SaLoop {
  at: string
  reentry: 'ESTIMATE_REVIEW' | 'INSPECTING'
  steps: ReadonlyArray<BookingHistoryStep>
}

export interface SaCancellation {
  kind: 'decline' | 'cancel'
  reason: string
  at: string
  by: string
  role: SaActorRole
  /** The status it was cancelled from and its `updatedAt` then, to rebuild the history. */
  fromStatus: BookingStatus
  previousUpdatedAt: string
}

export interface SaBookingRecord {
  /** 1 is the technician's estimate; every SA draft (edit, revise) or return adds one (D39). */
  estimateVersion: number
  /** The open version is the SA's own draft, so further saves update it (spec 08 O1). */
  saDraftOpen: boolean
  activity: ReadonlyArray<SaActivity>
  cancellation?: SaCancellation
  loops?: ReadonlyArray<SaLoop>
}

const KEY = 'sa_booking_records'
const NO_RECORDS: Readonly<Record<string, SaBookingRecord>> = {}

export const EMPTY_SA_RECORD: SaBookingRecord = {
  estimateVersion: 1,
  saDraftOpen: false,
  activity: [],
}

function getSaRecords(): Readonly<Record<string, SaBookingRecord>> {
  return getStoredData(KEY, NO_RECORDS)
}

/** One booking's record: the stored object itself (or a constant), as `useMockStore` needs. */
export function getSaRecord(bookingId: string): SaBookingRecord {
  const record = getSaRecords()[bookingId]
  return record && typeof record.estimateVersion === 'number' && Array.isArray(record.activity)
    ? record
    : EMPTY_SA_RECORD
}

function updateRecord(bookingId: string, change: (record: SaBookingRecord) => SaBookingRecord) {
  const current = getSaRecord(bookingId)
  const next = change(current)
  if (next !== current) setStoredData(KEY, { ...getSaRecords(), [bookingId]: next })
  return next
}

function activity(
  kind: SaActivity['kind'],
  actor: SaActor,
  extra: Partial<Pick<SaActivity, 'version' | 'note'>> = {},
): SaActivity {
  const at = new Date().toISOString()
  return {
    id: `${kind}-${Date.parse(at).toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    kind,
    at,
    by: actor.name,
    role: actor.role,
    ...extra,
  }
}

/** O1: the SA's first save in a review creates a new version; later saves update that draft. */
export function recordEstimateEdit(bookingId: string, actor: SaActor): SaBookingRecord {
  return updateRecord(bookingId, (record) => {
    if (record.saDraftOpen) return record
    const version = record.estimateVersion + 1
    return {
      ...record,
      estimateVersion: version,
      saDraftOpen: true,
      activity: [...record.activity, activity('estimate-edited', actor, { version })],
    }
  })
}

/** T07: the open version is sent, so it is no longer an editable draft. */
export function recordEstimateSent(bookingId: string): SaBookingRecord {
  return updateRecord(bookingId, (record) =>
    record.saDraftOpen ? { ...record, saDraftOpen: false } : record,
  )
}

/**
 * T10: a new SA draft copied from the declined version. `history` is the booking's status history
 * up to the decline (`historySince`), kept for the activity timeline.
 */
export function recordEstimateRevised(
  bookingId: string,
  actor: SaActor,
  history: ReadonlyArray<BookingHistoryStep>,
): SaBookingRecord {
  return updateRecord(bookingId, (record) => {
    const version = record.estimateVersion + 1
    const event = activity('estimate-revised', actor, { version })
    return {
      ...record,
      estimateVersion: version,
      saDraftOpen: true,
      activity: [...record.activity, event],
      loops: [
        ...(record.loops ?? []),
        { at: event.at, reentry: 'ESTIMATE_REVIEW', steps: history },
      ],
    }
  })
}

/** T11: a new draft for the technician, with the SA's optional note (see `recordEstimateRevised`). */
export function recordReturnedToTechnician(
  bookingId: string,
  actor: SaActor,
  note: string,
  history: ReadonlyArray<BookingHistoryStep>,
): SaBookingRecord {
  return updateRecord(bookingId, (record) => {
    const version = record.estimateVersion + 1
    const event = activity('returned-to-technician', actor, { version, ...(note ? { note } : {}) })
    return {
      ...record,
      estimateVersion: version,
      saDraftOpen: false,
      activity: [...record.activity, event],
      loops: [...(record.loops ?? []), { at: event.at, reentry: 'INSPECTING', steps: history }],
    }
  })
}

/** O3: `ready_notified_at`; repeatable (D27). */
export function recordReadyNotice(bookingId: string, actor: SaActor): SaBookingRecord {
  return updateRecord(bookingId, (record) => ({
    ...record,
    activity: [...record.activity, activity('ready-notice', actor)],
  }))
}

/** T03 / T22: who declined or cancelled the booking, when, why, and from which status. */
export function recordCancellation(
  bookingId: string,
  actor: SaActor,
  details: Pick<SaCancellation, 'kind' | 'reason' | 'fromStatus' | 'previousUpdatedAt'>,
): SaBookingRecord {
  return updateRecord(bookingId, (record) => ({
    ...record,
    saDraftOpen: false,
    cancellation: { ...details, at: new Date().toISOString(), by: actor.name, role: actor.role },
  }))
}

/** The latest pick-up notice, if the customer has been told the car is ready. */
export function lastReadyNotice(record: SaBookingRecord): SaActivity | undefined {
  return record.activity.findLast((entry) => entry.kind === 'ready-notice')
}
