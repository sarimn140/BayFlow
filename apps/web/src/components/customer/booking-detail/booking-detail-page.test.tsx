import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerBookingDetailPage from '@/app/(customer)/bookings/[bookingId]/page'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  DEFAULT_USER,
  INITIAL_BOOKINGS,
  setCurrentUser,
  setStoredData,
  type MockBooking,
} from '@/lib/mock-data'

vi.mock('next/navigation', () => ({
  useParams: () => ({ bookingId: 'bk-001' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/bookings/bk-001',
}))

/** The seed bookings, with Ayesha's bk-001 changed, as this browser's stored data. */
function stage(changes: Partial<MockBooking>) {
  setStoredData(
    'bookings',
    INITIAL_BOOKINGS.map((booking) =>
      booking.id === 'bk-001'
        ? {
            ...booking,
            customerName: 'Ayesha Khan',
            customerEmail: 'ayesha.customer@bayflow.test',
            ...changes,
          }
        : booking,
    ),
  )
}

/** The page as the app renders it (the copy button's tooltip needs the provider). */
function renderPage() {
  return render(
    <TooltipProvider>
      <CustomerBookingDetailPage />
    </TooltipProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  setCurrentUser({
    ...DEFAULT_USER,
    name: 'Ayesha Khan',
    email: 'ayesha.customer@bayflow.test',
    role: 'CUSTOMER',
  })
})

describe('C-02 booking detail: the quality check', () => {
  it('never shows a failed QC round to the customer (D92)', () => {
    stage({
      status: 'IN_REPAIR',
      qcPassed: false,
      qcNotes: 'QC Issue: Oil leak at the drain plug — Re-torque the crush washer.',
    })
    renderPage()

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Quality check' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Oil leak at the drain plug/)).not.toBeInTheDocument()
    expect(screen.queryByText('Passed')).not.toBeInTheDocument()
  })

  it('shows the inspector’s notes under "Passed" once the car passed', () => {
    stage({
      status: 'READY_FOR_PICKUP',
      qcPassed: true,
      qcNotes: 'Brakes bedded in and road tested. No leaks.',
    })
    renderPage()

    expect(screen.getByRole('heading', { name: 'Quality check' })).toBeInTheDocument()
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('Brakes bedded in and road tested. No leaks.')).toBeInTheDocument()
  })
})

describe('C-02 booking detail: a booking the shop ended (T03, T22)', () => {
  /** SA-02's record of the decline or cancellation (`recordCancellation`). */
  function shopEnded(kind: 'decline' | 'cancel', reason: string) {
    setStoredData('sa_booking_records', {
      'bk-001': {
        estimateVersion: 1,
        saDraftOpen: false,
        activity: [],
        cancellation: {
          kind,
          reason,
          at: '2026-10-09T06:00:00.000Z',
          by: 'Bilal',
          role: 'SERVICE_ADVISOR',
          fromStatus: 'CONFIRMED',
          previousUpdatedAt: '2026-10-09T05:00:00.000Z',
        },
      },
    })
  }

  it('shows the shop’s reason for cancelling, without the advisor’s name (E-13)', () => {
    stage({ status: 'CANCELLED' })
    shopEnded('cancel', 'The part is discontinued; we can’t do this repair.')
    const { container } = renderPage()

    expect(screen.getByRole('heading', { name: 'This booking was cancelled' })).toBeInTheDocument()
    expect(container).toHaveTextContent('Lahore Auto Care cancelled it on')
    expect(screen.getByText('The shop’s reason')).toBeInTheDocument()
    expect(container).toHaveTextContent('The part is discontinued; we can’t do this repair.')
    expect(container).not.toHaveTextContent('Bilal')
  })

  it('says the shop declined a booking it could not take', () => {
    stage({ status: 'CANCELLED' })
    shopEnded('decline', 'Fully booked on that day.')
    const { container } = renderPage()

    expect(container).toHaveTextContent('Lahore Auto Care declined it on')
    expect(container).toHaveTextContent('Fully booked on that day.')
  })

  it('names no one when the shop has no record of ending it', () => {
    stage({ status: 'CANCELLED' })
    renderPage()

    expect(screen.getByRole('heading', { name: 'This booking was cancelled' })).toBeInTheDocument()
    expect(screen.queryByText('The shop’s reason')).not.toBeInTheDocument()
  })

  it('shows no reason while the booking is still open', () => {
    shopEnded('cancel', 'Stale record')
    const { container } = renderPage()

    expect(container).not.toHaveTextContent('Stale record')
  })
})
