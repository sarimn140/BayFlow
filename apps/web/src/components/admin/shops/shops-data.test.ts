import { beforeEach, describe, expect, it } from 'vitest'

import {
  PLATFORM_ADMIN_ACCOUNT,
  getAdminShops,
  getAdminUsers,
  suspendShop,
  type AdminShop,
} from '@/lib/mock-admin'

import {
  NO_FILTERS,
  cityOptions,
  filterShops,
  hasActiveFilters,
  shopTeam,
  statusCounts,
  type ShopFilters,
} from './shops-data'

const areeba = { name: PLATFORM_ADMIN_ACCOUNT.name, email: PLATFORM_ADMIN_ACCOUNT.email }
const ids = (tenants: ReadonlyArray<AdminShop>) => tenants.map((t) => t.shop.id)
const filters = (patch: Partial<ShopFilters>): ShopFilters => ({ ...NO_FILTERS, ...patch })

beforeEach(() => {
  localStorage.clear()
})

describe('filterShops (E-62)', () => {
  it('lists every shop, newest first', () => {
    const all = filterShops(getAdminShops(), NO_FILTERS)
    expect(all).toHaveLength(6)
    expect(ids(all)[0]).toBe('shop-lyallpur-motors')
    expect(ids(all).at(-1)).toBe('shop-lahore-auto-care')
  })

  it('filters by status, suspended shops included', () => {
    suspendShop('shop-raza-auto-works', 'Unpaid platform invoices', areeba)
    const tenants = getAdminShops()
    expect(ids(filterShops(tenants, filters({ status: 'SUSPENDED' })))).toEqual([
      'shop-raza-auto-works',
    ])
    expect(filterShops(tenants, filters({ status: 'ACTIVE' }))).toHaveLength(5)
    expect(filterShops(tenants, NO_FILTERS)).toHaveLength(6)
  })

  it('filters by city and by directory listing', () => {
    const tenants = getAdminShops()
    expect(ids(filterShops(tenants, filters({ city: 'Lahore' })))).toEqual([
      'shop-raza-auto-works',
      'shop-lahore-auto-care',
    ])
    const unlisted = tenants.map((t) =>
      t.shop.id === 'shop-clifton-car-clinic' ? { ...t, shop: { ...t.shop, is_listed: false } } : t,
    )
    expect(ids(filterShops(unlisted, filters({ listed: 'UNLISTED' })))).toEqual([
      'shop-clifton-car-clinic',
    ])
    expect(filterShops(unlisted, filters({ listed: 'LISTED' }))).toHaveLength(5)
  })

  it('searches name, slug, city and owner e-mail, ignoring case and spaces', () => {
    const tenants = getAdminShops()
    expect(ids(filterShops(tenants, filters({ q: '  KARACHI ' })))).toEqual([
      'shop-clifton-car-clinic',
    ])
    expect(ids(filterShops(tenants, filters({ q: 'owner.pindi' })))).toEqual([
      'shop-pindi-auto-garage',
    ])
    expect(ids(filterShops(tenants, filters({ q: 'raza-auto' })))).toEqual(['shop-raza-auto-works'])
    expect(filterShops(tenants, filters({ q: 'zzz' }))).toEqual([])
  })
})

describe('statusCounts', () => {
  it('counts each status under the other filters', () => {
    suspendShop('shop-raza-auto-works', 'Unpaid platform invoices', areeba)
    const tenants = getAdminShops()
    expect(statusCounts(tenants, NO_FILTERS)).toEqual({ ALL: 6, ACTIVE: 5, SUSPENDED: 1 })
    expect(statusCounts(tenants, filters({ city: 'Lahore', status: 'ACTIVE' }))).toEqual({
      ALL: 2,
      ACTIVE: 1,
      SUSPENDED: 1,
    })
  })
})

describe('helpers', () => {
  it('knows when a filter is set', () => {
    expect(hasActiveFilters(NO_FILTERS)).toBe(false)
    expect(hasActiveFilters(filters({ q: '   ' }))).toBe(false)
    expect(hasActiveFilters(filters({ q: 'lahore' }))).toBe(true)
    expect(hasActiveFilters(filters({ listed: 'UNLISTED' }))).toBe(true)
  })

  it('lists each city once, A to Z', () => {
    expect(cityOptions(getAdminShops())).toEqual([
      'Faisalabad',
      'Islamabad',
      'Karachi',
      'Lahore',
      'Rawalpindi',
    ])
  })

  it('lists the team by role, then name, the owner first', () => {
    const team = shopTeam(getAdminUsers(), 'shop-lahore-auto-care')
    expect(team.map(({ user, membership }) => `${membership.role}:${user.name}`)).toEqual([
      'OWNER:Fatima Raza',
      'SERVICE_ADVISOR:Bilal',
      'TECHNICIAN:Hamza',
      'TECHNICIAN:Imran',
      'PARTS_PERSON:Usman',
      'QC_INSPECTOR:Hina',
      'QC_INSPECTOR:Sara',
    ])
    // Raza Auto Works has its own team (spec 11), with Fatima as its owner.
    expect(shopTeam(getAdminUsers(), 'shop-raza-auto-works').map((m) => m.user.name)).toEqual([
      'Fatima Raza',
      'Adeel Anwar',
      'Naveed Akhtar',
      'Faisal Javed',
      'Rabia Saeed',
    ])
  })
})
