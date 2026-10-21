import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CustomerBookingDetailPage from '@/app/(customer)/bookings/[bookingId]/page'
import { BookingConfirmation } from '@/components/booking/booking-confirmation'
import { MyBookings } from '@/components/customer/bookings-list/my-bookings'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  INITIAL_BOOKINGS,
  saveBooking,
  setCurrentUser,
  type CurrentUserSession,
} from '@/lib/mock-data'

const nav = vi.hoisted(() => ({ bookingId: '' }))

vi.mock('next/navigation', () => ({
  useParams: () => ({ bookingId: nav.bookingId }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/bookings',
}))

const customer = (name: string, email: string): CurrentUserSession => ({
  name,
  email,
  role: 'CUSTOMER',
  shopId: '',
  shopName: '',
})
const AYESHA = customer('Ayesha Khan', 'ayesha.customer@bayflow.test')
const ZAINAB = customer('Zainab Malik', 'zainab.customer@bayflow.test')
const BILAL: CurrentUserSession = {
  name: 'Bilal',
  email: 'bilal.sa@bayflow.test',
  role: 'SERVICE_ADVISOR',
  shopId: 'shop-lahore-auto-care',
  shopName: 'Lahore Auto Care',
}

/** A C-01 tab by its label and the count badge beside it. */
const tab = (label: string, count: number) =>
  screen.getByRole('tab', { name: new RegExp(`^${label}\\s*${count}$`) })

/** The references on the booking cards, top to bottom. */
const cardReferences = () =>
  screen
    .getAllByRole('heading', { level: 2 })
    .map((heading) => /BF-\d{4}-\d{3}/.exec(heading.textContent ?? '')?.[0])
    .filter(Boolean)

function openDetail(bookingId: string) {
  nav.bookingId = bookingId
  return render(
    <TooltipProvider>
      <CustomerBookingDetailPage />
    </TooltipProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('C-01 My bookings shows the signed-in account’s bookings only (D21)', () => {
  it('gives Ayesha her own bookings, the estimate waiting for her first (spec 11)', () => {
    setCurrentUser(AYESHA)
    render(<MyBookings />)
    expect(tab('Active', 3)).toBeInTheDocument()
    expect(tab('Past', 2)).toBeInTheDocument()
    // Her estimate first, then the car to collect, then the repair in progress.
    expect(cardReferences()).toEqual(['BF-2026-002', 'BF-2026-005', 'BF-2026-001'])
  })

  it('shows another customer none of Ayesha’s bookings', () => {
    setCurrentUser(ZAINAB)
    render(<MyBookings />)
    expect(cardReferences()).toEqual(['BF-2026-004'])
    expect(tab('Past', 0)).toBeInTheDocument()
  })

  it('shows staff only bookings they made as customers: none for Bilal', () => {
    setCurrentUser(BILAL)
    render(<MyBookings />)
    expect(screen.getByText('No bookings yet')).toBeInTheDocument()
    expect(screen.queryAllByRole('heading', { level: 2 })).toHaveLength(0)
  })

  it('matches the account’s e-mail in any case', () => {
    setCurrentUser({ ...AYESHA, email: 'Ayesha.Customer@BayFlow.test' })
    render(<MyBookings />)
    expect(tab('Active', 3)).toBeInTheDocument()
  })
})

describe('C-02 booking detail opens for its own customer only (D21, SM-17)', () => {
  it('opens Ayesha’s estimate for her', () => {
    setCurrentUser(AYESHA)
    openDetail('bk-002')
    expect(screen.getByRole('heading', { level: 1, name: 'BF-2026-002' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Approve/ }).length).toBeGreaterThan(0)
  })

  it.each([
    ['another customer', ZAINAB],
    ['a staff member', BILAL],
  ])('answers %s as if the booking did not exist', (_, viewer) => {
    setCurrentUser(viewer)
    const { container } = openDetail('bk-002')
    expect(screen.getByRole('heading', { level: 1, name: "We couldn't find that." })).toBeVisible()
    // Nothing of the booking leaks: no reference, vehicle, estimate or customer.
    const booking = INITIAL_BOOKINGS.find((b) => b.id === 'bk-002')!
    for (const text of [booking.reference, booking.licensePlate, booking.vehicleModel, 'Ayesha']) {
      expect(container).not.toHaveTextContent(text)
    }
  })

  it('reads the same for a reference typed into the URL and an unknown id', () => {
    setCurrentUser(ZAINAB)
    openDetail('BF-2026-005')
    expect(screen.getByRole('heading', { level: 1, name: "We couldn't find that." })).toBeVisible()
    openDetail('bk-404')
    expect(
      screen.getAllByRole('heading', { level: 1, name: "We couldn't find that." }),
    ).toHaveLength(2)
  })

  it('goes by the booking’s account e-mail, in any case', () => {
    setCurrentUser(ZAINAB)
    const booking = INITIAL_BOOKINGS.find((b) => b.id === 'bk-002')!
    saveBooking({ ...booking, customerEmail: 'Zainab.Customer@BayFlow.test' })
    openDetail('bk-002')
    expect(screen.getByRole('heading', { level: 1, name: 'BF-2026-002' })).toBeInTheDocument()
  })
})

describe('C-03 booking confirmed opens for its own customer only', () => {
  it('shows the booking to its customer', () => {
    setCurrentUser(ZAINAB)
    render(<BookingConfirmation bookingId="bk-004" newAccount={false} />)
    expect(screen.getByText('BF-2026-004')).toBeInTheDocument()
  })

  it('shows anyone else the not-found state, without the reference', () => {
    setCurrentUser(AYESHA)
    const { container } = render(<BookingConfirmation bookingId="bk-004" newAccount={false} />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'We couldn’t find that booking' }),
    ).toBeVisible()
    expect(container).not.toHaveTextContent('BF-2026-004')
  })
})
