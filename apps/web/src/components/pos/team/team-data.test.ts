import { describe, expect, it } from 'vitest'

import { INITIAL_BOOKINGS, INITIAL_TEAM, type MockTeamMember } from '@/lib/mock-data'

import {
  ALREADY_MEMBER,
  PASSWORD_NEEDED,
  canEditMember,
  deactivateMessage,
  memberRows,
  planAddMember,
  roleCoverage,
  teamSummary,
  validateDraft,
  type MemberDraft,
} from './team-data'

const LAHORE = 'shop-lahore-auto-care'
const team = INITIAL_TEAM.filter((m) => m.shopId === LAHORE)
const bookings = INITIAL_BOOKINGS.filter((b) => b.shopId === LAHORE)
const OWNER_EMAIL = 'fatima.owner@bayflow.test'

const draft = (overrides: Partial<MemberDraft> = {}): MemberDraft => ({
  fullName: 'Kamran Abbasi',
  email: 'kamran@bayflow.test',
  role: 'TECHNICIAN',
  password: 'BayFlow@2026',
  ...overrides,
})

const context = (overrides: Partial<Parameters<typeof planAddMember>[1]> = {}) => ({
  id: 'usr-new',
  shopId: LAHORE,
  team,
  accounts: [] as { email: string; name: string }[],
  ...overrides,
})

describe('validateDraft (E-26 field rules)', () => {
  it('accepts a complete draft', () => {
    expect(validateDraft(draft())).toEqual({})
  })

  it('asks for the name and the e-mail', () => {
    expect(validateDraft(draft({ fullName: '  ', email: '' }))).toEqual({
      fullName: 'Enter their full name.',
      email: 'Enter their e-mail address.',
    })
  })

  it('limits the name to 120 characters', () => {
    expect(validateDraft(draft({ fullName: 'a'.repeat(120) })).fullName).toBeUndefined()
    expect(validateDraft(draft({ fullName: 'a'.repeat(121) })).fullName).toBe(
      'Use 120 characters or fewer.',
    )
  })

  it('needs one @ with text on both sides, and accepts reserved domains (D62)', () => {
    expect(validateDraft(draft({ email: 'kamran' })).email).toBe(
      'Enter a valid e-mail address, like name@example.com.',
    )
    expect(validateDraft(draft({ email: 'a b@x.test' })).email).toBeDefined()
    expect(validateDraft(draft({ email: 'x@test' })).email).toBeUndefined()
    expect(validateDraft(draft({ email: `${'a'.repeat(250)}@x.pk` })).email).toBeDefined()
  })

  it('checks a given password against D10 (12–128) and leaves a blank one to the account check', () => {
    expect(validateDraft(draft({ password: 'short' })).password).toBe('Use 12 to 128 characters.')
    expect(validateDraft(draft({ password: 'x'.repeat(129) })).password).toBeDefined()
    expect(validateDraft(draft({ password: 'x'.repeat(12) })).password).toBeUndefined()
    expect(validateDraft(draft({ password: '' })).password).toBeUndefined()
  })
})

describe('planAddMember (E-26 on the mock store)', () => {
  it('adds a new account with a trimmed name and a lower-case e-mail', () => {
    const plan = planAddMember(
      draft({ fullName: '  Kamran Abbasi ', email: ' Kamran@BayFlow.test ' }),
      context(),
    )
    expect(plan).toEqual({
      ok: true,
      existingAccount: false,
      member: {
        id: 'usr-new',
        shopId: LAHORE,
        name: 'Kamran Abbasi',
        email: 'kamran@bayflow.test',
        role: 'TECHNICIAN',
        is_active: true,
      },
    })
  })

  it('refuses an e-mail that is already a member, inactive ones included (409)', () => {
    expect(planAddMember(draft({ email: 'IMRAN.tech@bayflow.test' }), context())).toEqual({
      ok: false,
      errors: { email: ALREADY_MEMBER },
    })
    const inactive = team.map((m) => (m.id === 'usr-sara' ? { ...m, is_active: false } : m))
    expect(
      planAddMember(draft({ email: 'sara.qc@bayflow.test' }), context({ team: inactive })),
    ).toEqual({ ok: false, errors: { email: ALREADY_MEMBER } })
  })

  it('needs a password for an e-mail without an account (422 missing)', () => {
    expect(planAddMember(draft({ password: '' }), context())).toEqual({
      ok: false,
      errors: { password: PASSWORD_NEEDED },
    })
  })

  it('only adds the membership for an existing account: its name stays, no password needed (D18)', () => {
    const plan = planAddMember(
      draft({ fullName: 'Someone Else', email: 'imran.tech@bayflow.test', password: '' }),
      context({
        shopId: 'shop-raza-auto-works',
        team: INITIAL_TEAM.filter((m) => m.shopId === 'shop-raza-auto-works'),
        accounts: [{ email: 'imran.tech@bayflow.test', name: 'Imran' }],
      }),
    )
    expect(plan.ok && plan.existingAccount).toBe(true)
    expect(plan.ok && plan.member).toMatchObject({
      name: 'Imran',
      email: 'imran.tech@bayflow.test',
      shopId: 'shop-raza-auto-works',
      role: 'TECHNICIAN',
    })
  })

  it('reports the field rules before the membership check', () => {
    const plan = planAddMember(draft({ fullName: '', email: 'imran.tech@bayflow.test' }), context())
    expect(plan).toEqual({ ok: false, errors: { fullName: 'Enter their full name.' } })
  })
})

