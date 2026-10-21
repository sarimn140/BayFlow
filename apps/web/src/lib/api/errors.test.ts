// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest'

import { onSessionExpired, resetSessionExpired } from '@/lib/auth/session'

import { sessionMiddleware, unwrap } from './client'
import {
  ApiError,
  ERROR_CODES,
  ERROR_MESSAGES,
  NETWORK_ERROR_MESSAGE,
  NetworkError,
  getErrorMessage,
  isApiError,
} from './errors'

const problemResponse = (status: number, headers: Record<string, string> = {}) =>
  new Response(null, {
    status,
    headers: { 'content-type': 'application/problem+json', ...headers },
  })

describe('ApiError.fromResponse (RFC 9457 problem+json → typed code, D49)', () => {
  it('reads code, title, detail and status', () => {
    const error = ApiError.fromResponse(problemResponse(409), {
      type: 'about:blank',
      title: 'Conflict',
      status: 409,
      code: 'SLOT_FULL',
      detail: 'Slot capacity already reached',
    })
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.code).toBe('SLOT_FULL')
    expect(error.title).toBe('Conflict')
    expect(error.detail).toBe('Slot capacity already reached')
    expect(error.rawCode).toBeUndefined()
    expect(isApiError(error, 'SLOT_FULL')).toBe(true)
  })

  it('maps `errors[]` body paths onto field errors with their code (spec 03 §2.3)', () => {
    const error = ApiError.fromResponse(problemResponse(422), {
      code: 'VALIDATION_ERROR',
      errors: [
        {
          field: 'vehicle.year',
          message: 'Year must be between 1900 and 2027.',
          code: 'value_error',
        },
        {
          field: 'customer.password',
          message: 'String should have at least 12 characters',
          code: 'string_too_short',
        },
        { field: 'lines.2.unit_price', message: 'Must be whole rupees', code: 'not_whole_rupees' },
        { field: 'vehicle.year', message: 'second error on the same field', code: 'ignored' },
      ],
    })
    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.fieldErrors).toEqual({
      'vehicle.year': { message: 'Year must be between 1900 and 2027.', code: 'value_error' },
      'customer.password': {
        message: 'String should have at least 12 characters',
        code: 'string_too_short',
      },
      'lines.2.unit_price': { message: 'Must be whole rupees', code: 'not_whole_rupees' },
    })
    expect(error.formErrors).toEqual([])
  })

  it('sends query/path parameters and the whole body to form-level errors', () => {
    const error = ApiError.fromResponse(problemResponse(422), {
      code: 'VALIDATION_ERROR',
      errors: [
        {
          field: 'query.limit',
          message: 'Input should be less than or equal to 100',
          code: 'less_than_equal',
        },
        { field: 'path.booking_id', message: 'Input should be a valid UUID', code: 'uuid_parsing' },
        { field: '', message: 'Field required', code: 'missing' },
      ],
    })
    expect(error.fieldErrors).toEqual({})
    expect(error.formErrors).toEqual([
      {
        field: 'query.limit',
        message: 'Input should be less than or equal to 100',
        code: 'less_than_equal',
      },
      { field: 'path.booking_id', message: 'Input should be a valid UUID', code: 'uuid_parsing' },
      { field: '', message: 'Field required', code: 'missing' },
    ])
  })

  it('skips malformed items and ignores non-standard shapes', () => {
    const error = ApiError.fromResponse(problemResponse(422), {
      code: 'VALIDATION_ERROR',
      errors: [
        null,
        'oops',
        { field: 'shop_id' },
        { message: 'no field' },
        { loc: ['body', 'x'], msg: 'old shape' },
      ],
      detail: [{ loc: ['body', 'shop_id'], msg: 'Input should be a valid UUID' }],
    })
    expect(error.fieldErrors).toEqual({})
    expect(error.formErrors).toEqual([])
    expect(error.detail).toBeUndefined()
  })

  it('maps an unknown (newer) code by HTTP status and keeps the raw code', () => {
    const error = ApiError.fromResponse(problemResponse(409), { code: 'SOMETHING_NEW' })
    expect(error.code).toBe('CONFLICT')
    expect(error.rawCode).toBe('SOMETHING_NEW')
  })

  it('treats non-problem bodies (e.g. a proxy error page) as INTERNAL_ERROR', () => {
    expect(
      ApiError.fromResponse(new Response(null, { status: 502 }), '<html>Bad gateway</html>').code,
    ).toBe('INTERNAL_ERROR')
    expect(ApiError.fromResponse(new Response(null, { status: 404 }), undefined).code).toBe(
      'INTERNAL_ERROR',
    )
  })

  it('keeps X-Request-ID and Retry-After', () => {
    const error = ApiError.fromResponse(
      problemResponse(429, { 'X-Request-ID': 'req-123', 'Retry-After': '30' }),
      { code: 'RATE_LIMITED' },
    )
    expect(error.requestId).toBe('req-123')
    expect(error.retryAfterSeconds).toBe(30)
  })
})

