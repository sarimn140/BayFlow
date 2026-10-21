import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import JobDetailPage from '@/app/(pos)/pos/shops/[shopId]/jobs/[bookingId]/page'
import JobsPage from '@/app/(pos)/pos/shops/[shopId]/jobs/page'
import {
  DEFAULT_USER,
  getBookingById,
  INITIAL_BOOKINGS,
  setCurrentUser,
  setStoredData,
  type MockBooking,
} from '@/lib/mock-data'

const SHOP = 'shop-lahore-auto-care'
const nav = vi.hoisted(() => ({ params: {} as Record<string, string> }))

vi.mock('next/navigation', () => ({
  useParams: () => nav.params,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => `/pos/shops/${nav.params.shopId}/jobs`,
}))

const TECHNICIAN = {
  ...DEFAULT_USER,
  name: 'Imran',
  email: 'imran.tech@bayflow.test',
  role: 'TECHNICIAN' as const,
}

/** The seed bookings, with one of them changed, as this browser's stored data. */
function stage(id: string, changes: Partial<MockBooking>) {
  setStoredData(
    'bookings',
    INITIAL_BOOKINGS.map((booking) => (booking.id === id ? { ...booking, ...changes } : booking)),
  )
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  setCurrentUser(TECHNICIAN)
  nav.params = { shopId: SHOP, bookingId: 'bk-001' }
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('T-02 job detail', () => {
  it('starts the estimate editor from the job saved in this browser, not the seed copy', async () => {
    stage('bk-001', {
      status: 'INSPECTING',
      estimateItems: [
        {
          id: 'est-saved',
          description: 'Saved brake fluid flush',
          type: 'LABOR',
          quantity: 1,
          unit_price: 1200,
          total: 1200,
        },
      ],
      estimateTotal: 1200,
    })

    // The server has no localStorage: it renders the seed job, so the page waits (skeleton).
    const html = renderToString(<JobDetailPage />)
    expect(html).not.toContain('Saved brake fluid flush')

    const container = document.createElement('div')
    container.innerHTML = html
    document.body.append(container)
    const onRecoverableError = vi.fn()
    const root = await act(async () =>
      hydrateRoot(container, <JobDetailPage />, { onRecoverableError }),
    )
    expect(onRecoverableError).not.toHaveBeenCalled()
    expect(within(container).getAllByText('Saved brake fluid flush').length).toBeGreaterThan(0)

    // A new line is added to the saved lines (the seed lines never come back).
    fireEvent.change(within(container).getByLabelText('Description'), {
      target: { value: 'Brake pads' },
    })
    fireEvent.click(within(container).getByRole('button', { name: 'Add line' }))
    const saved = getBookingById('bk-001')!
    expect(saved.estimateItems.map((item) => item.description)).toEqual([
      'Saved brake fluid flush',
      'Brake pads',
    ])
    expect(saved.estimateTotal).toBe(1200 + 2500)

    act(() => root.unmount())
    container.remove()
  })

  it('does not add a line without a description, and says why', () => {
    stage('bk-001', { status: 'INSPECTING' })
    render(<JobDetailPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Add line' }))
    expect(screen.getByText('Enter what the part or the labour is.')).toBeInTheDocument()
    expect(getBookingById('bk-001')!.estimateItems).toHaveLength(5)
  })

  it('removes a line while inspecting, saves the new total and keeps focus in the estimate', () => {
    stage('bk-001', { status: 'INSPECTING' })
    render(<JobDetailPage />)
    // Phones get stacked rows and wide screens a table: the first copy is enough here.
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove Oil Filter Cartridge' })[0]!)

    const saved = getBookingById('bk-001')!
    expect(saved.estimateItems.map((item) => item.description)).not.toContain(
      'Oil Filter Cartridge',
    )
    expect(saved.estimateTotal).toBe(17300 - 1500)
    expect(screen.queryAllByRole('button', { name: 'Remove Oil Filter Cartridge' })).toHaveLength(0)
    expect(document.activeElement).not.toBe(document.body)
  })

  it('blocks submitting an empty estimate, explains it and focuses the editor', () => {
    stage('bk-001', { status: 'INSPECTING', estimateItems: [], estimateTotal: 0 })
    render(<JobDetailPage />)
    fireEvent.click(screen.getAllByRole('button', { name: /submit estimate/i })[0]!)

    expect(screen.getByText('Add at least one part or labour line first.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(getBookingById('bk-001')!.status).toBe('INSPECTING')
    expect(document.activeElement).toBe(screen.getByLabelText('Description'))
  })

  it('submits the estimate and the notes to the service advisor after confirming', () => {
    stage('bk-001', { status: 'INSPECTING', inspectionNotes: '' })
    render(<JobDetailPage />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Inspection notes' }), {
      target: { value: 'Front pads at 2 mm.' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: /submit estimate/i })[0]!)

    const dialog = screen.getByRole('dialog', { name: 'Submit the estimate for BF-2026-001?' })
    fireEvent.click(within(dialog).getByRole('button', { name: /submit estimate/i }))

    const saved = getBookingById('bk-001')!
    expect(saved.status).toBe('ESTIMATE_REVIEW')
    expect(saved.inspectionNotes).toBe('Front pads at 2 mm.')
    expect(saved.estimateTotal).toBe(17300)
  })

  it('sends a repaired car to QC after confirming, and shows the QC issue it came back with', () => {
    stage('bk-001', {
      qcPassed: false,
      qcNotes: 'QC Issue: Oil seep at the drain plug — Re-torque the crush washer.',
    })
    render(<JobDetailPage />)
    expect(screen.getByText('QC sent this job back')).toBeInTheDocument()
    expect(screen.getByText('Oil seep at the drain plug')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /send back to qc/i })[0]!)
    const dialog = screen.getByRole('dialog', { name: 'Send BF-2026-001 to QC?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Send to QC' }))
    expect(getBookingById('bk-001')!.status).toBe('QC_PENDING')
  })

  it('keeps an approved estimate read-only during the repair', () => {
    render(<JobDetailPage />)
    expect(screen.getAllByText('Front Brake Pads Set').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /^remove /i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add line' })).toBeNull()
  })

  it('shows the Owner a read-only job (D16)', () => {
    setCurrentUser(DEFAULT_USER)
    stage('bk-001', { status: 'INSPECTING' })
    render(<JobDetailPage />)
    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit estimate/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Add line' })).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('says when the job does not exist', () => {
    nav.params = { shopId: SHOP, bookingId: 'bk-missing' }
    render(<JobDetailPage />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'We couldn’t find this job' }),
    ).toBeInTheDocument()
  })

  it('shows the service advisor’s note when a declined estimate comes back (T11)', () => {
    stage('bk-001', { status: 'INSPECTING' })
    setStoredData('sa_booking_records', {
      'bk-001': {
        estimateVersion: 3,
        saDraftOpen: false,
        activity: [
          {
            id: 'returned-1',
            kind: 'returned-to-technician',
            at: '2026-10-09T09:30:00.000Z',
            by: 'Bilal',
            role: 'SERVICE_ADVISOR',
            version: 3,
            note: 'Customer wants the pads only, not the rotor.',
          },
        ],
      },
    })
    render(<JobDetailPage />)
    const notice = screen.getByText('Estimate sent back to you').closest('[data-slot="alert"]')
    expect(notice).toHaveTextContent('The customer declined the estimate. Bilal sent it back on')
    expect(notice).toHaveTextContent('Customer wants the pads only, not the rotor.')
  })

  it('keeps the return note out of the way once the job has moved on', () => {
    setStoredData('sa_booking_records', {
      'bk-001': {
        estimateVersion: 3,
        saDraftOpen: false,
        activity: [
          {
            id: 'returned-1',
            kind: 'returned-to-technician',
            at: '2026-10-09T09:30:00.000Z',
            by: 'Bilal',
            role: 'SERVICE_ADVISOR',
            version: 3,
          },
        ],
      },
    })
    render(<JobDetailPage />)
    expect(screen.queryByText('Estimate sent back to you')).toBeNull()
  })
})

