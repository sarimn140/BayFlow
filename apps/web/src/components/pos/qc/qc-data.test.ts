import { afterEach, describe, expect, it } from 'vitest'

import { INITIAL_BOOKINGS, INITIAL_TEAM, type MockBooking } from '@/lib/mock-data'

import {
  EMPTY_DRAFT,
  ISSUE_TITLE_MAX,
  QC_CHECKLIST,
  checklistProgress,
  clearDraft,
  formatQcIssue,
  inProgressJobs,
  inShop,
  inspectedAgo,
  isInQc,
  isRetest,
  issueDescriptionFrom,
  issueTitleFrom,
  memberIdFor,
  memberName,
  parseDraft,
  parseQcIssue,
  passBlocker,
  pickedByOther,
  qcResultOf,
  readDraft,
  recentlyInspected,
  shopTimeZone,
  sinceLabel,
  validateIssue,
  waitedFor,
  waitingJobs,
  writeDraft,
  type QcAnswers,
} from './qc-data'

const LAHORE = 'shop-lahore-auto-care'
const TZ = 'Asia/Karachi'
const bookings = INITIAL_BOOKINGS.filter((b) => b.shopId === LAHORE)
const team = INITIAL_TEAM.filter((m) => m.shopId === LAHORE)
const seed = bookings.find((b) => b.id === 'bk-003')!

function booking(overrides: Partial<MockBooking>): MockBooking {
  return { ...seed, ...overrides }
}

/** ICU builds differ in which space they use before "am"/"pm"; compare plain spaces. */
const plain = (text: string) => text.replace(/[  ]/g, ' ')

const ALL_PASS: QcAnswers = {
  road_test: 'pass',
  no_warning_lights: 'pass',
  no_leaks: 'pass',
  fluid_levels: 'pass',
  complaint_resolved: 'pass',
}

describe('QC_CHECKLIST (D46, E-42)', () => {
  it('has the five default checks in the API order, with their labels', () => {
    expect(QC_CHECKLIST.map((item) => item.key)).toEqual([
      'road_test',
      'no_warning_lights',
      'no_leaks',
      'fluid_levels',
      'complaint_resolved',
    ])
    expect(QC_CHECKLIST.map((item) => item.label)).toEqual([
      'Road test',
      'No warning lights',
      'No leaks',
      'Fluid levels OK',
      'Customer complaint resolved',
    ])
  })
})

describe('the QC queue (QI-01)', () => {
  it('reads the seeded shop: BF-2026-003 waits, nothing is in progress, two passed', () => {
    expect(waitingJobs(bookings).map((b) => b.id)).toEqual(['bk-003'])
    expect(inProgressJobs(bookings, 'usr-sara')).toEqual([])
    expect(recentlyInspected(bookings).map((b) => b.id)).toEqual(['bk-005', 'bk-006'])
  })

  it('lists waiting cars oldest first (E-33 sort=status_changed_at)', () => {
    const newer = booking({ id: 'newer', updatedAt: '2026-10-10T08:00:00Z' })
    const older = booking({ id: 'older', updatedAt: '2026-10-10T07:00:00Z' })
    const picked = booking({ id: 'picked', status: 'QC_IN_PROGRESS' })
    expect(waitingJobs([newer, picked, older]).map((b) => b.id)).toEqual(['older', 'newer'])
  })

  it('lists your own inspections first, then the oldest', () => {
    const hinaOld = booking({
      id: 'hina-old',
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-hina',
      updatedAt: '2026-10-10T06:00:00Z',
    })
    const saraNew = booking({
      id: 'sara-new',
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-sara',
      updatedAt: '2026-10-10T09:00:00Z',
    })
    const hinaNew = booking({
      id: 'hina-new',
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-hina',
      updatedAt: '2026-10-10T08:00:00Z',
    })
    expect(inProgressJobs([hinaNew, saraNew, hinaOld], 'usr-sara').map((b) => b.id)).toEqual([
      'sara-new',
      'hina-old',
      'hina-new',
    ])
    // The Owner has no inspections of their own: oldest first.
    expect(inProgressJobs([hinaNew, saraNew, hinaOld], undefined).map((b) => b.id)).toEqual([
      'hina-old',
      'hina-new',
      'sara-new',
    ])
  })

  it('counts a failed job back in repair as recently inspected, newest result first', () => {
    const failed = booking({
      id: 'failed',
      status: 'IN_REPAIR',
      qcPassed: false,
      updatedAt: '2026-10-10T09:00:00Z',
    })
    const repairing = booking({ id: 'repairing', status: 'IN_REPAIR', qcPassed: undefined })
    expect(recentlyInspected([...bookings, failed, repairing]).map((b) => b.id)).toEqual([
      'failed',
      'bk-005',
      'bk-006',
    ])
    expect(recentlyInspected([...bookings, failed], 1).map((b) => b.id)).toEqual(['failed'])
  })
})

