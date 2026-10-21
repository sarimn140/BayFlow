import { DEFAULT_SHOP_TZ, formatDate, formatRelative, formatTime, shopDateKey } from '@/lib/format'
import { bookingHistory } from '@/lib/mock-booking-history'
import type { CurrentUserSession, MockBooking, MockTeamMember } from '@/lib/mock-data'
import type { BookingStatus } from '@/lib/status'

/**
 * QC queue (QI-01) and inspection (QI-02, spec 10): the D46 checklist and the rules both screens
 * share, worked out from the mock store the way the QC endpoints will answer (E-33 queue order,
 * E-37 `pass-qc` / `fail-qc` validation).
 */

/** D46 default checklist in the API's fixed order (E-42; keys are glossary §5 `QcChecklistKey`). */
export const QC_CHECKLIST = [
  {
    key: 'road_test',
    label: 'Road test',
    hint: 'Drive the car: brakes, steering and suspension feel right, with no new noise or vibration.',
  },
  {
    key: 'no_warning_lights',
    label: 'No warning lights',
    hint: 'With the engine running, the dashboard shows no check-engine, ABS, airbag or other warning light.',
  },
  {
    key: 'no_leaks',
    label: 'No leaks',
    hint: 'No oil, coolant, brake fluid or fuel under the car or around the parts that were worked on.',
  },
  {
    key: 'fluid_levels',
    label: 'Fluid levels OK',
    hint: 'Engine oil, coolant, brake and washer fluid sit between their minimum and maximum marks.',
  },
  {
    key: 'complaint_resolved',
    label: 'Customer complaint resolved',
    hint: 'What the customer booked the car in for is fixed.',
  },
] as const

export type QcChecklistKey = (typeof QC_CHECKLIST)[number]['key']
export type QcAnswer = 'pass' | 'fail'
export type QcAnswers = Partial<Record<QcChecklistKey, QcAnswer>>
export type QcItemNotes = Partial<Record<QcChecklistKey, string>>

/** Field limits of `pass-qc` / `fail-qc` (spec 03 `QcChecklistItemWrite`, spec 10 QI-02). */
export const ITEM_NOTE_MAX = 500
export const NOTES_MAX = 2000
export const ISSUE_TITLE_MAX = 120
export const ISSUE_DESCRIPTION_MAX = 2000

/**
 * The QC inspector a pick is recorded for when the signed-in user is not on the shop's team: the
 * mock's demo inspector, whom every pick was recorded for before picks used the signed-in user.
 */
export const FALLBACK_INSPECTOR_ID = 'usr-sara'

export type QcResult = 'passed' | 'failed'