describe('getErrorMessage (WEB-05)', () => {
  it('has a default message for every glossary §10 code', () => {
    expect(Object.keys(ERROR_MESSAGES).sort()).toEqual([...ERROR_CODES].sort())
    expect(ERROR_CODES).toHaveLength(27)
  })

  it('maps by code, never by parsing detail', () => {
    const slotFull = ApiError.fromResponse(problemResponse(409), {
      code: 'SLOT_FULL',
      detail: 'internal wording',
    })
    expect(getErrorMessage(slotFull)).toBe(
      'That time was just booked by someone else. Please pick another slot.',
    )
    const emailTaken = ApiError.fromResponse(problemResponse(409), {
      code: 'EMAIL_ALREADY_REGISTERED',
    })
    expect(getErrorMessage(emailTaken)).toBe('An account with this e-mail already exists.')
  })

  it('shows the server detail only for CONFLICT', () => {
    const conflict = ApiError.fromResponse(problemResponse(409), {
      code: 'CONFLICT',
      detail: 'SKU already exists',
    })
    expect(getErrorMessage(conflict)).toBe('SKU already exists')
  })

  it('handles network and unknown errors', () => {
    expect(getErrorMessage(new NetworkError(new TypeError('fetch failed')))).toBe(
      NETWORK_ERROR_MESSAGE,
    )
    expect(getErrorMessage(new Error('boom'))).toBe(ERROR_MESSAGES.INTERNAL_ERROR)
  })
})

describe('unwrap', () => {
  it('returns data for 2xx responses', async () => {
    const data = { id: 'b1' }
    await expect(
      unwrap(Promise.resolve({ data, response: new Response(null, { status: 200 }) })),
    ).resolves.toBe(data)
  })

  it('throws ApiError for non-2xx responses', async () => {
    const call = Promise.resolve({
      error: { code: 'NOT_FOUND', title: 'Not found' },
      response: problemResponse(404),
    })
    await expect(unwrap(call)).rejects.toMatchObject({
      name: 'ApiError',
      code: 'NOT_FOUND',
      status: 404,
    })
  })

  it('throws NetworkError when fetch rejects', async () => {
    await expect(unwrap(Promise.reject(new TypeError('fetch failed')))).rejects.toBeInstanceOf(
      NetworkError,
    )
  })
})

describe('session middleware (spec 09 §2.8)', () => {
  afterEach(() => resetSessionExpired())

  const respond = (schemaPath: string, status: number) =>
    sessionMiddleware.onResponse?.({
      request: new Request(`http://localhost:3000${schemaPath}`),
      response: new Response(null, { status }),
      schemaPath,
      params: {},
      id: 'test',
      // Test double: the middleware never reads the client options.
      options: {} as never,
    })

  it('emits session-expired once on a 401 from a normal call', async () => {
    let calls = 0
    const unsubscribe = onSessionExpired(() => {
      calls += 1
    })
    await respond('/api/v1/me/bookings', 401)
    await respond('/api/v1/me/notifications', 401)
    unsubscribe()
    expect(calls).toBe(1)
  })

  it('ignores 401 from auth probes and non-401 statuses', async () => {
    let calls = 0
    const unsubscribe = onSessionExpired(() => {
      calls += 1
    })
    await respond('/api/v1/auth/login', 401)
    await respond('/api/v1/me', 401)
    await respond('/api/v1/me/bookings', 403)
    unsubscribe()
    expect(calls).toBe(0)
  })
})