describe('QC states', () => {
  it('knows which statuses QC can act on', () => {
    expect(isInQc('QC_PENDING')).toBe(true)
    expect(isInQc('QC_IN_PROGRESS')).toBe(true)
    expect(isInQc('IN_REPAIR')).toBe(false)
    expect(isInQc('READY_FOR_PICKUP')).toBe(false)
  })

  it('reads the standing QC result', () => {
    expect(qcResultOf(booking({ status: 'READY_FOR_PICKUP' }))).toBe('passed')
    expect(qcResultOf(booking({ status: 'COMPLETED' }))).toBe('passed')
    expect(qcResultOf(booking({ status: 'IN_REPAIR', qcPassed: false }))).toBe('failed')
    expect(qcResultOf(booking({ status: 'IN_REPAIR' }))).toBeNull()
    expect(qcResultOf(booking({ status: 'QC_PENDING', qcPassed: false }))).toBeNull()
  })

  it('marks a job back in QC after a failed round as a re-test', () => {
    expect(isRetest(booking({ status: 'QC_PENDING', qcPassed: false }))).toBe(true)
    expect(isRetest(booking({ status: 'QC_IN_PROGRESS', qcPassed: false }))).toBe(true)
    expect(isRetest(booking({ status: 'QC_PENDING' }))).toBe(false)
    expect(isRetest(booking({ status: 'IN_REPAIR', qcPassed: false }))).toBe(false)
  })

  it('locks a picked job to its picker; an unrecorded picker leaves it open', () => {
    const picked = booking({ status: 'QC_IN_PROGRESS', qcInspectorId: 'usr-hina' })
    expect(pickedByOther(picked, 'usr-sara')).toBe(true)
    expect(pickedByOther(picked, 'usr-hina')).toBe(false)
    expect(pickedByOther(picked, undefined)).toBe(true)
    expect(pickedByOther(booking({ status: 'QC_IN_PROGRESS' }), 'usr-sara')).toBe(false)
    // A waiting job keeps the last round's picker until someone picks it again.
    expect(
      pickedByOther(booking({ status: 'QC_PENDING', qcInspectorId: 'usr-hina' }), 'usr-sara'),
    ).toBe(false)
  })

  it('keeps bookings to their shop (D20)', () => {
    expect(inShop(seed, LAHORE)).toBe(true)
    expect(inShop(seed, 'lahore-auto-care')).toBe(true)
    expect(inShop(seed, 'shop-raza-auto-works')).toBe(false)
  })
})

