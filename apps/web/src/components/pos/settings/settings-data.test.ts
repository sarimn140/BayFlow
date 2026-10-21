import { describe, expect, it } from 'vitest'

import { hoursOn } from '@/lib/booking-slots'
import { INITIAL_SHOPS, type MockBooking, type MockShop } from '@/lib/mock-data'

import {
  copyMondayToOpenDays,
  defaultHours,
  hoursFitGrid,
  hoursFromShop,
  hoursToShop,
  sameHours,
  slotLengthLabel,
  slotTimeMinutes,
  timeOptions,
  timeZoneLabel,
  upcomingBookingCount,
  validateHours,
  validateProfile,
  validateSlots,
  type DayHours,
} from './settings-data'

const lahore = INITIAL_SHOPS.find((s) => s.id === 'shop-lahore-auto-care')!
const pindi = INITIAL_SHOPS.find((s) => s.id === 'shop-pindi-auto-garage')!

describe('validateProfile (ShopUpdate)', () => {
  const profile = { name: 'Lahore Auto Care', address: 'Plot 12', city: 'Lahore', phone: '' }

  it('requires name, address, city and phone', () => {
    expect(validateProfile({ name: ' ', address: '', city: '', phone: '' })).toEqual({
      name: 'Enter the shop name.',
      address: 'Enter the street address.',
      city: 'Enter the city.',
      phone: 'Enter a phone number customers can call.',
    })
  })

  it('applies the length limits 120 / 255 / 80', () => {
    const errors = validateProfile({
      name: 'n'.repeat(121),
      address: 'a'.repeat(256),
      city: 'c'.repeat(81),
      phone: '0300-1234567',
    })
    expect(Object.keys(errors)).toEqual(['name', 'address', 'city'])
    expect(
      validateProfile({
        name: 'n'.repeat(120),
        address: 'a'.repeat(255),
        city: 'c'.repeat(80),
        phone: '0300-1234567',
      }),
    ).toEqual({})
  })

  it('accepts the Phone type: 7–20 digits, spaces or hyphens and an optional leading +', () => {
    for (const phone of ['+92 42 35789011', '0300-1234567', '1234567'])
      expect(validateProfile({ ...profile, phone }).phone).toBeUndefined()
    for (const phone of ['123456', '+92 (42) 3578', '0300 123 4567 ext 2', '92+300'])
      expect(validateProfile({ ...profile, phone }).phone).toBe(
        'Use 7 to 20 digits, spaces or hyphens, with an optional leading +.',
      )
  })
})

describe('slots and capacity (D37)', () => {
  it('labels slot lengths in words', () => {
    expect(slotLengthLabel(15)).toBe('15 minutes')
    expect(slotLengthLabel(60)).toBe('1 hour')
    expect(slotLengthLabel(90)).toBe('1 hour 30 minutes')
    expect(slotLengthLabel(240)).toBe('4 hours')
  })

  it('takes a capacity from 1 to 50', () => {
    for (const capacity of ['1', '50', ' 2 '])
      expect(validateSlots({ duration: '60', capacity }, lahore)).toEqual({})
    expect(validateSlots({ duration: '60', capacity: '' }, lahore).capacity).toBe(
      'Enter how many cars you can take in one slot.',
    )
    for (const capacity of ['0', '51', '2.5', 'two'])
      expect(validateSlots({ duration: '60', capacity }, lahore).capacity).toBe(
        'Enter a whole number from 1 to 50.',
      )
  })

  it('needs a new slot length that keeps the saved hours on its grid', () => {
    // 09:00–18:00 lies on the 30, 45 and 90-minute grids, not on the 120-minute one.
    for (const duration of ['30', '45', '90'])
      expect(validateSlots({ duration, capacity: '2' }, lahore).duration).toBeUndefined()
    expect(validateSlots({ duration: '120', capacity: '2' }, lahore).duration).toBe(
      "Your working hours don't fit the new slot length — adjust them first.",
    )
    expect(validateSlots({ duration: '50', capacity: '2' }, lahore).duration).toBe(
      'Choose a slot length.',
    )
  })

  it('never re-checks an unchanged length, even one off the 15-minute steps', () => {
    const legacy: MockShop = { ...lahore, slot_duration_minutes: 50 }
    expect(validateSlots({ duration: '50', capacity: '3' }, legacy)).toEqual({})
  })

  it('names the default time zone (D38)', () => {
    expect(timeZoneLabel('Asia/Karachi')).toBe('Asia/Karachi (PKT, UTC+5)')
    expect(timeZoneLabel('Asia/Dubai')).toBe('Asia/Dubai')
  })
})

describe('upcomingBookingCount (has_future_bookings)', () => {
  // 05:42 in Karachi on Saturday 10 October 2026.
  const now = new Date('2026-10-10T00:42:00Z')
  const booking = (scheduledDate: string, scheduledTime: string, status = 'CONFIRMED') =>
    ({ scheduledDate, scheduledTime, status }) as Pick<
      MockBooking,
      'status' | 'scheduledDate' | 'scheduledTime'
    >

  it('counts non-cancelled bookings whose slot starts after now, in shop time', () => {
    expect(upcomingBookingCount([booking('2026-10-10', '09:00 am')], now, 'Asia/Karachi')).toBe(1)
    expect(upcomingBookingCount([booking('2026-10-10', '05:00 am')], now, 'Asia/Karachi')).toBe(0)
    expect(upcomingBookingCount([booking('2026-10-11', '12:00 am')], now, 'Asia/Karachi')).toBe(1)
    expect(upcomingBookingCount([booking('2026-10-09', '06:00 pm')], now, 'Asia/Karachi')).toBe(0)
    expect(
      upcomingBookingCount([booking('2026-10-12', '10:00 am', 'CANCELLED')], now, 'Asia/Karachi'),
    ).toBe(0)
  })

  it('reads the stored slot times', () => {
    expect(slotTimeMinutes('10:00 am')).toBe(600)
    expect(slotTimeMinutes('12:00 pm')).toBe(720)
    expect(slotTimeMinutes('12:30 am')).toBe(30)
    expect(slotTimeMinutes('02:00 pm')).toBe(840)
    expect(slotTimeMinutes('later')).toBeNull()
  })
})

