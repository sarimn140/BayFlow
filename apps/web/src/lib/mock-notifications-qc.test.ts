import { describe, expect, it } from 'vitest'

import { resolveMockSession } from './mock-auth'
import { INITIAL_BOOKINGS, INITIAL_TEAM, type MockBooking } from './mock-data'
import { deriveNotifications, qcIssueTitle } from './mock-notifications'

describe('QC_FAILED: the technician is told the issue title only (D92)', () => {
  it('quotes the title, never the description', () => {
    const failed: MockBooking = {
      ...INITIAL_BOOKINGS.find((b) => b.id === 'bk-001')!,
      status: 'IN_REPAIR',
      assignedTechnicianName: 'Imran',
      qcPassed: false,
      qcNotes: 'QC Issue: Oil leak at the drain plug — Re-torque the crush washer.',
    }
    const qcFailed = deriveNotifications(
      resolveMockSession('imran.tech@bayflow.test'),
      [failed],
      INITIAL_TEAM,
    ).filter((n) => n.type === 'QC_FAILED')
    expect(qcFailed).toHaveLength(1)
    expect(qcFailed[0]!.body).toBe('LEA-22-4589: Oil leak at the drain plug.')
    expect(qcFailed[0]!.link).toBe('/pos/shops/shop-lahore-auto-care/jobs/bk-001')
  })
})

describe('qcIssueTitle (the FAIL_QC note, D92)', () => {
  it('reads the title out of the stored "QC Issue: {title} — {description}"', () => {
    expect(qcIssueTitle('QC Issue: Loose heat shield — Refit both bolts.')).toBe(
      'Loose heat shield',
    )
    expect(qcIssueTitle('QC Issue: Loose heat shield')).toBe('Loose heat shield')
  })

  it('uses notes in another shape whole, and has nothing for empty notes', () => {
    expect(qcIssueTitle('Brake pedal feels soft')).toBe('Brake pedal feels soft')
    expect(qcIssueTitle('  ')).toBeNull()
    expect(qcIssueTitle(undefined)).toBeNull()
  })
})
