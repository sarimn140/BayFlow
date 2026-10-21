import { describe, expect, it } from 'vitest'

import { IN_PROGRESS_STATUSES, SA_ACTION_STATUSES, isLowStock } from './kpis'
import { BOOKING_STATUSES } from './status'

describe('KPI status groups (API reporting/domain/kpis.py)', () => {
  it('put every non-final status in exactly one group', () => {
    for (const status of BOOKING_STATUSES) {
      const groups = [SA_ACTION_STATUSES.has(status), IN_PROGRESS_STATUSES.has(status)].filter(
        Boolean,
      ).length
      expect(groups, status).toBe(status === 'COMPLETED' || status === 'CANCELLED' ? 0 : 1)
    }
  })

  it("count an approved estimate as the advisor's move and a sent one as in progress", () => {
    expect(SA_ACTION_STATUSES.has('ESTIMATE_APPROVED')).toBe(true)
    expect(IN_PROGRESS_STATUSES.has('AWAITING_CUSTOMER')).toBe(true)
  })
})

describe('isLowStock (D45)', () => {
  it('compares what is available, not what is on hand', () => {
    expect(isLowStock({ on_hand: 10, reserved: 6, reorder_level: 5 })).toBe(true)
    expect(isLowStock({ on_hand: 10, reserved: 0, reorder_level: 5 })).toBe(false)
    expect(isLowStock({ on_hand: 5, reserved: 0, reorder_level: 5 })).toBe(true)
  })
})
