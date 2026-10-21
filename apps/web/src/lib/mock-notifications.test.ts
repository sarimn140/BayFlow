import { beforeEach, describe, expect, it } from 'vitest'

import { resolveMockSession } from './mock-auth'
import { INITIAL_BOOKINGS, INITIAL_TEAM, type MockBooking } from './mock-data'
import {
  deriveNotifications,
  getReadNotificationIds,
  markNotificationsRead,
} from './mock-notifications'

const forEmail = (email: string, bookings: ReadonlyArray<MockBooking> = INITIAL_BOOKINGS) =>
  deriveNotifications(resolveMockSession(email), bookings, INITIAL_TEAM)

const types = (email: string) => forEmail(email).map((n) => n.type)

describe('deriveNotifications (glossary §6 recipients, D67 links)', () => {
  it('gives the Service Advisor the hand-offs addressed to "SAs of the shop"', () => {
    const items = forEmail('bilal.sa@bayflow.test')
    expect(items.length).toBeGreaterThan(0)
    const saTypes = [
      'BOOKING_CREATED',
      'ESTIMATE_SUBMITTED',
      'ESTIMATE_APPROVED',
      'ESTIMATE_REJECTED',
      'QC_PASSED',
    ]
    for (const n of items) {
      expect(saTypes).toContain(n.type)
      expect(n.link).toMatch(/^\/pos\/shops\/[^/]+\/bookings\/[^/]+$/)
    }
  })

  it('sends the Owner nothing while the shop has a Service Advisor (D26)', () => {
    expect(forEmail('fatima.owner@bayflow.test')).toEqual([])
  })

  it('falls back to the Owner when the shop has no Service Advisor', () => {
    const owner = resolveMockSession('fatima.owner@bayflow.test')
    const noSa = INITIAL_TEAM.filter((m) => m.role !== 'SERVICE_ADVISOR')
    expect(deriveNotifications(owner, INITIAL_BOOKINGS, noSa).length).toBeGreaterThan(0)
  })

  it('gives each workshop role only its own hand-offs, linked to its own screen', () => {
    for (const n of forEmail('imran.tech@bayflow.test')) {
      expect(['TECHNICIAN_ASSIGNED', 'PARTS_READY', 'QC_FAILED']).toContain(n.type)
      expect(n.link).toMatch(/\/jobs\//)
    }
    for (const n of forEmail('usman.parts@bayflow.test')) {
      expect(n.type).toBe('PARTS_NEEDED')
      expect(n.link).toMatch(/\/parts\//)
    }
    for (const n of forEmail('sara.qc@bayflow.test')) {
      expect(n.type).toBe('QC_REQUESTED')
      expect(n.link).toMatch(/\/qc\//)
    }
    expect(types('sara.qc@bayflow.test')).toContain('QC_REQUESTED')
  })

  it("gives a customer only their own bookings' updates, linked to the customer view", () => {
    const items = forEmail('ayesha.customer@bayflow.test')
    expect(items.length).toBeGreaterThan(0)
    const ayeshaBookings = new Set(
      INITIAL_BOOKINGS.filter((b) => b.customerEmail === 'ayesha.customer@bayflow.test').map(
        (b) => b.reference,
      ),
    )
    for (const n of items) {
      expect(ayeshaBookings.has(n.reference)).toBe(true)
      expect(n.link).toMatch(/^\/bookings\/[^/]+$/)
    }
  })

  it('never gives one customer the updates of another with the same name (D21)', () => {
    const namesake = { ...resolveMockSession('ayesha.customer@bayflow.test') }
    namesake.email = 'ayesha.k@example.pk'
    expect(deriveNotifications(namesake, INITIAL_BOOKINGS, INITIAL_TEAM)).toEqual([])
  })

  it('gives staff nothing from a shop they are not a member of, whatever the session claims', () => {
    const bilal = resolveMockSession('bilal.sa@bayflow.test')
    const elsewhere = { ...bilal, shopId: 'shop-clifton-car-clinic', shopName: 'Clifton' }
    expect(deriveNotifications(elsewhere, INITIAL_BOOKINGS, INITIAL_TEAM)).toEqual([])
    // Clifton Car Clinic's own Service Advisor gets its new booking.
    expect(types('sa.clifton-car-clinic@bayflow.test')).toEqual(['BOOKING_CREATED'])
  })

  it('lists newest first, with one stable id per hand-off', () => {
    const items = forEmail('bilal.sa@bayflow.test')
    const times = items.map((n) => n.createdAt)
    expect([...times].sort().reverse()).toEqual(times)
    expect(new Set(items.map((n) => n.id)).size).toBe(items.length)
  })

  it('adds the confirmation once a pending booking is confirmed', () => {
    const pending = {
      ...INITIAL_BOOKINGS[0]!,
      customerName: 'Ayesha Khan',
      status: 'PENDING' as const,
    }
    const before = forEmail('ayesha.customer@bayflow.test', [pending])
    const after = forEmail('ayesha.customer@bayflow.test', [{ ...pending, status: 'CONFIRMED' }])
    expect(before.map((n) => n.type)).not.toContain('BOOKING_CONFIRMED')
    expect(after.map((n) => n.type)).toContain('BOOKING_CONFIRMED')
  })
})

describe('read state after seeding (spec 11 "What each demo account sees on first login")', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  const unread = (email: string) => {
    const read = new Set(getReadNotificationIds())
    return forEmail(email)
      .filter((n) => !read.has(n.id))
      .map((n) => `${n.type} ${n.reference}`)
  }

  it('leaves unread only what waits on each demo account', () => {
    expect(unread('ayesha.customer@bayflow.test')).toEqual(['ESTIMATE_SENT BF-2026-002'])
    expect(unread('bilal.sa@bayflow.test').sort()).toEqual([
      'BOOKING_CREATED BF-2026-004',
      'QC_PASSED BF-2026-005',
    ])
    expect(unread('imran.tech@bayflow.test')).toEqual(['PARTS_READY BF-2026-001'])
    expect(unread('hamza.tech@bayflow.test')).toEqual([])
    expect(unread('sara.qc@bayflow.test')).toEqual(['QC_REQUESTED BF-2026-003'])
    expect(unread('hina.qc@bayflow.test')).toEqual(['QC_REQUESTED BF-2026-003'])
    expect(unread('fatima.owner@bayflow.test')).toEqual([])
  })

  it("gives each other shop's Service Advisor its new booking, and Lyallpur Motors nothing", () => {
    expect(unread('sa.raza-auto-works@bayflow.test')).toEqual(['BOOKING_CREATED BF-2026-008'])
    expect(unread('sa.clifton-car-clinic@bayflow.test')).toEqual(['BOOKING_CREATED BF-2026-010'])
    expect(unread('sa.margalla-motor-works@bayflow.test')).toEqual(['BOOKING_CREATED BF-2026-011'])
    expect(unread('sa.pindi-auto-garage@bayflow.test')).toEqual(['BOOKING_CREATED BF-2026-012'])
    expect(unread('sa.lyallpur-motors@bayflow.test')).toEqual([])
  })

  it('keeps the seed read state when the user marks more as read', () => {
    markNotificationsRead(['ESTIMATE_SENT:bk-002'])
    expect(unread('ayesha.customer@bayflow.test')).toEqual([])
    expect(unread('bilal.sa@bayflow.test')).toHaveLength(2)
  })
})