describe('opening hours', () => {
  it('reads seven rows, Monday first, and writes the shape the booking wizard reads', () => {
    const rows = hoursFromShop(lahore)
    expect(rows.map((r) => r.day)).toEqual([
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ])
    expect(rows[0]).toEqual({ day: 'Monday', open: true, opens: '09:00', closes: '18:00' })
    expect(rows[6]).toEqual({ day: 'Sunday', open: false, opens: '', closes: '' })
    expect(hoursToShop(rows)).toEqual(lahore.working_hours)

    // Pindi opens on Sunday afternoons; the wizard reads the saved rows back.
    const saved = { working_hours: hoursToShop(hoursFromShop(pindi)) }
    expect(hoursOn(saved, '2026-10-11')).toEqual({ open: 600, close: 840 })
    expect(hoursOn(saved, '2026-10-12')).toEqual({ open: 540, close: 1080 })
  })

  it('treats a missing day as closed and unreadable hours as unset', () => {
    const rows = hoursFromShop({ working_hours: [{ day: 'Monday', hours: '9am till late' }] })
    expect(rows[0]).toEqual({ day: 'Monday', open: true, opens: '', closes: '' })
    expect(rows.slice(1).every((r) => !r.open)).toBe(true)
  })

  it('checks each open day: both times, on the grid, closing after opening', () => {
    const day = (opens: string, closes: string): DayHours => ({
      day: 'Monday',
      open: true,
      opens,
      closes,
    })
    expect(validateHours([day('09:00', '18:00')], 60)).toEqual({})
    expect(validateHours([day('', '18:00')], 60).Monday).toBe(
      'Choose an opening and a closing time.',
    )
    expect(validateHours([day('09:30', '18:00')], 60).Monday).toBe(
      'Use times on your 60-minute slot grid.',
    )
    expect(validateHours([day('18:00', '09:00')], 60).Monday).toBe(
      'Closing time must be after opening time.',
    )
    expect(validateHours([day('09:00', '09:00')], 60).Monday).toBe(
      'Closing time must be after opening time.',
    )
    expect(validateHours([{ ...day('', ''), open: false }], 60)).toEqual({})
  })

  it('knows whether saved hours fit a slot length', () => {
    expect(hoursFitGrid(lahore.working_hours, 45)).toBe(true)
    expect(hoursFitGrid(lahore.working_hours, 120)).toBe(false)
  })

  it('offers grid times only, keeping an off-grid current value so it can be fixed', () => {
    const opens = timeOptions(60, '09:00', 'opens')
    expect(opens).toHaveLength(24)
    expect(opens[0]).toEqual({ value: '00:00', label: '12:00 am' })
    expect(opens[9]).toEqual({ value: '09:00', label: '09:00 am' })
    const closes = timeOptions(60, '18:00', 'closes')
    expect(closes).toHaveLength(23)
    expect(closes[0]?.value).toBe('01:00')
    expect(closes.at(-1)).toEqual({ value: '23:00', label: '11:00 pm' })
    const withLegacy = timeOptions(60, '09:30', 'opens').map((o) => o.value)
    expect(withLegacy.slice(9, 12)).toEqual(['09:00', '09:30', '10:00'])
    expect(timeOptions(15, '', 'opens')).toHaveLength(96)
  })

  it('opens a day with Monday’s hours, or 09:00–18:00 moved onto the grid', () => {
    expect(defaultHours(hoursFromShop(lahore), 60)).toEqual({ opens: '09:00', closes: '18:00' })
    const allClosed = hoursFromShop(lahore).map((r) => ({ ...r, open: false }))
    expect(defaultHours(allClosed, 60)).toEqual({ opens: '09:00', closes: '18:00' })
    expect(defaultHours(allClosed, 120)).toEqual({ opens: '10:00', closes: '18:00' })
    expect(defaultHours(allClosed, 135)).toEqual({ opens: '09:00', closes: '18:00' })
  })

  it('copies Monday to the other open days only', () => {
    const rows = hoursFromShop(lahore).map((r, i) =>
      i === 0 ? { ...r, opens: '10:00', closes: '19:00' } : r,
    )
    const copied = copyMondayToOpenDays(rows)
    expect(copied.slice(0, 6).every((r) => r.opens === '10:00' && r.closes === '19:00')).toBe(true)
    expect(copied[6]).toEqual(rows[6])
  })

  it('ignores the times of closed days when comparing', () => {
    const saved = hoursFromShop(lahore)
    const edited = saved.map((r) =>
      r.day === 'Sunday' ? { ...r, opens: '10:00', closes: '14:00' } : r,
    )
    expect(sameHours(saved, edited)).toBe(true)
    expect(
      sameHours(
        saved,
        edited.map((r) => (r.day === 'Sunday' ? { ...r, open: true } : r)),
      ),
    ).toBe(false)
  })
})
