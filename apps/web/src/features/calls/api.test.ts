import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/lib/api/errors'

const GET = vi.fn()
vi.mock('@/lib/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/client')>()),
  api: { GET },
}))

const { findMyBookingId } = await import('./api')

function respond(status: number, body: unknown) {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
  return response.ok ? { data: body, response } : { error: body, response }
}

describe('calls api', () => {
  beforeEach(() => GET.mockReset())

  it("finds the customer's live booking by its reference", async () => {
    GET.mockResolvedValue(
      respond(200, {
        items: [
          { id: 'b-1', reference: 'BF-SEED01' },
          { id: 'b-2', reference: 'BF-SEED02' },
        ],
      }),
    )
    await expect(findMyBookingId('BF-SEED02')).resolves.toBe('b-2')
    await expect(findMyBookingId('BF-SEED09')).resolves.toBeNull()
  })

  it('surfaces a missing API session as a 401 ApiError', async () => {
    GET.mockResolvedValue(
      respond(401, { status: 401, code: 'UNAUTHENTICATED', title: 'Unauthorized' }),
    )
    const error = await findMyBookingId('BF-SEED02').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(401)
  })
})
