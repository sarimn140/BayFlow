import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getBookingById,
  saveBooking,
  setCurrentUser,
  type CurrentUserSession,
} from '@/lib/mock-data'

import { QcInspection } from './qc-inspection'
import { QcQueue } from './qc-queue'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}))

const SHOP = 'shop-lahore-auto-care'
const QUEUE = `/pos/shops/${SHOP}/qc`
const inShop = { shopId: SHOP, shopName: 'Lahore Auto Care' }
const SARA: CurrentUserSession = {
  name: 'Sara',
  email: 'sara.qc@bayflow.test',
  role: 'QC_INSPECTOR',
  ...inShop,
}
const HINA: CurrentUserSession = { ...SARA, name: 'Hina', email: 'hina.qc@bayflow.test' }
const OWNER: CurrentUserSession = {
  name: 'Fatima Raza',
  email: 'fatima.owner@bayflow.test',
  role: 'OWNER',
  ...inShop,
}
const CHECKS = [
  'Road test',
  'No warning lights',
  'No leaks',
  'Fluid levels OK',
  'Customer complaint resolved',
]

/**
 * A row action's name, e.g. "Pick job BF-2026-003". The reference is an `sr-only` span starting
 * with a space; Chrome keeps that space, jsdom's name computation drops it.
 */
const action = (label: string, reference = 'BF-2026-003') =>
  new RegExp(`^${label}\\s?${reference}$`)

