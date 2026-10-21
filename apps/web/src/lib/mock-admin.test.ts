import { beforeEach, describe, expect, it } from 'vitest'

import {
  AdminActionError,
  PLATFORM_ADMIN_ACCOUNT,
  auditCsv,
  csvCell,
  getAdminShops,
  getAdminUsers,
  getAuditEvents,
  getShopSuspension,
  isAccountActive,
  isPlatformAdminEmail,
  reactivateShop,
  recordAdminView,
  recordSignIn,
  setPlatformAdmin,
  setUserActive,
  suspendShop,
  type AuditEvent,
} from './mock-admin'
import { INITIAL_BOOKINGS } from './mock-data'

const areeba = { name: PLATFORM_ADMIN_ACCOUNT.name, email: PLATFORM_ADMIN_ACCOUNT.email }
const userByEmail = (email: string) => getAdminUsers().find((u) => u.email === email)!

function expectRefusal(action: () => void, code: AdminActionError['code']) {
  try {
    action()
  } catch (error) {
    expect(error).toBeInstanceOf(AdminActionError)
    expect((error as AdminActionError).code).toBe(code)
    return
  }
  throw new Error('expected the action to be refused')
}

beforeEach(() => {
  localStorage.clear()
})

describe('directory', () => {
  it('lists each person once, with all their memberships', () => {
    const users = getAdminUsers()
    expect(new Set(users.map((u) => u.email)).size).toBe(users.length)
    const fatima = userByEmail('fatima.owner@bayflow.test')
    expect(fatima.memberships.map((m) => m.shopId).sort()).toEqual([
      'shop-lahore-auto-care',
      'shop-raza-auto-works',
    ])
    expect(fatima.kind).toBe('STAFF')
  })

  it('knows the platform admin, the staff and the customers', () => {
    expect(userByEmail('admin@bayflow.test')).toMatchObject({
      kind: 'PLATFORM_ADMIN',
      isPlatformAdmin: true,
      memberships: [],
    })
    expect(userByEmail('bilal.sa@bayflow.test').kind).toBe('STAFF')
    expect(userByEmail('ayesha.customer@bayflow.test').kind).toBe('CUSTOMER')
    expect(userByEmail('zainab.customer@bayflow.test').kind).toBe('CUSTOMER')
  })

  it('gives every shop at least one owner', () => {
    for (const tenant of getAdminShops())
      expect(tenant.owners.length, tenant.shop.name).toBeGreaterThan(0)
  })
})

describe('shop suspension (D96)', () => {
  it('suspends with a reason, refuses to do it twice, and reactivates', () => {
    expectRefusal(() => suspendShop('shop-raza-auto-works', 'no', areeba), 'VALIDATION_ERROR')
    suspendShop('shop-raza-auto-works', 'Unpaid subscription for September', areeba)
    expect(getShopSuspension('shop-raza-auto-works')).toMatchObject({
      reason: 'Unpaid subscription for September',
      byEmail: areeba.email,
    })
    expectRefusal(
      () => suspendShop('shop-raza-auto-works', 'Again, for testing', areeba),
      'CONFLICT',
    )
    reactivateShop('shop-raza-auto-works', areeba)
    expect(getShopSuspension('shop-raza-auto-works')).toBeNull()
    expectRefusal(() => reactivateShop('shop-raza-auto-works', areeba), 'CONFLICT')
  })

  it('records both actions in the audit log with the reason', () => {
    suspendShop('shop-lyallpur-motors', 'Reported for fake reviews', areeba)
    reactivateShop('shop-lyallpur-motors', areeba)
    // Seeded sample events may be timestamped later today, so compare this browser's events only.
    const [latest, previous] = getAuditEvents().filter((e) => e.id.startsWith('live:'))
    expect(latest).toMatchObject({ action: 'shop.reactivated', category: 'SHOP' })
    expect(previous).toMatchObject({
      action: 'shop.suspended',
      metadata: { reason: 'Reported for fake reviews' },
      actor: { role: 'PLATFORM_ADMIN', email: areeba.email },
    })
  })
})

describe('account safeguards (spec 19 §1)', () => {
  it('refuses self-deactivation and self-revocation', () => {
    const me = userByEmail(areeba.email)
    expectRefusal(() => setUserActive(me.id, false, 'Leaving the company', areeba), 'FORBIDDEN')
    const bilal = userByEmail('bilal.sa@bayflow.test')
    setPlatformAdmin(bilal.id, true, areeba)
    expectRefusal(() => setPlatformAdmin(me.id, false, areeba), 'FORBIDDEN')
  })

  it('keeps at least one active platform admin', () => {
    const bilal = userByEmail('bilal.sa@bayflow.test')
    setPlatformAdmin(bilal.id, true, areeba)
    const asBilal = { name: 'Bilal', email: 'bilal.sa@bayflow.test' }
    setPlatformAdmin(userByEmail(areeba.email).id, false, asBilal)
    // Bilal is now the only admin: nobody can remove or deactivate him.
    expectRefusal(() => setPlatformAdmin(bilal.id, false, areeba), 'CONFLICT')
    expectRefusal(() => setUserActive(bilal.id, false, 'Testing the guard', areeba), 'CONFLICT')
  })

  it('needs a reason to deactivate, refuses no-op changes and inactive grants', () => {
    const zainab = userByEmail('zainab.customer@bayflow.test')
    expectRefusal(() => setUserActive(zainab.id, false, '', areeba), 'VALIDATION_ERROR')
    setUserActive(zainab.id, false, 'Chargeback fraud reported by the shop', areeba)
    expect(userByEmail('zainab.customer@bayflow.test').isActive).toBe(false)
    expect(isAccountActive('Zainab.Customer@bayflow.test')).toBe(false)
    expectRefusal(
      () => setUserActive(zainab.id, false, 'Twice for good measure', areeba),
      'CONFLICT',
    )
    expectRefusal(() => setPlatformAdmin(zainab.id, true, areeba), 'VALIDATION_ERROR')
    setUserActive(zainab.id, true, null, areeba)
    expect(isAccountActive('zainab.customer@bayflow.test')).toBe(true)
  })

  it('grants and revokes platform admin', () => {
    const sara = userByEmail('sara.qc@bayflow.test')
    expect(isPlatformAdminEmail(sara.email)).toBe(false)
    setPlatformAdmin(sara.id, true, areeba)
    expect(isPlatformAdminEmail(sara.email)).toBe(true)
    expect(userByEmail(sara.email).kind).toBe('PLATFORM_ADMIN')
    expectRefusal(() => setPlatformAdmin(sara.id, true, areeba), 'CONFLICT')
    setPlatformAdmin(sara.id, false, areeba)
    expect(isPlatformAdminEmail(sara.email)).toBe(false)
  })
})