const timeOf = (iso: string): number => {
  const time = Date.parse(iso)
  return Number.isNaN(time) ? 0 : time
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`
}

/** The booking belongs to this shop (D20: anything else reads as "not found"). */
export function inShop(booking: Pick<MockBooking, 'shopId' | 'shopSlug'>, shopId: string): boolean {
  return booking.shopId === shopId || booking.shopSlug === shopId
}

/** QC can act on the booking: waiting for an inspector or being inspected. */
export function isInQc(status: BookingStatus): boolean {
  return status === 'QC_PENDING' || status === 'QC_IN_PROGRESS'
}

/** The latest QC result that still stands: passed (ready or collected) or failed (back in repair). */
export function qcResultOf(booking: Pick<MockBooking, 'status' | 'qcPassed'>): QcResult | null {
  if (booking.status === 'READY_FOR_PICKUP' || booking.status === 'COMPLETED') return 'passed'
  if (booking.status === 'IN_REPAIR' && booking.qcPassed === false) return 'failed'
  return null
}

/** Back in QC after a failed round ("Re-test" in spec 10 QI-01). */
export function isRetest(booking: Pick<MockBooking, 'status' | 'qcPassed'>): boolean {
  return isInQc(booking.status) && booking.qcPassed === false
}

/** QI-01 "Waiting": `QC_PENDING`, oldest first (E-33 `sort=status_changed_at`). */
export function waitingJobs(bookings: ReadonlyArray<MockBooking>): MockBooking[] {
  return bookings
    .filter((b) => b.status === 'QC_PENDING')
    .sort((a, b) => timeOf(a.updatedAt) - timeOf(b.updatedAt))
}

/** QI-01 "In progress": `QC_IN_PROGRESS`, the viewer's own first, then oldest first. */
export function inProgressJobs(
  bookings: ReadonlyArray<MockBooking>,
  myId: string | undefined,
): MockBooking[] {
  const mine = (b: MockBooking) => (myId !== undefined && b.qcInspectorId === myId ? 1 : 0)
  return bookings
    .filter((b) => b.status === 'QC_IN_PROGRESS')
    .sort((a, b) => mine(b) - mine(a) || timeOf(a.updatedAt) - timeOf(b.updatedAt))
}

/** When the standing QC result was given: the pass (kept after collection) or the fail. */
export function inspectedAt(booking: MockBooking): string {
  if (booking.status === 'COMPLETED') {
    const passed = bookingHistory(booking).find((step) => step.status === 'READY_FOR_PICKUP')
    return passed?.at ?? booking.updatedAt
  }
  return booking.updatedAt
}

/**
 * "2 days ago" since the standing QC result, "just now" within the minute (`now` is rounded up
 * to the minute, so a second-precise "54 seconds ago" would be wrong), '' for a bad date.
 */
export function inspectedAgo(booking: MockBooking, now: Date): string {
  const at = Date.parse(inspectedAt(booking))
  if (Number.isNaN(at)) return ''
  if (Math.abs(now.getTime() - at) < 60_000) return 'just now'
  return formatRelative(new Date(at), now)
}

/**
 * Another inspector picked this job (spec 10 QI-02: pass and fail are for the picker only). A job
 * in progress with no picker recorded stays open to any inspector.
 */
export function pickedByOther(
  booking: Pick<MockBooking, 'status' | 'qcInspectorId'>,
  myId: string | undefined,
): boolean {
  return (
    booking.status === 'QC_IN_PROGRESS' &&
    booking.qcInspectorId !== undefined &&
    booking.qcInspectorId !== myId
  )
}

/** QI-01 "Recently inspected": jobs whose QC result stands, newest result first. */
export function recentlyInspected(bookings: ReadonlyArray<MockBooking>, limit = 5): MockBooking[] {
  return bookings
    .filter((b) => qcResultOf(b) !== null)
    .sort((a, b) => timeOf(inspectedAt(b)) - timeOf(inspectedAt(a)))
    .slice(0, limit)
}

/** The signed-in user's team member id in this shop, matched by e-mail. */
export function memberIdFor(
  user: Pick<CurrentUserSession, 'email'>,
  team: ReadonlyArray<MockTeamMember>,
): string | undefined {
  const email = user.email.trim().toLowerCase()
  if (!email) return undefined
  return team.find((member) => member.email.trim().toLowerCase() === email)?.id
}

export function memberName(
  id: string | undefined,
  team: ReadonlyArray<MockTeamMember>,
): string | null {
  if (!id) return null
  return team.find((member) => member.id === id)?.name ?? null
}

export function vehicleName(
  booking: Pick<MockBooking, 'vehicleYear' | 'vehicleMake' | 'vehicleModel'>,
): string {
  return `${booking.vehicleYear} ${booking.vehicleMake} ${booking.vehicleModel}`
}

/** A valid IANA zone for the shop, else the default (Asia/Karachi). */
export function shopTimeZone(timeZone: string | undefined): string {
  if (!timeZone) return DEFAULT_SHOP_TZ
  try {
    new Intl.DateTimeFormat('en', { timeZone })
    return timeZone
  } catch {
    return DEFAULT_SHOP_TZ
  }
}

/** How long since `iso`: "under a minute", "25 min", "3 h 10 min", "2 days" ('' for a bad date). */
export function waitedFor(iso: string, now: Date): string {
  const start = Date.parse(iso)
  if (Number.isNaN(start)) return ''
  const minutes = Math.max(0, Math.floor((now.getTime() - start) / 60_000))
  if (minutes < 1) return 'under a minute'
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    const rest = minutes % 60
    return rest > 0 ? `${hours} h ${rest} min` : `${hours} h`
  }
  return plural(Math.floor(hours / 24), 'day')
}

/** "11:40 am" today in the shop, else "Thu, 8 Oct 2026 at 11:40 am" ('' for a bad date). */
export function sinceLabel(iso: string, now: Date, timeZone: string): string {
  try {
    const time = formatTime(iso, timeZone)
    return shopDateKey(iso, timeZone) === shopDateKey(now, timeZone)
      ? time
      : `${formatDate(iso, timeZone)} at ${time}`
  } catch {
    return ''
  }
}

export interface ChecklistProgress {
  total: number
  answered: number
  failed: number
}

export function checklistProgress(answers: QcAnswers): ChecklistProgress {
  const values = QC_CHECKLIST.map((item) => answers[item.key])
  return {
    total: QC_CHECKLIST.length,
    answered: values.filter((value) => value !== undefined).length,
    failed: values.filter((value) => value === 'fail').length,
  }
}

/**
 * Why "Pass QC" cannot go ahead (spec 10 QI-02, D46): a check is not answered yet (the API's
 * `checklist_incomplete`) or a check failed (`checklist_item_failed`, "use Fail QC").
 */
export function passBlocker(answers: QcAnswers): 'incomplete' | 'failed' | null {
  const { total, answered, failed } = checklistProgress(answers)
  if (answered < total) return 'incomplete'
  if (failed > 0) return 'failed'
  return null
}

export function failedChecks(answers: QcAnswers) {
  return QC_CHECKLIST.filter((item) => answers[item.key] === 'fail')
}

/** The fail dialog's issue title, prefilled from the failed checks ("Failed: No leaks"). */
export function issueTitleFrom(answers: QcAnswers): string {
  const failed = failedChecks(answers)
  if (failed.length === 0) return ''
  const title = `Failed: ${failed.map((item) => item.label).join(', ')}`
  return title.length <= ISSUE_TITLE_MAX ? title : `${title.slice(0, ISSUE_TITLE_MAX - 1)}…`
}

/** The fail dialog's description, prefilled from the failed checks' notes and the notes. */
export function issueDescriptionFrom(
  answers: QcAnswers,
  itemNotes: QcItemNotes,
  notes: string,
): string {
  const lines = failedChecks(answers).flatMap((item) => {
    const note = itemNotes[item.key]?.trim()
    return note ? [`${item.label}: ${note}`] : []
  })
  const general = notes.trim()
  if (general) lines.push(general)
  return lines.join('\n').slice(0, ISSUE_DESCRIPTION_MAX)
}

export interface IssueErrors {
  title?: string
  description?: string
}

/** `fail-qc` needs a reason (D46, D92): an issue title (1–120) and a description (1–2,000). */
export function validateIssue(title: string, description: string): IssueErrors {
  const errors: IssueErrors = {}
  const cleanTitle = title.trim()
  const cleanDescription = description.trim()
  if (!cleanTitle) errors.title = 'Enter a short title for the issue.'
  else if (cleanTitle.length > ISSUE_TITLE_MAX) {
    errors.title = `Keep the title to ${ISSUE_TITLE_MAX} characters.`
  }
  if (!cleanDescription) errors.description = 'Describe what the technician needs to fix.'
  else if (cleanDescription.length > ISSUE_DESCRIPTION_MAX) {
    errors.description = 'Keep the description to 2,000 characters.'
  }
  return errors
}

/** How a failed QC is written to `qcNotes` (unchanged from the first mock screens). */
const ISSUE_PREFIX = 'QC Issue: '
const ISSUE_SEPARATOR = ' — '

export function formatQcIssue(title: string, description: string): string {
  return `${ISSUE_PREFIX}${title}${ISSUE_SEPARATOR}${description}`
}

/** Reads a failed QC's issue back from `qcNotes` (`formatQcIssue`'s format). */
export function parseQcIssue(
  notes: string | undefined,
): { title: string; description: string } | null {
  const text = notes?.trim()
  if (!text) return null
  if (!text.startsWith(ISSUE_PREFIX)) return { title: text, description: '' }
  const body = text.slice(ISSUE_PREFIX.length)
  const split = body.indexOf(ISSUE_SEPARATOR)
  if (split < 0) return { title: body, description: '' }
  return {
    title: body.slice(0, split),
    description: body.slice(split + ISSUE_SEPARATOR.length),
  }
}

/** The inspection form kept per booking in `sessionStorage` while the inspector works (R9). */
export interface QcDraft {
  answers: QcAnswers
  itemNotes: QcItemNotes
  notes: string
}

export const EMPTY_DRAFT: QcDraft = { answers: {}, itemNotes: {}, notes: '' }

const draftKey = (bookingId: string) => `bf:qc-draft:${bookingId}`

/** A stored draft, keeping only known checklist keys and values of the right type. */
export function parseDraft(value: unknown): QcDraft {
  if (typeof value !== 'object' || value === null) return EMPTY_DRAFT
  const raw = value as Record<string, unknown>
  const answersIn =
    typeof raw.answers === 'object' && raw.answers !== null
      ? (raw.answers as Record<string, unknown>)
      : {}
  const notesIn =
    typeof raw.itemNotes === 'object' && raw.itemNotes !== null
      ? (raw.itemNotes as Record<string, unknown>)
      : {}
  const answers: QcAnswers = {}
  const itemNotes: QcItemNotes = {}
  for (const { key } of QC_CHECKLIST) {
    const answer = answersIn[key]
    if (answer === 'pass' || answer === 'fail') answers[key] = answer
    const note = notesIn[key]
    if (typeof note === 'string' && note) itemNotes[key] = note.slice(0, ITEM_NOTE_MAX)
  }
  const notes = typeof raw.notes === 'string' ? raw.notes.slice(0, NOTES_MAX) : ''
  return { answers, itemNotes, notes }
}

export function readDraft(bookingId: string): QcDraft {
  if (typeof window === 'undefined') return EMPTY_DRAFT
  try {
    const raw = window.sessionStorage.getItem(draftKey(bookingId))
    return raw ? parseDraft(JSON.parse(raw)) : EMPTY_DRAFT
  } catch {
    return EMPTY_DRAFT
  }
}

export function writeDraft(bookingId: string, draft: QcDraft): void {
  try {
    window.sessionStorage.setItem(draftKey(bookingId), JSON.stringify(draft))
  } catch {
    // Storage full or blocked: the form still works, it just isn't kept across visits.
  }
}

export function clearDraft(bookingId: string): void {
  try {
    window.sessionStorage.removeItem(draftKey(bookingId))
  } catch {
    // ignore
  }
}
