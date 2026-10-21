import { z } from 'zod'

/**
 * The booking wizard's single form (spec 10 P-03 "State"): one schema across the steps, each step
 * validating only its own fields. Limits follow `BookingCreate` (spec 03 §4.6, spec 09 §2.10).
 * Anonymous visitors give their name, e-mail and a password (D32); a signed-in user books as
 * themselves, so those three are not asked for.
 */

const PHONE = /^\+?[0-9][0-9 -]*[0-9]$/
const textUpTo = (max: number) => z.string().trim().max(max, `Use at most ${max} characters.`)

export function wizardSchema(signedIn: boolean, nextYear: number) {
  return z.object({
    serviceIds: z
      .array(z.string())
      .min(1, 'Choose at least one service.')
      .max(10, 'Choose at most 10 services.'),
    notes: z.string().max(2000, 'Use at most 2,000 characters.'),
    date: z.string().min(1, 'Choose a date.'),
    time: z.string().min(1, 'Choose a time.'),
    fullName: signedIn ? z.string() : textUpTo(120).min(1, 'Enter your full name.'),
    email: signedIn
      ? z.string()
      : z
          .string()
          .trim()
          .min(1, 'Enter your e-mail address.')
          .max(254, 'Use at most 254 characters.')
          .pipe(z.email('Enter a valid e-mail address, like name@example.com.')),
    password: signedIn
      ? z.string()
      : z.string().min(12, 'Use at least 12 characters.').max(128, 'Use at most 128 characters.'),
    phone: z
      .string()
      .trim()
      .refine(
        (value) => value === '' || (value.length >= 7 && value.length <= 20 && PHONE.test(value)),
        'Use 7–20 digits, spaces or hyphens, with an optional leading +.',
      ),
    registration: z
      .string()
      .trim()
      .min(2, 'Enter the registration number.')
      .max(20, 'Use at most 20 characters.')
      .refine(
        (value) => /^[A-Za-z0-9]{2,}$/.test(value.replace(/[\s-]/g, '')),
        'Use letters and digits, like LEA-1234.',
      ),
    make: textUpTo(60).min(1, 'Enter the make, like Toyota.'),
    model: textUpTo(60).min(1, 'Enter the model, like Corolla.'),
    year: z
      .string()
      .trim()
      .refine(
        (value) => /^\d{4}$/.test(value) && Number(value) >= 1900 && Number(value) <= nextYear,
        `Enter a year from 1900 to ${nextYear}.`,
      ),
    color: textUpTo(30),
    mileage: z
      .string()
      .trim()
      .refine(
        (value) => value === '' || (/^\d+$/.test(value) && Number(value) <= 2_000_000),
        'Enter whole kilometres, up to 2,000,000.',
      ),
  })
}

export type WizardValues = z.input<ReturnType<typeof wizardSchema>>

export const EMPTY_VALUES: WizardValues = {
  serviceIds: [],
  notes: '',
  date: '',
  time: '',
  fullName: '',
  email: '',
  password: '',
  phone: '',
  registration: '',
  make: '',
  model: '',
  year: '',
  color: '',
  mileage: '',
}

/** The fields each step owns; Continue validates only these. */
export const STEP_FIELDS = {
  services: ['serviceIds', 'notes'],
  time: ['date', 'time'],
  details: [
    'fullName',
    'email',
    'password',
    'phone',
    'registration',
    'make',
    'model',
    'year',
    'color',
    'mileage',
  ],
} as const satisfies Record<string, ReadonlyArray<keyof WizardValues>>

export type FormStep = keyof typeof STEP_FIELDS

/** The first step whose fields don't pass, or null when everything up to review is valid. */
export function firstIncompleteStep(
  values: WizardValues,
  signedIn: boolean,
  nextYear: number,
): FormStep | null {
  const result = wizardSchema(signedIn, nextYear).safeParse(values)
  if (result.success) return null
  const invalid = new Set(result.error.issues.map((issue) => String(issue.path[0])))
  return (
    (Object.keys(STEP_FIELDS) as FormStep[]).find((step) =>
      STEP_FIELDS[step].some((field) => invalid.has(field)),
    ) ?? null
  )
}

const STORAGE_PREFIX = 'bf:wizard:'

/** Saved answers for a shop (R9): everything except the password, which is never stored. */
export function loadSavedAnswers(slug: string): Partial<WizardValues> | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_PREFIX + slug)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    const saved: Partial<WizardValues> = {}
    for (const key of Object.keys(EMPTY_VALUES) as Array<keyof WizardValues>) {
      if (key === 'password') continue
      const value = (parsed as Record<string, unknown>)[key]
      if (key === 'serviceIds') {
        if (Array.isArray(value) && value.every((id) => typeof id === 'string')) {
          saved.serviceIds = value as string[]
        }
      } else if (typeof value === 'string') {
        saved[key] = value
      }
    }
    return saved
  } catch {
    return null
  }
}

export function saveAnswers(slug: string, values: WizardValues): void {
  try {
    const stored: Partial<WizardValues> = { ...values }
    delete stored.password
    window.sessionStorage.setItem(STORAGE_PREFIX + slug, JSON.stringify(stored))
  } catch {
    // Storage full or blocked (private mode): the wizard still works, it just won't survive a reload.
  }
}

export function clearAnswers(slug: string): void {
  try {
    window.sessionStorage.removeItem(STORAGE_PREFIX + slug)
  } catch {
    // Nothing to clear.
  }
}