describe('the team', () => {
  it('finds the signed-in inspector by e-mail, whatever the case', () => {
    expect(memberIdFor({ email: 'sara.qc@bayflow.test' }, team)).toBe('usr-sara')
    expect(memberIdFor({ email: ' Hina.QC@bayflow.test ' }, team)).toBe('usr-hina')
    expect(memberIdFor({ email: 'someone@example.test' }, team)).toBeUndefined()
    expect(memberIdFor({ email: '' }, team)).toBeUndefined()
  })

  it('names a member', () => {
    expect(memberName('usr-sara', team)).toBe('Sara')
    expect(memberName('usr-nobody', team)).toBeNull()
    expect(memberName(undefined, team)).toBeNull()
  })
})

describe('Pass QC and Fail QC rules (D46, D92)', () => {
  it('needs every check answered, then every check passed', () => {
    expect(passBlocker({})).toBe('incomplete')
    expect(passBlocker({ ...ALL_PASS, no_leaks: undefined })).toBe('incomplete')
    expect(passBlocker({ ...ALL_PASS, no_leaks: 'fail', road_test: undefined })).toBe('incomplete')
    expect(passBlocker({ ...ALL_PASS, no_leaks: 'fail' })).toBe('failed')
    expect(passBlocker(ALL_PASS)).toBeNull()
  })

  it('counts progress', () => {
    expect(checklistProgress({})).toEqual({ total: 5, answered: 0, failed: 0 })
    expect(checklistProgress({ road_test: 'pass', no_leaks: 'fail' })).toEqual({
      total: 5,
      answered: 2,
      failed: 1,
    })
  })

  it('prefills the issue title from the failed checks, within 120 characters', () => {
    expect(issueTitleFrom(ALL_PASS)).toBe('')
    expect(issueTitleFrom({ ...ALL_PASS, no_leaks: 'fail' })).toBe('Failed: No leaks')
    expect(issueTitleFrom({ no_leaks: 'fail', road_test: 'fail' })).toBe(
      'Failed: Road test, No leaks',
    )
    const everything = issueTitleFrom({
      road_test: 'fail',
      no_warning_lights: 'fail',
      no_leaks: 'fail',
      fluid_levels: 'fail',
      complaint_resolved: 'fail',
    })
    expect(everything.length).toBeLessThanOrEqual(ISSUE_TITLE_MAX)
    expect(everything.startsWith('Failed: Road test, No warning lights')).toBe(true)
  })

  it('prefills the description from the failed checks’ notes and the inspection notes', () => {
    const answers: QcAnswers = { ...ALL_PASS, no_leaks: 'fail', fluid_levels: 'fail' }
    expect(
      issueDescriptionFrom(
        answers,
        {
          no_leaks: '  Oil at the drain plug ',
          road_test: 'ignored: it passed',
          fluid_levels: ' ',
        },
        'Road test on the ring road.',
      ),
    ).toBe('No leaks: Oil at the drain plug\nRoad test on the ring road.')
    expect(issueDescriptionFrom(ALL_PASS, {}, '   ')).toBe('')
  })

  it('needs a reason to fail: an issue title and a description', () => {
    expect(validateIssue('', '')).toEqual({
      title: 'Enter a short title for the issue.',
      description: 'Describe what the technician needs to fix.',
    })
    expect(validateIssue('   ', 'Re-torque the drain plug')).toEqual({
      title: 'Enter a short title for the issue.',
    })
    expect(validateIssue('Oil leak', '  ')).toEqual({
      description: 'Describe what the technician needs to fix.',
    })
    expect(validateIssue('x'.repeat(121), 'ok').title).toBe('Keep the title to 120 characters.')
    expect(validateIssue('Oil leak', 'Re-torque the drain plug')).toEqual({})
  })
})

describe('the failed-QC note on the booking', () => {
  it('keeps the first mock screens’ format and reads it back', () => {
    const notes = formatQcIssue('Oil leak at the drain plug', 'Re-torque the washer.')
    expect(notes).toBe('QC Issue: Oil leak at the drain plug — Re-torque the washer.')
    expect(parseQcIssue(notes)).toEqual({
      title: 'Oil leak at the drain plug',
      description: 'Re-torque the washer.',
    })
  })

  it('reads notes in another shape as a title', () => {
    expect(parseQcIssue(undefined)).toBeNull()
    expect(parseQcIssue('  ')).toBeNull()
    expect(parseQcIssue('Loose heat shield')).toEqual({
      title: 'Loose heat shield',
      description: '',
    })
    expect(parseQcIssue('QC Issue: Loose heat shield')).toEqual({
      title: 'Loose heat shield',
      description: '',
    })
  })
})