describe('audit log (D95)', () => {
  it('records every booking action of the mock bookings, newest first', () => {
    const events = getAuditEvents()
    const times = events.map((e) => e.occurredAt)
    expect([...times].sort().reverse()).toEqual(times)
    for (const booking of INITIAL_BOOKINGS) {
      expect(
        events.some((e) => e.target?.label === booking.reference && e.action === 'booking.create'),
        booking.reference,
      ).toBe(true)
    }
    expect(new Set(events.map((e) => e.id)).size).toBe(events.length)
  })

  it('records sign-ins, failed sign-ins and audited admin reads', () => {
    recordSignIn('Bilal.SA@bayflow.test', true)
    recordSignIn('nobody@bayflow.test', false)
    recordAdminView('user', { id: 'usr-bilal', label: 'bilal.sa@bayflow.test' }, areeba)
    recordAdminView('user', { id: 'usr-bilal', label: 'bilal.sa@bayflow.test' }, areeba)
    const live = getAuditEvents().filter((e) => e.id.startsWith('live:'))
    expect(live.map((e) => e.action).sort()).toEqual([
      'admin.user_viewed',
      'auth.login_failed',
      'auth.login_succeeded',
    ])
    expect(live.find((e) => e.action === 'auth.login_failed')!.metadata).toEqual({
      email: 'nobody@bayflow.test',
    })
    expect(userByEmail('bilal.sa@bayflow.test').lastLoginAt).toBe(
      live.find((e) => e.action === 'auth.login_succeeded')!.occurredAt,
    )
  })

  it("credits each shop's own owner for its team and its creation", () => {
    const events = getAuditEvents()
    const added = (shopId: string, userId: string) =>
      events.find((e) => e.id === `seed:membership.added:${shopId}:${userId}`)
    expect(added('shop-clifton-car-clinic', 'usr-sadia')).toMatchObject({
      summary: 'Asif Memon added Sadia Qureshi to Clifton Car Clinic as Service Advisor',
      actor: { email: 'owner.clifton-car-clinic@bayflow.test', role: 'OWNER' },
    })
    expect(added('shop-raza-auto-works', 'usr-adeel')?.actor?.name).toBe('Fatima Raza')
    // Fatima registered once, before her first shop.
    expect(events.filter((e) => e.action === 'auth.owner_registered')).toHaveLength(5)
    expect(events.find((e) => e.id === 'seed:shop.created:shop-lyallpur-motors')?.actor?.name).toBe(
      'Khalid Chaudhry',
    )
  })

  it('never puts a password, token or hash in an event', () => {
    for (const event of getAuditEvents()) {
      expect(JSON.stringify(event)).not.toContain('BayFlow@2026')
      for (const key of Object.keys(event.metadata)) {
        expect(key).not.toMatch(/password|token|hash|secret/i)
      }
    }
  })
})

describe('CSV export (E-75)', () => {
  it('quotes per RFC 4180 and neutralises formulas', () => {
    expect(csvCell('plain')).toBe('plain')
    expect(csvCell('a, b')).toBe('"a, b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell('line\nbreak')).toBe('"line\nbreak"')
    expect(csvCell('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`)
    expect(csvCell('+92 300 1234567')).toBe("'+92 300 1234567")
    expect(csvCell('-1')).toBe("'-1")
    expect(csvCell('@user')).toBe("'@user")
    expect(csvCell(null)).toBe('')
  })

  it('writes a header and one CRLF line per event', () => {
    const events = getAuditEvents().slice(0, 3)
    const csv = auditCsv(events)
    const lines = csv.split('\r\n')
    expect(lines[0]).toMatch(/^occurred_at,category,action,summary,/)
    expect(lines).toHaveLength(events.length + 2) // header + rows + trailing empty
  })

  it('caps the export at 10 000 rows', () => {
    const one = getAuditEvents()[0]!
    const many: AuditEvent[] = Array.from({ length: 10_005 }, (_, i) => ({ ...one, id: `x${i}` }))
    expect(auditCsv(many).split('\r\n')).toHaveLength(10_000 + 2)
  })
})
