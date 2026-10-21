import type { MockService, MockShop } from '@/lib/mock-data'

/**
 * O-03 Services catalogue (spec 10): the rules of `ServiceCreate` / `ServiceUpdate` (spec 03,
 * spec 09 §2.10), so the form never accepts a value the API refuses, and the D34 / D64 booking
 * rules the screen explains.
 */

export const SERVICE_NAME_MAX = 120
export const SERVICE_DESCRIPTION_MAX = 1000
export const DURATION_MIN = 5
export const DURATION_MAX = 10_080
/** `Money` (spec 03 §1.5, D41): whole rupees, 0 to 9 999 999 999. */
export const PRICE_MAX = 9_999_999_999

export type ServiceFilter = 'all' | 'active' | 'inactive'

/** The create / edit form's values, as typed. */
export interface ServiceDraft {
  name: string
  description: string
  duration: string
  price: string
  isActive: boolean
}

export type ServiceField = 'name' | 'description' | 'duration' | 'price'
export type ServiceErrors = Partial<Record<ServiceField, string>>

/** Field order, for moving focus to the first error. */
export const SERVICE_FIELDS: ReadonlyArray<ServiceField> = [
  'name',
  'description',
  'duration',
  'price',
]

export const NEW_SERVICE_DRAFT: ServiceDraft = {
  name: '',
  description: '',
  duration: '60',
  price: '',
  isActive: true,
}

export function draftFromService(service: MockService): ServiceDraft {
  return {
    name: service.name,
    description: service.description,
    duration: String(service.estimated_duration_minutes),
    price: service.base_price === null ? '' : String(service.base_price),
    isActive: service.is_active,
  }
}

/** A whole number typed with optional thousands separators ("1,100" → 1100), else `null`. */
export function parseWholeNumber(raw: string): number | null {
  const compact = raw.replace(/[\s,]/g, '')
  if (!/^\d+$/.test(compact)) return null
  const value = Number(compact)
  return Number.isSafeInteger(value) ? value : null
}

/** The API compares service names trimmed and case-insensitively. */
export function sameServiceName(a: string, b: string): boolean {
  return a.trim().toLocaleLowerCase('en') === b.trim().toLocaleLowerCase('en')
}

/** Another active service of the shop with this name (the API's 409 `CONFLICT`), if any. */
export function activeNameClash(
  name: string,
  services: ReadonlyArray<MockService>,
  exceptId?: string,
): MockService | undefined {
  return services.find((s) => s.id !== exceptId && s.is_active && sameServiceName(s.name, name))
}

export function validateService(
  draft: ServiceDraft,
  services: ReadonlyArray<MockService>,
  editingId?: string,
): ServiceErrors {
  const errors: ServiceErrors = {}

  const name = draft.name.trim()
  const clash = draft.isActive ? activeNameClash(name, services, editingId) : undefined
  if (!name) errors.name = 'Enter a name for the service.'
  else if (name.length > SERVICE_NAME_MAX) errors.name = 'Use 120 characters or fewer.'
  else if (clash) errors.name = `Another active service is already called “${clash.name}”.`

  if (draft.description.trim().length > SERVICE_DESCRIPTION_MAX)
    errors.description = 'Use 1,000 characters or fewer.'

  const duration = parseWholeNumber(draft.duration)
  if (!draft.duration.trim()) errors.duration = 'Enter how long the service takes, in minutes.'
  else if (duration === null || duration < DURATION_MIN || duration > DURATION_MAX)
    errors.duration = 'Enter whole minutes from 5 to 10,080.'

  if (draft.price.trim()) {
    const price = parseWholeNumber(draft.price)
    if (price === null || price > PRICE_MAX)
      errors.price = 'Enter whole rupees, like 2500, or leave it blank.'
  }
  return errors
}

/** The service as stored: trimmed text, whole numbers, and `null` for "Price after inspection". */
export function serviceFromDraft(
  draft: ServiceDraft,
  ids: { id: string; shopId: string },
): MockService {
  return {
    id: ids.id,
    shopId: ids.shopId,
    name: draft.name.trim(),
    description: draft.description.trim(),
    estimated_duration_minutes: parseWholeNumber(draft.duration) ?? 60,
    base_price: draft.price.trim() ? parseWholeNumber(draft.price) : null,
    is_active: draft.isActive,
  }
}

/** "45 min", "2 h", "1 h 30 min". */
export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

/** E-28 lists services by name. */
export function sortServices(services: ReadonlyArray<MockService>): MockService[] {
  return [...services].sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }))
}

export function filterServices(
  services: ReadonlyArray<MockService>,
  query: string,
  filter: ServiceFilter,
): MockService[] {
  const needle = query.trim().toLocaleLowerCase('en')
  return services.filter((s) => {
    if (filter === 'active' && !s.is_active) return false
    if (filter === 'inactive' && s.is_active) return false
    if (!needle) return true
    return (
      s.name.toLocaleLowerCase('en').includes(needle) ||
      s.description.toLocaleLowerCase('en').includes(needle)
    )
  })
}

/**
 * Whether customers can book the shop online (D64: listed and at least one active service; D96
 * suspensions are handled by the section gate before this screen renders).
 */
export type Bookability = 'bookable' | 'no-services' | 'no-active' | 'unlisted'

export function bookability(
  shop: Pick<MockShop, 'is_listed'>,
  services: ReadonlyArray<MockService>,
): Bookability {
  if (services.length === 0) return 'no-services'
  if (!services.some((s) => s.is_active)) return 'no-active'
  if (!shop.is_listed) return 'unlisted'
  return 'bookable'
}

export interface ServiceSuggestion {
  name: string
  description: string
  minutes: number
}

/**
 * P1 quick-add (spec 10 O-03): the brief's §5.1 examples, worded as in the spec 11 catalogue. The
 * owner still sets the price.
 */
export const COMMON_SERVICES: ReadonlyArray<ServiceSuggestion> = [
  {
    name: 'Oil change',
    description:
      'Drain and refill engine oil, replace the oil filter, top up fluids. Oil and filter are quoted on the estimate.',
    minutes: 45,
  },
  {
    name: 'Brake failure',
    description: 'Diagnose and repair brake problems: pads, discs, fluid, lines and handbrake.',
    minutes: 120,
  },
  {
    name: 'Check engine light',
    description: 'OBD-II scan, fault-code reading, sensor checks and a road test.',
    minutes: 60,
  },
  {
    name: 'Tire rotation',
    description: 'Rotate tires, set pressures and check tread depth.',
    minutes: 30,
  },
]

/** The common services the shop doesn't have yet (active or not). */
export function suggestionsFor(services: ReadonlyArray<MockService>): ServiceSuggestion[] {
  return COMMON_SERVICES.filter(
    (suggestion) => !services.some((s) => sameServiceName(s.name, suggestion.name)),
  )
}

export function plural(count: number, noun: string): string {
  return `${count.toLocaleString('en')} ${count === 1 ? noun : `${noun}s`}`
}