describe('T-02 assignee visibility (D21)', () => {
  it("does not open another technician's job, even by its id", () => {
    // BF-2026-002 is Hamza's job; Imran works in the same shop.
    nav.params = { shopId: SHOP, bookingId: 'bk-002' }
    const { container } = render(<JobDetailPage />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'We couldn’t find this job' }),
    ).toBeInTheDocument()
    expect(container).not.toHaveTextContent('BF-2026-002')
  })

  it("opens any technician's job for the Owner's read-only view (D16)", () => {
    setCurrentUser(DEFAULT_USER)
    nav.params = { shopId: SHOP, bookingId: 'bk-002' }
    render(<JobDetailPage />)
    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.getAllByText('BF-2026-002').length).toBeGreaterThan(0)
  })
})

describe('T-01 my jobs', () => {
  beforeEach(() => {
    nav.params = { shopId: SHOP }
  })

  it('starts an inspection inline, moves the job to Inspecting and keeps focus on it', () => {
    stage('bk-004', {
      status: 'ASSIGNED',
      assignedTechnicianId: 'usr-imran',
      assignedTechnicianName: 'Imran',
    })
    render(<JobsPage />)
    const toInspect = screen.getByRole('region', { name: /^to inspect/i })
    fireEvent.click(within(toInspect).getByRole('button', { name: /start inspection/i }))

    expect(getBookingById('bk-004')!.status).toBe('INSPECTING')
    expect(screen.queryByRole('region', { name: /^to inspect/i })).toBeNull()
    const inspecting = screen.getByRole('region', { name: /^inspecting/i })
    expect(
      within(inspecting).getByRole('heading', { name: '2022 Hyundai Tucson GLS' }),
    ).toBeVisible()
    expect(document.activeElement).toHaveTextContent('Continue inspection')
  })

  it('lists the job QC sent back first, with the issue', () => {
    stage('bk-003', {
      status: 'IN_REPAIR',
      qcPassed: false,
      qcNotes: 'QC Issue: Oil seep at the drain plug — Re-torque the crush washer.',
    })
    render(<JobsPage />)
    const [first] = screen.getAllByRole('region')
    expect(first).toHaveAccessibleName(/^QC sent back/)
    expect(within(first!).getByText('Oil seep at the drain plug')).toBeInTheDocument()
  })

  it('gives the Owner a read-only view without inline actions (D16)', () => {
    setCurrentUser(DEFAULT_USER)
    stage('bk-004', { status: 'ASSIGNED', assignedTechnicianId: 'usr-imran' })
    render(<JobsPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Technician jobs' })).toBeInTheDocument()
    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start inspection/i })).toBeNull()
  })

  it('lists only the jobs assigned to the signed-in technician (D21)', () => {
    // Imran has BF-2026-001, -003 and -006; Hamza has BF-2026-002 and -005.
    const { container, unmount } = render(<JobsPage />)
    expect(container).toHaveTextContent('BF-2026-001')
    expect(container).toHaveTextContent('BF-2026-003')
    expect(container).not.toHaveTextContent('BF-2026-002')
    expect(container).not.toHaveTextContent('BF-2026-005')
    unmount()

    setCurrentUser({ ...TECHNICIAN, name: 'Hamza', email: 'hamza.tech@bayflow.test' })
    const hamza = render(<JobsPage />)
    expect(hamza.container).toHaveTextContent('BF-2026-002')
    expect(hamza.container).not.toHaveTextContent('BF-2026-001')
    expect(hamza.container).not.toHaveTextContent('BF-2026-003')
  })

  it('shows the Owner every technician’s jobs, and one technician’s on request', () => {
    setCurrentUser(DEFAULT_USER)
    const { container } = render(<JobsPage />)
    expect(container).toHaveTextContent('BF-2026-001')
    expect(container).toHaveTextContent('BF-2026-002')

    fireEvent.click(screen.getByRole('radio', { name: 'Hamza' }))
    expect(container).toHaveTextContent('BF-2026-002')
    expect(container).not.toHaveTextContent('BF-2026-001')
  })
})

describe('T-02 tenant isolation (D20)', () => {
  it("does not open another shop's job, even by its id", () => {
    // BF-2026-009 is Raza Auto Works' job; Imran works at Lahore Auto Care.
    nav.params = { shopId: SHOP, bookingId: 'bk-009' }
    const { container } = render(<JobDetailPage />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'We couldn’t find this job' }),
    ).toBeInTheDocument()
    expect(container).not.toHaveTextContent('Hilux')
    expect(container).not.toHaveTextContent('BF-2026-009')
  })
})
