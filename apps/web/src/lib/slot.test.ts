import { describe, expect, it } from 'vitest'

import { slotSortKey } from './slot'

describe('slotSortKey', () => {
  it('sorts afternoon slots after morning ones', () => {
    const morning = slotSortKey({ scheduledDate: '2026-10-09', scheduledTime: '10:00 am' })
    const afternoon = slotSortKey({ scheduledDate: '2026-10-09', scheduledTime: '02:00 pm' })
    expect(morning).toBe('2026-10-09 10:00')
    expect(afternoon).toBe('2026-10-09 14:00')
    expect(afternoon > morning).toBe(true)
  })

  it('handles noon and midnight', () => {
    expect(slotSortKey({ scheduledDate: 'd', scheduledTime: '12:00 pm' })).toBe('d 12:00')
    expect(slotSortKey({ scheduledDate: 'd', scheduledTime: '12:30 am' })).toBe('d 00:30')
  })
})
