import { beforeEach, describe, expect, it } from 'vitest'

import { bookingHistory } from './mock-booking-history'
import { INITIAL_BOOKINGS, INITIAL_TEAM, setStoredData, type MockBooking } from './mock-data'

const seed = (id: string) => INITIAL_BOOKINGS.find((b) => b.id === id)!

/** Who did each step, as "ROLE name". */
const actors = (booking: MockBooking) =>
  [...new Set(bookingHistory(booking).map((step) => `${step.actorRole} ${step.actorName}`))].sort()

beforeEach(() => {
  localStorage.clear()
})

describe('booking history actors (the booking’s own shop, D20)', () => {
  it('credits Lahore Auto Care’s team for its bookings', () => {
    expect(actors(seed('bk-005'))).toEqual([
      'CUSTOMER Ayesha Khan',
      'PARTS_PERSON Usman',
      'QC_INSPECTOR Sara',
      'SERVICE_ADVISOR Bilal',
      'TECHNICIAN Hamza',
    ])
  })

  it('credits another shop’s own staff, never Lahore Auto Care’s', () => {
    expect(actors(seed('bk-009'))).toEqual([
      'CUSTOMER Kamran Shah',
      'PARTS_PERSON Faisal Javed',
      'QC_INSPECTOR Rabia Saeed',
      'SERVICE_ADVISOR Adeel Anwar',
      'TECHNICIAN Naveed Akhtar',
    ])
    expect(actors(seed('bk-013'))).toContain('SERVICE_ADVISOR Mariam Yousaf')
  })

  it('lets the Owner act as Service Advisor where the shop has none (D26)', () => {
    setStoredData(
      'team',
      INITIAL_TEAM.filter(
        (m) => !(m.shopId === 'shop-lyallpur-motors' && m.role === 'SERVICE_ADVISOR'),
      ),
    )
    // A copy: the history of the seed object itself may already be memoised.
    expect(actors({ ...seed('bk-013') })).toContain('SERVICE_ADVISOR Khalid Chaudhry')
  })
})
