import { describe, expect, it } from 'vitest'

import { sectionAccess, sectionAudience, sectionOf } from './pos-access'

describe('sectionAccess (spec 10 S-01 matrix)', () => {
  it('gives each role its own queue', () => {
    expect(sectionAccess('SERVICE_ADVISOR', 'bookings')).toBe('manage')
    expect(sectionAccess('TECHNICIAN', 'jobs')).toBe('manage')
    expect(sectionAccess('PARTS_PERSON', 'parts')).toBe('manage')
    expect(sectionAccess('PARTS_PERSON', 'inventory')).toBe('manage')
    expect(sectionAccess('QC_INSPECTOR', 'qc')).toBe('manage')
  })

  it("lets the Owner manage the shop and read the other roles' queues (D16)", () => {
    for (const section of ['overview', 'bookings', 'inventory', 'team', 'services', 'settings'])
      expect(sectionAccess('OWNER', section)).toBe('manage')
    for (const section of ['jobs', 'parts', 'purchase-orders', 'qc'])
      expect(sectionAccess('OWNER', section)).toBe('read')
  })

  it("keeps roles out of each other's areas", () => {
    expect(sectionAccess('TECHNICIAN', 'overview')).toBeNull()
    expect(sectionAccess('SERVICE_ADVISOR', 'qc')).toBeNull()
    expect(sectionAccess('QC_INSPECTOR', 'inventory')).toBeNull()
    expect(sectionAccess('CUSTOMER', 'bookings')).toBeNull()
  })

  it('does not gate paths that are not sections', () => {
    expect(sectionAccess('TECHNICIAN', 'unknown')).toBe('manage')
  })
})

describe('sectionAudience', () => {
  it('names the roles, Owners last', () => {
    expect(sectionAudience('bookings')).toBe('This area is for Service Advisors and Owners.')
    expect(sectionAudience('overview')).toBe('This area is for Owners.')
    expect(sectionAudience('inventory')).toBe('This area is for Parts staff and Owners.')
  })
})

describe('sectionOf', () => {
  it('reads the section from a shop path', () => {
    expect(sectionOf('/pos/shops/shop-a/qc/bk-3')).toBe('qc')
    expect(sectionOf('/pos/shops/shop-a/overview')).toBe('overview')
    expect(sectionOf('/pos/shops/shop-a')).toBeNull()
    expect(sectionOf('/pos/summary')).toBeNull()
  })
})