describe('time labels', () => {
  const now = new Date('2026-10-10T07:00:00Z') // 12:00 pm in Karachi

  it('says how long a car has waited', () => {
    expect(waitedFor('2026-10-10T06:59:30Z', now)).toBe('under a minute')
    expect(waitedFor('2026-10-10T06:35:00Z', now)).toBe('25 min')
    expect(waitedFor('2026-10-10T04:00:00Z', now)).toBe('3 h')
    expect(waitedFor('2026-10-10T03:50:00Z', now)).toBe('3 h 10 min')
    expect(waitedFor('2026-10-09T06:00:00Z', now)).toBe('1 day')
    expect(waitedFor('2026-10-08T06:00:00Z', now)).toBe('2 days')
    expect(waitedFor('not a date', now)).toBe('')
  })

  it('gives the time of day for today in the shop, else the date', () => {
    expect(plain(sinceLabel('2026-10-10T06:40:00Z', now, TZ))).toBe('11:40 am')
    expect(plain(sinceLabel('2026-10-09T06:40:00Z', now, TZ))).toBe('Fri, 9 Oct 2026 at 11:40 am')
    expect(sinceLabel('not a date', now, TZ)).toBe('')
  })

  it('says when the QC result was given', () => {
    const passed = booking({ status: 'READY_FOR_PICKUP', updatedAt: '2026-10-10T06:59:20Z' })
    expect(inspectedAgo(passed, now)).toBe('just now')
    expect(inspectedAgo({ ...passed, updatedAt: '2026-10-08T07:00:00Z' }, now)).toBe('2 days ago')
    expect(inspectedAgo({ ...passed, updatedAt: 'not a date' }, now)).toBe('')
  })

  it('falls back to Asia/Karachi for a missing or unknown timezone', () => {
    expect(shopTimeZone(undefined)).toBe('Asia/Karachi')
    expect(shopTimeZone('Not/AZone')).toBe('Asia/Karachi')
    expect(shopTimeZone('Asia/Dubai')).toBe('Asia/Dubai')
  })
})

describe('the inspection draft (R9)', () => {
  afterEach(() => {
    sessionStorage.clear()
  })

  it('keeps only known checks and values of the right type', () => {
    expect(parseDraft(null)).toEqual(EMPTY_DRAFT)
    expect(
      parseDraft({
        answers: { road_test: 'pass', no_leaks: 'fail', fluid_levels: 'maybe', unknown: 'pass' },
        itemNotes: { no_leaks: 'Drip', road_test: 3, unknown: 'x' },
        notes: 42,
      }),
    ).toEqual({
      answers: { road_test: 'pass', no_leaks: 'fail' },
      itemNotes: { no_leaks: 'Drip' },
      notes: '',
    })
  })

  it('round-trips through sessionStorage per booking and clears', () => {
    const draft = { answers: { road_test: 'pass' as const }, itemNotes: {}, notes: 'Dry road' }
    writeDraft('bk-003', draft)
    expect(readDraft('bk-003')).toEqual(draft)
    expect(readDraft('bk-001')).toEqual(EMPTY_DRAFT)
    clearDraft('bk-003')
    expect(readDraft('bk-003')).toEqual(EMPTY_DRAFT)
  })

  it('ignores a broken stored draft', () => {
    sessionStorage.setItem('bf:qc-draft:bk-003', '{not json')
    expect(readDraft('bk-003')).toEqual(EMPTY_DRAFT)
  })
})
