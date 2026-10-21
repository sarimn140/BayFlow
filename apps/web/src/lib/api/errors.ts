/**
 * Typed API errors (spec 09 §2.9, D49). Every API error is RFC 9457 `application/problem+json`
 * with an extra `code` (glossary §10). UI code maps errors to messages by `code`, never by
 * parsing `detail` (spec 12 §1.2).
 */

/** Glossary §10, in table order (including the bonus calling codes). */
export const ERROR_CODES = [
  'VALIDATION_ERROR',
  'INVALID_SLOT',
  'ESTIMATE_EMPTY',
  'MEMBER_NOT_ELIGIBLE',
  'UNAUTHENTICATED',
  'INVALID_CREDENTIALS',
  'FORBIDDEN',
  'NOT_ASSIGNED',
  'IDENTITY_NOT_VERIFIED',
  'NOT_FOUND',
  'METHOD_NOT_ALLOWED',
  'EMAIL_ALREADY_REGISTERED',
  'INVALID_TRANSITION',
  'CONCURRENT_UPDATE',
  'SLOT_FULL',
  'ALREADY_PICKED',
  'STALE_ESTIMATE',
  'ESTIMATE_LOCKED',
  'INSUFFICIENT_STOCK',
  'CALL_BUSY',
  'CALL_ALREADY_ANSWERED',
  'CALL_NOT_ACTIVE',
  'CONFLICT',
  'PAYLOAD_TOO_LARGE',
  'RATE_LIMITED',
  'INTERNAL_ERROR',
  'CALLING_DISABLED',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

export function isErrorCode(value: unknown): value is ErrorCode {
  return typeof value === 'string' && (ERROR_CODES as ReadonlyArray<string>).includes(value)
}

/** Default user-facing message per code (spec 09 §2.9). Screens may override with context. */
export const ERROR_MESSAGES = {
  VALIDATION_ERROR: 'Please check the highlighted fields.',
  INVALID_SLOT: 'That time is no longer available. Please choose another slot.',
  ESTIMATE_EMPTY: 'Add at least one part or labour line first.',
  MEMBER_NOT_ELIGIBLE: "That person can't be assigned — they may be inactive or have another role.",
  UNAUTHENTICATED: 'Your session has expired. Please log in again.',
  INVALID_CREDENTIALS: 'Incorrect e-mail or password.',
  FORBIDDEN: "Your role can't do that in this shop.",
  NOT_ASSIGNED: 'This job is assigned to someone else.',
  IDENTITY_NOT_VERIFIED: "The caller's identity hasn't been verified yet.",
  NOT_FOUND: "We couldn't find that. It may have been removed, or you may not have access.",
  METHOD_NOT_ALLOWED: "That action isn't supported here.",
  EMAIL_ALREADY_REGISTERED: 'An account with this e-mail already exists.',
  INVALID_TRANSITION: "This booking has moved on — we've refreshed it.",
  CONCURRENT_UPDATE:
    "Someone else just updated this booking. We've loaded the latest version — please check and try again.",
  SLOT_FULL: 'That time was just booked by someone else. Please pick another slot.',
  ALREADY_PICKED: 'Another inspector picked this job first.',
  STALE_ESTIMATE: 'The shop updated this estimate. Please review the latest version.',
  ESTIMATE_LOCKED: "This estimate can't be edited any more.",
  INSUFFICIENT_STOCK:
    'Not enough stock is available. Check the parts list or order the missing parts.',
  CALL_BUSY: 'This booking already has an active call.',
  CALL_ALREADY_ANSWERED: 'Another service advisor answered this call first.',
  CALL_NOT_ACTIVE: 'This call has already ended.',
  CONFLICT: 'That conflicts with an existing record.',
  PAYLOAD_TOO_LARGE: 'That request is too large.',
  RATE_LIMITED: 'Too many attempts. Please wait a moment and try again.',
  INTERNAL_ERROR: 'Something went wrong on our side. Please try again.',
  CALLING_DISABLED: "Calling isn't available right now.",
} as const satisfies Record<ErrorCode, string>

/** Shown for `NetworkError` (offline, DNS, CORS — no HTTP status). */
export const NETWORK_ERROR_MESSAGE = 'Something went wrong — try again.'

/** One item of a 422 body's `errors[]` (spec 03 §2.3): `message` is user-safe, `code` is Pydantic's. */
export interface FieldError {
  message: string
  code: string
}

/** A field error that does not belong to a form field (a `query.`/`path.` parameter or `""`). */
export interface FormError extends FieldError {
  field: string
}

interface ApiErrorInit {
  status: number
  code: ErrorCode
  rawCode?: string | undefined
  title?: string | undefined
  detail?: string | undefined
  fieldErrors?: Record<string, FieldError>
  formErrors?: FormError[]
  requestId?: string | undefined
  retryAfterSeconds?: number | undefined
}

/** An HTTP error answer from the API (any non-2xx response). */
export class ApiError extends Error {
  override readonly name = 'ApiError'
  /** HTTP status code. */
  readonly status: number
  /** Glossary §10 code. Non-problem bodies (e.g. a proxy's 502 page) become `INTERNAL_ERROR`. */
  readonly code: ErrorCode
  /** The `code` exactly as sent, when it is not (yet) a known `ErrorCode`. */
  readonly rawCode: string | undefined
  readonly title: string | undefined
  /** Server text; show it only where it is user-safe (e.g. `CONFLICT`). */
  readonly detail: string | undefined
  /**
   * Request-body field path (`vehicle.registration_number`, `lines.2.unit_price`) → `{message, code}`.
   * Form fields are named exactly like the request body, so `form.setError(path, …)` needs no
   * mapping (spec 09 §2.9).
   */
  readonly fieldErrors: Readonly<Record<string, FieldError>>
  /** Errors on query/path parameters or on the body as a whole — shown in a form-level alert. */
  readonly formErrors: ReadonlyArray<FormError>
  /** `X-Request-ID` echoed by the API (glossary §9), for support. */
  readonly requestId: string | undefined
  /** Parsed `Retry-After` (seconds) on 429 responses. */
  readonly retryAfterSeconds: number | undefined

  constructor(init: ApiErrorInit) {
    super(init.detail ?? init.title ?? `API request failed with ${init.status} (${init.code})`)
    this.status = init.status
    this.code = init.code
    this.rawCode = init.rawCode
    this.title = init.title
    this.detail = init.detail
    this.fieldErrors = init.fieldErrors ?? {}
    this.formErrors = init.formErrors ?? []
    this.requestId = init.requestId
    this.retryAfterSeconds = init.retryAfterSeconds
  }

  /** Builds the error from a non-2xx response and its parsed body (openapi-fetch's `error`). */
  static fromResponse(response: Response, body: unknown): ApiError {
    const requestId = response.headers.get('X-Request-ID') ?? undefined
    const retryAfterSeconds = parseRetryAfter(response.headers.get('Retry-After'))
    const problem = isRecord(body) ? body : undefined
    const rawCode = typeof problem?.code === 'string' ? problem.code : undefined

    let code: ErrorCode
    if (isErrorCode(rawCode)) code = rawCode
    else if (rawCode !== undefined)
      code = codeFromStatus(response.status) // newer API code
    else code = 'INTERNAL_ERROR' // not a problem document (spec 09 §2.9)

    const { fieldErrors, formErrors } = problem
      ? parseErrors(problem)
      : { fieldErrors: {}, formErrors: [] }
    return new ApiError({
      status: response.status,
      code,
      rawCode: rawCode !== undefined && rawCode !== code ? rawCode : undefined,
      title: typeof problem?.title === 'string' ? problem.title : undefined,
      detail: typeof problem?.detail === 'string' ? problem.detail : undefined,
      fieldErrors,
      formErrors,
      requestId,
      retryAfterSeconds,
    })
  }
}

/** `fetch` itself rejected: offline, DNS, CORS — there is no HTTP status. */
export class NetworkError extends Error {
  override readonly name = 'NetworkError'

  constructor(cause?: unknown) {
    super('Network request failed', { cause })
  }
}

export function isApiError(error: unknown, code?: ErrorCode): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code)
}

