import { describe, expect, it } from 'vitest'

import {
  addDays,
  formatDateKey,
  freeSlots,
  hoursOn,
  minutesInZone,
  openDates,
  slotLabel,
  weekdayOf,
} from './booking-slots'

const shop = {
  id: 'shop-x',
  slot_duration_minutes: 60,
  slot_capacity: 2,
  working_hours: [
    { day: 'Monday', hours: '09:00 - 18:00' },
    { day: 'Tuesday', hours: '09:00 - 18:00' },
    { day: 'Wednesday', hours: '09:00 - 18:00' },
    { day: 'Thursday', hours: '09:00 - 18:00' },
    { day: 'Friday', hours: '09:00 - 18:00' },
    { day: 'Saturday', hours: '10:00 - 14:00' },
    { day: 'Sunday', hours: 'Closed', is_closed: true },
  ],
}

// 2026-10-12 is a Monday.
const MONDAY = '2026-10-12'

describe('calendar arithmetic', () => {
  it('names weekdays with Monday first and crosses month ends', () => {
    expect(weekdayOf(MONDAY)).toBe('Monday')
    expect(weekdayOf('2026-10-18')).toBe('Sunday')
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
  })

  it('formats a date key without shifting the day', () => {
    expect(formatDateKey(MONDAY)).toBe('Mon 12 Oct')
    expect(formatDateKey(MONDAY, true)).toBe('Mon 12 Oct 2026')
  })

  it('labels slots like the stored bookings', () => {
    expect(slotLabel(9 * 60)).toBe('09:00 am')
    expect(slotLabel(12 * 60)).toBe('12:00 pm')
    expect(slotLabel(14 * 60 + 30)).toBe('02:30 pm')
    expect(slotLabel(0)).toBe('12:00 am')
  })

  it('reads the time of day in the shop timezone', () => {
    // 05:30 UTC is 10:30 in Karachi (UTC+5).
    expect(minutesInZone(new Date('2026-10-12T05:30:00Z'), 'Asia/Karachi')).toBe(10 * 60 + 30)
  })
})

describe('opening days', () => {
  it('knows closed days and parses hours', () => {
    expect(hoursOn(shop, MONDAY)).toEqual({ open: 540, close: 1080 })
    expect(hoursOn(shop, '2026-10-18')).toBeNull()
  })

  it('offers today to today + 30, skipping closed days', () => {
    const dates = openDates(shop, MONDAY)
    expect(dates[0]).toBe(MONDAY)
    expect(dates.at(-1)! <= addDays(MONDAY, 30)).toBe(true)
    expect(dates).not.toContain('2026-10-18')
    expect(dates).toHaveLength(31 - 4) // 18 and 25 Oct, 1 and 8 Nov are Sundays
  })
})

describe('free slots', () => {
  const ctx = { todayKey: MONDAY, nowMinutes: 0, bookings: [] }

  it('builds the grid from opening time, ending before closing', () => {
    const slots = freeSlots(shop, '2026-10-17', ctx) // Saturday 10:00–14:00
    expect(slots.map((s) => s.time)).toEqual(['10:00 am', '11:00 am', '12:00 pm', '01:00 pm'])
    expect(slots.every((s) => s.remaining === 2)).toBe(true)
  })

  it('drops slots that have started today', () => {
    const slots = freeSlots(shop, MONDAY, { ...ctx, nowMinutes: 10 * 60 })
    expect(slots[0]!.time).toBe('11:00 am')
  })

  it('counts bookings against capacity and leaves out full slots', () => {
    const booking = (time: string, status = 'CONFIRMED') => ({
      shopId: 'shop-x',
      scheduledDate: '2026-10-13',
      scheduledTime: time,
      status: status as never,
    })
    const slots = freeSlots(shop, '2026-10-13', {
      ...ctx,
      bookings: [
        booking('09:00 am'),
        booking('09:00 am'),
        booking('10:00 am'),
        booking('11:00 am', 'CANCELLED'),
        { ...booking('10:00 am'), shopId: 'another-shop' },
      ],
    })
    expect(slots.find((s) => s.time === '09:00 am')).toBeUndefined()
    expect(slots.find((s) => s.time === '10:00 am')!.remaining).toBe(1)
    expect(slots.find((s) => s.time === '11:00 am')!.remaining).toBe(2)
  })

  it('is empty on closed days and outside the window', () => {
    expect(freeSlots(shop, '2026-10-18', ctx)).toEqual([])
    expect(freeSlots(shop, '2026-10-11', ctx)).toEqual([])
    expect(freeSlots(shop, addDays(MONDAY, 31), ctx)).toEqual([])
  })
})
