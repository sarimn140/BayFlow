import { describe, expect, it } from 'vitest'

import { INITIAL_SERVICES, type MockService } from '@/lib/mock-data'

import {
  NEW_SERVICE_DRAFT,
  activeNameClash,
  bookability,
  draftFromService,
  filterServices,
  formatDuration,
  parseWholeNumber,
  serviceFromDraft,
  sortServices,
  suggestionsFor,
  validateService,
  type ServiceDraft,
} from './catalogue-data'

const lahore = INITIAL_SERVICES.filter((s) => s.shopId === 'shop-lahore-auto-care')
const clifton = INITIAL_SERVICES.filter((s) => s.shopId === 'shop-clifton-car-clinic')

function service(overrides: Partial<MockService>): MockService {
  return {
    id: 'srv-test',
    shopId: 'shop-test',
    name: 'Oil change',
    description: '',
    estimated_duration_minutes: 45,
    base_price: 1100,
    is_active: true,
    ...overrides,
  }
}

const draft = (overrides: Partial<ServiceDraft>): ServiceDraft => ({
  ...NEW_SERVICE_DRAFT,
  name: 'Wheel balancing',
  ...overrides,
})

describe('parseWholeNumber', () => {
  it('reads whole numbers, with or without thousands separators', () => {
    expect(parseWholeNumber('1100')).toBe(1100)
    expect(parseWholeNumber(' 1,100 ')).toBe(1100)
    expect(parseWholeNumber('0')).toBe(0)
  })

  it('refuses decimals, signs and text (whole rupees only, D41)', () => {
    for (const raw of ['', '4.5', '-5', '+5', 'abc', '1e3'])
      expect(parseWholeNumber(raw)).toBeNull()
  })
})

describe('validateService (spec 09 §2.10, ServiceCreate)', () => {
  it('accepts a complete service', () => {
    expect(validateService(draft({ price: '2,500' }), lahore)).toEqual({})
  })

  it('needs a name of 1 to 120 characters', () => {
    expect(validateService(draft({ name: '   ' }), lahore).name).toBe(
      'Enter a name for the service.',
    )
    expect(validateService(draft({ name: 'x'.repeat(121) }), lahore).name).toBe(
      'Use 120 characters or fewer.',
    )
    expect(validateService(draft({ name: 'x'.repeat(120) }), lahore).name).toBeUndefined()
  })

  it('refuses a second active service with the same name, ignoring case and spaces (409)', () => {
    const errors = validateService(draft({ name: '  wheel alignment & BALANCING ' }), lahore)
    expect(errors.name).toBe(
      'Another active service is already called “Wheel Alignment & Balancing”.',
    )
    // An inactive draft, or the service itself, is not a clash.
    expect(
      validateService(draft({ name: 'Wheel Alignment & Balancing', isActive: false }), lahore).name,
    ).toBeUndefined()
    expect(
      validateService(draft({ name: 'Wheel Alignment & Balancing' }), lahore, 'srv-alignment').name,
    ).toBeUndefined()
  })

  it('limits the description to 1,000 characters', () => {
    expect(validateService(draft({ description: 'x'.repeat(1000) }), lahore)).toEqual({})
    expect(validateService(draft({ description: 'x'.repeat(1001) }), lahore).description).toBe(
      'Use 1,000 characters or fewer.',
    )
  })

  it('needs a duration of 5 to 10,080 whole minutes', () => {
    expect(validateService(draft({ duration: '' }), lahore).duration).toBe(
      'Enter how long the service takes, in minutes.',
    )
    for (const duration of ['4', '10081', '30.5', 'soon'])
      expect(validateService(draft({ duration }), lahore).duration).toBe(
        'Enter whole minutes from 5 to 10,080.',
      )
    for (const duration of ['5', '10080', '10,080'])
      expect(validateService(draft({ duration }), lahore).duration).toBeUndefined()
  })

  it('takes an optional price in whole rupees up to 9,999,999,999', () => {
    expect(validateService(draft({ price: '' }), lahore).price).toBeUndefined()
    expect(validateService(draft({ price: '0' }), lahore).price).toBeUndefined()
    expect(validateService(draft({ price: '9999999999' }), lahore).price).toBeUndefined()
    for (const price of ['10000000000', '2500.50', 'free'])
      expect(validateService(draft({ price }), lahore).price).toBe(
        'Enter whole rupees, like 2500, or leave it blank.',
      )
  })
})