/** The human message for any thrown value (toasts, alerts). Raw codes are never shown alone. */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'CONFLICT' && error.detail) return error.detail
    return ERROR_MESSAGES[error.code]
  }
  if (error instanceof NetworkError) return NETWORK_ERROR_MESSAGE
  return ERROR_MESSAGES.INTERNAL_ERROR
}

function codeFromStatus(status: number): ErrorCode {
  switch (status) {
    case 401:
      return 'UNAUTHENTICATED'
    case 403:
      return 'FORBIDDEN'
    case 404:
      return 'NOT_FOUND'
    case 405:
      return 'METHOD_NOT_ALLOWED'
    case 409:
      return 'CONFLICT'
    case 413:
      return 'PAYLOAD_TOO_LARGE'
    case 422:
      return 'VALIDATION_ERROR'
    case 429:
      return 'RATE_LIMITED'
    default:
      return 'INTERNAL_ERROR'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Location prefixes of non-body parameters (spec 03 §2.3). */
const FORM_LEVEL_PREFIXES = ['query.', 'path.'] as const

/**
 * The 422 extension `errors: [{ field, message, code }]` (spec 03 §2.3). `field` is a dot path into
 * the request body (`customer.email`, `lines.2.unit_price`) and becomes a field error; paths with a
 * `query.`/`path.` prefix, or `""` (the body as a whole), become form-level errors (spec 09 §2.9).
 * Malformed items are skipped; the first error per body path wins.
 */
function parseErrors(problem: Record<string, unknown>): {
  fieldErrors: Record<string, FieldError>
  formErrors: FormError[]
} {
  const fieldErrors: Record<string, FieldError> = {}
  const formErrors: FormError[] = []
  const list = Array.isArray(problem.errors) ? problem.errors : []
  for (const item of list) {
    if (!isRecord(item)) continue
    const { field, message, code } = item
    if (typeof field !== 'string' || typeof message !== 'string') continue
    const error: FieldError = { message, code: typeof code === 'string' ? code : '' }
    const formLevel = field === '' || FORM_LEVEL_PREFIXES.some((prefix) => field.startsWith(prefix))
    if (formLevel) formErrors.push({ field, ...error })
    else if (!(field in fieldErrors)) fieldErrors[field] = error
  }
  return { fieldErrors, formErrors }
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const at = Date.parse(trimmed)
  if (Number.isNaN(at)) return undefined
  return Math.max(0, Math.ceil((at - Date.now()) / 1000))
}