describe('canEditMember (D19, the last-owner rule)', () => {
  const owner = team.find((m) => m.role === 'OWNER')!
  const imran = team.find((m) => m.id === 'usr-imran')!

  it('never offers the owner membership or your own row', () => {
    expect(canEditMember(owner, 'someone@else.test')).toBe(false)
    expect(canEditMember(imran, 'IMRAN.tech@bayflow.test')).toBe(false)
    expect(canEditMember(imran, OWNER_EMAIL)).toBe(true)
  })
})

describe('memberRows', () => {
  const rows = memberRows(team, bookings, OWNER_EMAIL, true)
  const byName = (name: string) => rows.find((row) => row.member.name === name)!

  it('lists the team by role, then name, as the shop overview does', () => {
    expect(rows.map((row) => row.member.name)).toEqual([
      'Fatima Raza',
      'Bilal',
      'Hamza',
      'Imran',
      'Usman',
      'Hina',
      'Sara',
    ])
  })

  it("counts open jobs with the API's rule; owner and advisor show none", () => {
    expect(byName('Imran').openJobs).toBe(2)
    // READY_FOR_PICKUP is not an open job (OPEN_JOB_EXCLUDED_STATUSES).
    expect(byName('Hamza').openJobs).toBe(1)
    expect(byName('Sara').openJobs).toBe(0)
    expect(byName('Fatima Raza').openJobs).toBeNull()
    expect(byName('Bilal').openJobs).toBeNull()
  })

  it('keeps the count of someone moved to a role that takes no jobs', () => {
    const moved = team.map((m): MockTeamMember =>
      m.id === 'usr-imran' ? { ...m, role: 'SERVICE_ADVISOR' } : m,
    )
    const row = memberRows(moved, bookings, OWNER_EMAIL, true).find(
      (r) => r.member.id === 'usr-imran',
    )
    expect(row?.openJobs).toBe(2)
  })

  it('marks you and offers the menu on staff rows only', () => {
    expect(byName('Fatima Raza')).toMatchObject({ isSelf: true, editable: false })
    expect(byName('Bilal')).toMatchObject({ isSelf: false, editable: true })
    expect(memberRows(team, bookings, OWNER_EMAIL, false).some((row) => row.editable)).toBe(false)
  })
})

describe('roleCoverage and teamSummary', () => {
  it('counts active and inactive members per staff role', () => {
    const withInactive = team.map((m) => (m.id === 'usr-hamza' ? { ...m, is_active: false } : m))
    expect(roleCoverage(withInactive)).toEqual([
      { role: 'SERVICE_ADVISOR', active: 1, inactive: 0 },
      { role: 'TECHNICIAN', active: 1, inactive: 1 },
      { role: 'PARTS_PERSON', active: 1, inactive: 0 },
      { role: 'QC_INSPECTOR', active: 2, inactive: 0 },
    ])
    expect(teamSummary(team)).toBe('7 members · all active')
    expect(teamSummary(withInactive)).toBe('7 members · 1 inactive')
    expect(teamSummary(team.slice(0, 1))).toBe('1 member · all active')
  })
})

describe('deactivateMessage', () => {
  it('says the access ends and what happens to their open jobs', () => {
    expect(deactivateMessage('Imran', 'Lahore Auto Care', 2)).toBe(
      'Imran loses access to Lahore Auto Care immediately. Their 2 open jobs stay assigned — reassign them from each booking.',
    )
    expect(deactivateMessage('Hamza', 'Lahore Auto Care', 1)).toBe(
      'Hamza loses access to Lahore Auto Care immediately. Their open job stays assigned — reassign it from the booking.',
    )
    expect(deactivateMessage('Bilal', 'Lahore Auto Care', null)).toBe(
      'Bilal loses access to Lahore Auto Care immediately. You can reactivate them at any time.',
    )
  })
})