describe('draftFromService and serviceFromDraft', () => {
  it('round-trips a service, keeping a price of 0 and "Price after inspection"', () => {
    const free = service({ base_price: 0 })
    expect(draftFromService(free).price).toBe('0')
    expect(serviceFromDraft(draftFromService(free), free)).toEqual(free)

    const inspected = service({ base_price: null })
    expect(draftFromService(inspected).price).toBe('')
    expect(serviceFromDraft(draftFromService(inspected), inspected).base_price).toBeNull()
  })

  it('trims text and stores whole numbers', () => {
    const saved = serviceFromDraft(
      draft({
        name: '  AC service ',
        description: ' Gas top-up ',
        duration: '1,440',
        price: '4,950',
      }),
      { id: 'srv-new', shopId: 'shop-x' },
    )
    expect(saved).toEqual({
      id: 'srv-new',
      shopId: 'shop-x',
      name: 'AC service',
      description: 'Gas top-up',
      estimated_duration_minutes: 1440,
      base_price: 4950,
      is_active: true,
    })
  })
})

describe('activeNameClash', () => {
  it('finds only active services of the same name', () => {
    const list = [service({ id: 'a', is_active: false }), service({ id: 'b', name: 'OIL CHANGE' })]
    expect(activeNameClash('oil change', list)?.id).toBe('b')
    expect(activeNameClash('oil change', list, 'b')).toBeUndefined()
  })
})

describe('formatDuration', () => {
  it('reads minutes and hours', () => {
    expect(formatDuration(45)).toBe('45 min')
    expect(formatDuration(60)).toBe('1 h')
    expect(formatDuration(90)).toBe('1 h 30 min')
    expect(formatDuration(180)).toBe('3 h')
  })
})

describe('sortServices and filterServices', () => {
  it('lists by name (E-28) and filters by state and text', () => {
    const list = [
      service({ id: 'b', name: 'brake failure', description: 'Pads and discs' }),
      service({ id: 'a', name: 'AC service', is_active: false }),
      service({ id: 'c', name: 'Check engine light' }),
    ]
    expect(sortServices(list).map((s) => s.id)).toEqual(['a', 'b', 'c'])
    expect(filterServices(list, '', 'inactive').map((s) => s.id)).toEqual(['a'])
    expect(filterServices(list, '', 'active').map((s) => s.id)).toEqual(['b', 'c'])
    expect(filterServices(list, ' DISCS ', 'all').map((s) => s.id)).toEqual(['b'])
    expect(filterServices(list, 'nothing', 'all')).toEqual([])
  })
})

describe('bookability (D64)', () => {
  it('needs a listed shop with at least one active service', () => {
    expect(bookability({ is_listed: true }, [])).toBe('no-services')
    expect(bookability({ is_listed: true }, [service({ is_active: false })])).toBe('no-active')
    expect(bookability({ is_listed: false }, [service({ is_active: false })])).toBe('no-active')
    expect(bookability({ is_listed: false }, [service({})])).toBe('unlisted')
    expect(bookability({ is_listed: true }, lahore)).toBe('bookable')
  })
})

describe('suggestionsFor (P1 quick-add)', () => {
  it('offers the brief’s common services the shop does not have yet', () => {
    expect(suggestionsFor([]).map((s) => s.name)).toEqual([
      'Oil change',
      'Brake failure',
      'Check engine light',
      'Tire rotation',
    ])
    // The spec 11 catalogue shops already offer all four.
    expect(suggestionsFor(clifton)).toEqual([])
    expect(
      suggestionsFor([service({ name: 'oil CHANGE', is_active: false })]).map((s) => s.name),
    ).toEqual(['Brake failure', 'Check engine light', 'Tire rotation'])
  })
})
