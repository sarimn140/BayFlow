import { describe, expect, it } from 'vitest'

import {
  draftLineTotal,
  estimateTotals,
  lineTotal,
  sameItems,
  toDraftLines,
  validateDraft,
  type DraftLine,
} from './estimate-math'

const newId = (index: number) => `new-${index}`

const line = (patch: Partial<DraftLine>): DraftLine => ({
  key: 'k',
  type: 'LABOR',
  description: 'Labour',
  quantity: '1',
  unitPrice: '1000',
  ...patch,
})

describe('lineTotal (D41)', () => {
  it('multiplies in whole rupees and rounds half up', () => {
    expect(lineTotal(1, 6000)).toBe(6000)
    expect(lineTotal(2, 1500)).toBe(3000)
    expect(lineTotal(1.5, 3333)).toBe(5000) // 4,999.5 → 5,000
    expect(lineTotal(0.33, 100)).toBe(33)
  })
})

describe('estimateTotals', () => {
  it('splits parts and labour', () => {
    expect(
      estimateTotals([
        { type: 'PART', total: 1800 },
        { type: 'LABOR', total: 6000 },
        { type: 'LABOR', total: 3000 },
      ]),
    ).toEqual({ parts: 1800, labour: 9000, total: 10800 })
  })
})

describe('validateDraft (spec 08 O1)', () => {
  it('refuses an empty estimate', () => {
    expect(validateDraft([], newId)).toEqual({
      ok: false,
      formError: 'Add at least one part or labour line first.',
      errors: {},
    })
  })

  it('accepts rupee formatting and labour decimals, and keeps saved ids', () => {
    const result = validateDraft(
      [
        line({ key: 'a', id: 'est-1', unitPrice: 'Rs 3,500', quantity: '1.5' }),
        line({ key: 'b', type: 'PART', description: 'Oil filter', unitPrice: '900' }),
      ],
      newId,
    )
    expect(result).toEqual({
      ok: true,
      items: [
        {
          id: 'est-1',
          description: 'Labour',
          type: 'LABOR',
          quantity: 1.5,
          unit_price: 3500,
          total: 5250,
        },
        {
          id: 'new-1',
          description: 'Oil filter',
          type: 'PART',
          quantity: 1,
          unit_price: 900,
          total: 900,
        },
      ],
    })
  })

  it('flags each bad field by line', () => {
    const result = validateDraft(
      [
        line({ key: 'a', description: '  ' }),
        line({ key: 'b', type: 'PART', quantity: '1.5' }),
        line({ key: 'c', quantity: '0', unitPrice: '12.50' }),
      ],
      newId,
    )
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(Object.keys(result.errors)).toEqual(['a', 'b', 'c'])
    expect(result.errors.a?.description).toBe('Describe the work.')
    expect(result.errors.b?.quantity).toMatch(/whole number/)
    expect(result.errors.c?.quantity).toMatch(/0\.01 to 999\.99/)
    expect(result.errors.c?.unitPrice).toBe('Enter whole rupees, 0 or more.')
  })

  it('previews a line total only while both numbers are valid', () => {
    expect(draftLineTotal(line({ quantity: '2', unitPrice: '1,250' }))).toBe(2500)
    expect(draftLineTotal(line({ unitPrice: '' }))).toBeNull()
  })
})

describe('sameItems', () => {
  it('tells an unchanged estimate from an edited one', () => {
    const oil = {
      id: 'e1',
      description: 'Oil',
      type: 'PART' as const,
      quantity: 1,
      unit_price: 900,
      total: 900,
    }
    const roundTrip = validateDraft(toDraftLines([oil]), newId)
    expect(roundTrip.ok && sameItems(roundTrip.items, [oil])).toBe(true)
    expect(sameItems([{ ...oil, unit_price: 800, total: 800 }], [oil])).toBe(false)
  })
})
