import { beforeEach, describe, expect, it } from 'vitest'

import { DEMO_ACCOUNTS } from '@/content/demo-accounts'

import { homePathFor, resolveMockSession } from './mock-auth'
import { INITIAL_TEAM, saveTeamMember } from './mock-data'

beforeEach(() => {
  localStorage.clear()
})

const ROLE_OF: Record<string, string> = {
  Owner: 'OWNER',
  'Service Advisor': 'SERVICE_ADVISOR',
  Technician: 'TECHNICIAN',
  'QC Inspector': 'QC_INSPECTOR',
  'Parts Person': 'PARTS_PERSON',
  Customer: 'CUSTOMER',
  'Platform Admin': 'PLATFORM_ADMIN',
}

describe('resolveMockSession', () => {
  it.each(DEMO_ACCOUNTS.map((a) => [a.email, a]))(
    'signs %s in as the listed person and role',
    (email, account) => {
      const session = resolveMockSession(email)
      expect(session.role).toBe(ROLE_OF[account.role])
      expect(session.name).toBe(account.name)
      expect(session.email).toBe(email)
    },
  )

  it('never makes a customer a platform admin because of a shared first name', () => {
    expect(resolveMockSession('zainab.customer@bayflow.test').role).toBe('CUSTOMER')
  })

  it('matches whole tokens, so a name containing "sa" is not a Service Advisor', () => {
    expect(resolveMockSession('sara.qc@bayflow.test').role).toBe('QC_INSPECTOR')
    expect(resolveMockSession('Hamza.Tech@BayFlow.test').name).toBe('Hamza')
  })

  it('normalises the e-mail and falls back to an owner named after it', () => {
    const session = resolveMockSession('  Zain.Malik@Example.pk ')
    expect(session).toMatchObject({ email: 'zain.malik@example.pk', role: 'OWNER', name: 'Zain' })
  })

  it('signs a new team member in as themselves, in their shop, not as a demo persona', () => {
    saveTeamMember({
      id: 'mbr-kamran',
      shopId: 'shop-lahore-auto-care',
      name: 'Kamran Abbasi',
      email: 'kamran.tech@bayflow.test',
      role: 'TECHNICIAN',
      is_active: true,
    })
    expect(resolveMockSession('Kamran.Tech@bayflow.test')).toEqual({
      email: 'kamran.tech@bayflow.test',
      name: 'Kamran Abbasi',
      role: 'TECHNICIAN',
      shopId: 'shop-lahore-auto-care',
      shopName: 'Lahore Auto Care',
    })
  })

  it("opens another shop's staff in their own shop (D20), never Lahore Auto Care", () => {
    expect(resolveMockSession('sa.clifton-car-clinic@bayflow.test')).toMatchObject({
      name: 'Sadia Qureshi',
      role: 'SERVICE_ADVISOR',
      shopId: 'shop-clifton-car-clinic',
      shopName: 'Clifton Car Clinic',
    })
    expect(resolveMockSession('owner.pindi-auto-garage@bayflow.test')).toMatchObject({
      name: 'Tariq Mehmood',
      role: 'OWNER',
      shopId: 'shop-pindi-auto-garage',
    })
    expect(resolveMockSession('parts.raza-auto-works@bayflow.test')).toMatchObject({
      name: 'Faisal Javed',
      role: 'PARTS_PERSON',
      shopId: 'shop-raza-auto-works',
    })
  })

  it("opens an owner's first shop by name (spec 11: Fatima → Lahore Auto Care)", () => {
    expect(resolveMockSession('fatima.owner@bayflow.test')).toMatchObject({
      role: 'OWNER',
      shopId: 'shop-lahore-auto-care',
    })
  })

  it('signs customers in without a shop, by the name on their bookings', () => {
    expect(resolveMockSession('kamran.customer@bayflow.test')).toEqual({
      email: 'kamran.customer@bayflow.test',
      name: 'Kamran Shah',
      role: 'CUSTOMER',
      shopId: '',
      shopName: '',
    })
  })

  it('gives someone whose membership was deactivated no shop (D19)', () => {
    const hamza = INITIAL_TEAM.find((m) => m.email === 'hamza.tech@bayflow.test')!
    saveTeamMember({ ...hamza, is_active: false })
    expect(resolveMockSession('hamza.tech@bayflow.test')).toMatchObject({
      name: 'Hamza',
      role: 'CUSTOMER',
      shopId: '',
    })
  })

  it('keeps an unknown e-mail out of every shop, whatever its words say', () => {
    for (const email of ['boss.owner@example.pk', 'new.tech@example.pk', 'admin@example.pk']) {
      expect(resolveMockSession(email), email).toMatchObject({ shopId: '', shopName: '' })
    }
    expect(resolveMockSession('new.tech@example.pk')).toMatchObject({
      role: 'TECHNICIAN',
      name: 'New',
    })
  })
})

describe('homePathFor', () => {
  it('sends each role to its home', () => {
    const shopId = 'shop-x'
    expect(homePathFor({ role: 'OWNER', shopId })).toBe('/pos/shops/shop-x/overview')
    expect(homePathFor({ role: 'SERVICE_ADVISOR', shopId })).toBe('/pos/shops/shop-x/bookings')
    expect(homePathFor({ role: 'TECHNICIAN', shopId })).toBe('/pos/shops/shop-x/jobs')
    expect(homePathFor({ role: 'PARTS_PERSON', shopId })).toBe('/pos/shops/shop-x/parts')
    expect(homePathFor({ role: 'QC_INSPECTOR', shopId })).toBe('/pos/shops/shop-x/qc')
    expect(homePathFor({ role: 'CUSTOMER', shopId })).toBe('/bookings')
    expect(homePathFor({ role: 'PLATFORM_ADMIN', shopId })).toBe('/admin')
  })

  it('sends staff without a shop to the hub, never to a shop path', () => {
    expect(homePathFor({ role: 'OWNER', shopId: '' })).toBe('/pos')
    expect(homePathFor({ role: 'TECHNICIAN', shopId: '' })).toBe('/pos')
    expect(homePathFor({ role: 'CUSTOMER', shopId: '' })).toBe('/bookings')
    expect(homePathFor({ role: 'PLATFORM_ADMIN', shopId: '' })).toBe('/admin')
  })
})