function answer(check: string, value: 'Pass' | 'Fail') {
  const group = screen.getByRole('radiogroup', { name: check })
  fireEvent.click(within(group).getByRole('radio', { name: value }))
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  push.mockReset()
  // jsdom has no layout: the "answer every check" focus move scrolls the first open check.
  Element.prototype.scrollIntoView = vi.fn()
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  vi.useRealTimers()
  // React (act, keys, update loops) and Radix (dialog titles) report problems here.
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('QI-02 inspection', () => {
  it('passes QC only when every check is answered and passed, then returns to the queue', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    setCurrentUser(SARA)
    render(<QcInspection shopId={SHOP} bookingId="bk-003" />)

    expect(screen.getByRole('heading', { level: 1, name: 'BF-2026-003' })).toBeVisible()
    const [passQc] = screen.getAllByRole('button', { name: 'Pass QC' })

    fireEvent.click(passQc!)
    expect(
      screen.getAllByText('Answer every check before you pass QC: 5 checks left.'),
    ).not.toHaveLength(0)
    expect(screen.getAllByText('Choose Pass or Fail.')).toHaveLength(5)
    expect(
      within(screen.getByRole('radiogroup', { name: 'Road test' })).getByRole('radio', {
        name: 'Pass',
      }),
    ).toHaveFocus()
    expect(getBookingById('bk-003')?.status).toBe('QC_PENDING')

    for (const check of CHECKS.slice(0, 4)) answer(check, 'Pass')
    answer('Customer complaint resolved', 'Fail')
    fireEvent.click(passQc!)
    expect(
      screen.getAllByText('1 check failed. Use Fail QC to send the car back to Imran.'),
    ).not.toHaveLength(0)
    expect(getBookingById('bk-003')?.status).toBe('QC_PENDING')

    answer('Customer complaint resolved', 'Pass')
    fireEvent.change(screen.getByRole('textbox', { name: 'Inspection notes' }), {
      target: { value: 'Dry after a 5 km drive.' },
    })
    fireEvent.click(passQc!)

    expect(getBookingById('bk-003')).toMatchObject({
      status: 'READY_FOR_PICKUP',
      qcPassed: true,
      qcNotes: 'Dry after a 5 km drive.',
    })
    expect(screen.getByText('QC passed')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).toBeNull()
    expect(sessionStorage.getItem('bf:qc-draft:bk-003')).toBeNull()

    expect(push).not.toHaveBeenCalled()
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(push).toHaveBeenCalledWith(QUEUE)
  })

  it('fails QC only with an issue title and description, prefilled from the failed checks', () => {
    setCurrentUser(SARA)
    render(<QcInspection shopId={SHOP} bookingId="bk-003" />)

    answer('No leaks', 'Fail')
    fireEvent.change(screen.getByRole('textbox', { name: /What did you find/ }), {
      target: { value: 'Oil at the drain plug' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Fail QC' })[0]!)

    const dialog = screen.getByRole('alertdialog', { name: 'Fail QC for BF-2026-003?' })
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    const title = within(dialog).getByRole('textbox', { name: 'Issue title' })
    const description = within(dialog).getByRole('textbox', { name: 'What needs fixing' })
    expect(title).toHaveValue('Failed: No leaks')
    expect(description).toHaveValue('No leaks: Oil at the drain plug')

    const confirm = within(dialog).getByRole('button', { name: 'Fail QC and return to Imran' })
    fireEvent.change(title, { target: { value: '  ' } })
    fireEvent.click(confirm)
    expect(within(dialog).getByText('Enter a short title for the issue.')).toBeInTheDocument()
    expect(title).toHaveFocus()
    expect(title).toHaveAttribute('aria-invalid', 'true')
    expect(getBookingById('bk-003')?.status).toBe('QC_PENDING')

    fireEvent.change(title, { target: { value: 'Oil leak at the drain plug' } })
    fireEvent.click(confirm)

    expect(getBookingById('bk-003')).toMatchObject({
      status: 'IN_REPAIR',
      qcPassed: false,
      qcNotes: 'QC Issue: Oil leak at the drain plug — No leaks: Oil at the drain plug',
    })
    expect(screen.getByText('QC failed: returned to Imran')).toBeInTheDocument()
    expect(screen.getByText('Oil leak at the drain plug')).toBeInTheDocument()
  })

  it('keeps the answers when the inspector comes back to the job (R9)', () => {
    setCurrentUser(SARA)
    const { unmount } = render(<QcInspection shopId={SHOP} bookingId="bk-003" />)
    answer('Road test', 'Pass')
    answer('No leaks', 'Fail')
    unmount()

    render(<QcInspection shopId={SHOP} bookingId="bk-003" />)
    const roadTest = screen.getByRole('radiogroup', { name: 'Road test' })
    expect(within(roadTest).getByRole('radio', { name: 'Pass' })).toBeChecked()
    const leaks = screen.getByRole('radiogroup', { name: 'No leaks' })
    expect(within(leaks).getByRole('radio', { name: 'Fail' })).toBeChecked()
  })

  it('locks a job to the inspector who picked it', () => {
    saveBooking({
      ...getBookingById('bk-003')!,
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-sara',
    })
    setCurrentUser(HINA)
    render(<QcInspection shopId={SHOP} bookingId="bk-003" />)

    expect(screen.getByText('Sara is inspecting this job')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Pass QC' })).toBeNull()
  })

  it('is read-only for the Owner (D16)', () => {
    setCurrentUser(OWNER)
    render(<QcInspection shopId={SHOP} bookingId="bk-003" />)

    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup')).toBeNull()
    expect(screen.queryByRole('button', { name: /Pass QC|Fail QC/ })).toBeNull()
  })

  it('shows the QC result of a job that passed, and nothing to pass again', () => {
    setCurrentUser(SARA)
    render(<QcInspection shopId={SHOP} bookingId="bk-006" />)

    expect(screen.getByText('This car passed QC')).toBeInTheDocument()
    expect(screen.getByText('The customer has collected it.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pass QC' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Back to QC queue' })).toHaveAttribute('href', QUEUE)
  })

  it("does not show another shop's job (D20)", () => {
    setCurrentUser(SARA)
    render(<QcInspection shopId="shop-raza-auto-works" bookingId="bk-003" />)

    expect(
      screen.getByRole('heading', { level: 1, name: "We couldn't find that job" }),
    ).toBeVisible()
  })
})

describe('QI-01 QC queue', () => {
  it('lets an inspector pick a waiting car, which then waits for them in progress', () => {
    setCurrentUser(HINA)
    render(<QcQueue shopId={SHOP} />)

    expect(screen.getByRole('heading', { level: 1, name: 'QC queue' })).toBeVisible()
    expect(screen.getByRole('link', { name: action('Inspect') })).toHaveAttribute(
      'href',
      `${QUEUE}/bk-003`,
    )
    fireEvent.click(screen.getByRole('button', { name: action('Pick job') }))

    expect(getBookingById('bk-003')).toMatchObject({
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-hina',
    })
    expect(screen.getByText('No cars waiting for a quality check')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: action('Continue inspection') })).toHaveAttribute(
      'href',
      `${QUEUE}/bk-003`,
    )
  })

  it("shows another inspector's job without letting you continue it", () => {
    saveBooking({
      ...getBookingById('bk-003')!,
      status: 'QC_IN_PROGRESS',
      qcInspectorId: 'usr-sara',
    })
    setCurrentUser(HINA)
    render(<QcQueue shopId={SHOP} />)

    expect(screen.getByText('Sara')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Continue inspection/ })).toBeNull()
    expect(screen.getByRole('link', { name: action('View') })).toBeInTheDocument()
  })

  it('is read-only for the Owner (D16)', () => {
    setCurrentUser(OWNER)
    render(<QcQueue shopId={SHOP} />)

    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pick job/ })).toBeNull()
    expect(screen.getByRole('link', { name: action('View') })).toBeInTheDocument()
  })
})
