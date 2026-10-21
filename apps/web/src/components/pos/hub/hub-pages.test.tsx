import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ComponentType } from 'react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PosHubPage from '@/app/(pos)/pos/page'
import CreateShopPage from '@/app/(pos)/pos/shops/new/page'
import ShopsSummaryPage from '@/app/(pos)/pos/summary/page'
import {
  DEFAULT_USER,
  getCurrentUser,
  getShops,
  getTeamMembers,
  setCurrentUser,
  setStoredData,
  type CurrentUserSession,
} from '@/lib/mock-data'

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }))

vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/pos',
}))

// jsdom has no ResizeObserver, and Radix's Switch measures itself with one.
vi.stubGlobal(
  'ResizeObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
)

const LAHORE = 'shop-lahore-auto-care'
const RAZA = 'shop-raza-auto-works'

/** Fatima (Owner of Lahore Auto Care and Raza Auto Works), with any changes. */
function signIn(changes: Partial<CurrentUserSession> = {}) {
  setCurrentUser({ ...DEFAULT_USER, ...changes })
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  router.push.mockReset()
  router.replace.mockReset()
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  vi.useRealTimers()
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('S-02 POS hub', () => {
  it.each([
    ['OWNER', 'overview'],
    ['SERVICE_ADVISOR', 'bookings'],
    ['TECHNICIAN', 'jobs'],
    ['PARTS_PERSON', 'parts'],
    ['QC_INSPECTOR', 'qc'],
    ['CUSTOMER', 'overview'],
  ] as const)('sends a %s with a current shop to /%s, behind a skeleton', (role, segment) => {
    signIn({ role })
    render(<PosHubPage />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'Opening your workspace' }),
    ).toBeInTheDocument()
    expect(router.replace).toHaveBeenCalledWith(`/pos/shops/${LAHORE}/${segment}`)
  })

  it('lists the shops of someone without a current shop, each opening their role home', () => {
    signIn({ shopId: '', shopName: '' })
    render(<PosHubPage />)
    expect(router.replace).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { level: 1, name: 'Your shops' })).toBeInTheDocument()
    const shops = within(screen.getByRole('list', { name: 'Your shops' })).getAllByRole('link')
    expect(shops.map((link) => link.getAttribute('href'))).toEqual([
      `/pos/shops/${LAHORE}/overview`,
      `/pos/shops/${RAZA}/overview`,
    ])
    expect(shops[0]).toHaveTextContent('Lahore Auto Care')
    expect(shops[0]).toHaveTextContent('Owner')
    expect(screen.getByRole('link', { name: 'Create shop' })).toHaveAttribute(
      'href',
      '/pos/shops/new',
    )
    expect(screen.getByRole('link', { name: 'All shops summary' })).toHaveAttribute(
      'href',
      '/pos/summary',
    )
  })

  it('shows a staff member only their own shop, with their role', () => {
    signIn({ name: 'Bilal', email: 'bilal.sa@bayflow.test', role: 'SERVICE_ADVISOR', shopId: '' })
    render(<PosHubPage />)
    const shops = within(screen.getByRole('list', { name: 'Your shops' })).getAllByRole('link')
    expect(shops.map((link) => link.getAttribute('href'))).toEqual([
      `/pos/shops/${LAHORE}/bookings`,
    ])
    expect(shops[0]).toHaveTextContent('Service Advisor')
    expect(screen.queryByRole('link', { name: 'All shops summary' })).not.toBeInTheDocument()
  })

  it('welcomes someone without a shop to create their first one (R12)', () => {
    signIn({ name: 'Tariq Mehmood', email: 'tariq@falconauto.pk', shopId: '', shopName: '' })
    render(<PosHubPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Welcome, Tariq')
    expect(screen.getByRole('link', { name: 'Create your first shop' })).toHaveAttribute(
      'href',
      '/pos/shops/new',
    )
    expect(screen.queryByRole('link', { name: 'Go to My bookings' })).not.toBeInTheDocument()
  })
})

describe('S-03 / O-05 create shop', () => {
  it('reports what is missing and puts the keyboard on the first field', () => {
    signIn()
    render(<CreateShopPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Create a new shop')
    fireEvent.click(screen.getByRole('button', { name: 'Create shop' }))

    const name = screen.getByLabelText('Shop name')
    expect(name).toHaveFocus()
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(name).toHaveAccessibleDescription('Enter the name of your shop.')
    expect(screen.getByText('Enter the street address.')).toBeInTheDocument()
    expect(screen.getByText('Enter a phone number customers can call.')).toBeInTheDocument()
    expect(getShops()).toHaveLength(6)
    expect(router.push).not.toHaveBeenCalled()
  })

  it('creates the shop, makes its creator the Owner and opens the overview with the checklist', async () => {
    signIn()
    render(<CreateShopPage />)
    fireEvent.change(screen.getByLabelText('Shop name'), {
      target: { value: 'Falcon Auto Works' },
    })
    fireEvent.change(screen.getByLabelText('Street address'), {
      target: { value: 'Shop 2, Ferozepur Road' },
    })
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '+92 42 3500 1234' } })
    fireEvent.change(screen.getByLabelText('Slot length'), { target: { value: '30' } })
    fireEvent.change(screen.getByLabelText('Cars per slot'), { target: { value: '3' } })
    expect(screen.getByText('Up to 54 bookings on each open day')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('switch', { name: 'Show on the BayFlow shop directory' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create shop' }))

    expect(screen.getByRole('button', { name: 'Creating shop…' })).toBeDisabled()
    const shop = getShops().find((s) => s.id === 'shop-falcon-auto-works')
    expect(shop).toMatchObject({
      slug: 'falcon-auto-works',
      name: 'Falcon Auto Works',
      city: 'Lahore',
      address: 'Shop 2, Ferozepur Road',
      phone: '+92 42 3500 1234',
      rating: null,
      slot_duration_minutes: 30,
      slot_capacity: 3,
      timezone: 'Asia/Karachi',
      is_listed: false,
    })
    expect(shop?.working_hours).toEqual([
      { day: 'Monday', hours: '09:00 - 18:00' },
      { day: 'Tuesday', hours: '09:00 - 18:00' },
      { day: 'Wednesday', hours: '09:00 - 18:00' },
      { day: 'Thursday', hours: '09:00 - 18:00' },
      { day: 'Friday', hours: '09:00 - 18:00' },
      { day: 'Saturday', hours: '09:00 - 18:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ])
    expect(getTeamMembers().filter((m) => m.shopId === 'shop-falcon-auto-works')).toEqual([
      expect.objectContaining({ email: DEFAULT_USER.email, role: 'OWNER', is_active: true }),
    ])
    expect(getCurrentUser()).toMatchObject({
      shopId: 'shop-falcon-auto-works',
      shopName: 'Falcon Auto Works',
      role: 'OWNER',
    })
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith(
        '/pos/shops/shop-falcon-auto-works/overview?welcome=1',
      ),
    )
  })

  it('never replaces an existing shop that has the same name', async () => {
    signIn()
    render(<CreateShopPage />)
    fireEvent.change(screen.getByLabelText('Shop name'), { target: { value: 'Raza Auto Works' } })
    fireEvent.change(screen.getByLabelText('Street address'), { target: { value: 'Plot 1' } })
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '0300-1234567' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create shop' }))

    expect(getShops().find((s) => s.id === RAZA)?.address).toBe(
      'Plot 8, Commercial Area, DHA Phase 6',
    )
    expect(getShops().find((s) => s.id === `${RAZA}-2`)?.name).toBe('Raza Auto Works')
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith(`/pos/shops/${RAZA}-2/overview?welcome=1`),
    )
  })

  it('greets someone without a shop, and points a customer to their bookings', async () => {
    signIn({ name: 'Ayesha Khan', email: 'ayesha.customer@bayflow.test', role: 'CUSTOMER' })
    render(<CreateShopPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Let’s set up your first shop',
    )
    expect(screen.getByText('Welcome, Ayesha')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Setup steps' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to My bookings' })).toHaveAttribute(
      'href',
      '/bookings',
    )

    // Creating the shop makes her an Owner; the page stays as it is until the overview opens.
    fireEvent.change(screen.getByLabelText('Shop name'), { target: { value: 'Ayesha Motors' } })
    fireEvent.change(screen.getByLabelText('Street address'), { target: { value: 'Plot 9' } })
    fireEvent.change(screen.getByLabelText('Phone'), { target: { value: '0321-7654321' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create shop' }))
    expect(getCurrentUser()).toMatchObject({ role: 'OWNER', shopId: 'shop-ayesha-motors' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Let’s set up your first shop',
    )
    expect(screen.getByRole('link', { name: 'Go to My bookings' })).toBeInTheDocument()
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith('/pos/shops/shop-ayesha-motors/overview?welcome=1'),
    )
    expect(screen.getByRole('button', { name: 'Creating shop…' })).toBeDisabled()
  })
})

describe('O-07 all shops summary', () => {
  beforeEach(() => {
    // Saturday 10 October 2026, noon in Karachi: BF-2026-004 is today's booking.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-10T07:00:00Z'))
  })

  it("shows each owned shop's day and the totals; Open switches to that shop", () => {
    signIn()
    render(<ShopsSummaryPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'All shops' })).toBeInTheDocument()

    const rows = within(screen.getByRole('table', { name: 'By shop' })).getAllByRole('row')
    const cells = (row: HTMLElement) =>
      within(row)
        .getAllByRole('cell')
        .slice(0, 6)
        .map((cell) => cell.textContent)
    expect(rows.slice(1).map(cells)).toEqual([
      ['Lahore Auto CareLahore', '1', '2', '3', '1', '0'],
      // Spec 11: Raza Auto Works' own pending booking and its 4 LOW/OUT parts.
      ['Raza Auto WorksLahore', '0', '1', '0', '0', '4'],
      ['All shops', '1', '3', '3', '1', '4'],
    ])

    fireEvent.click(within(rows[2]!).getByRole('button', { name: 'Open Raza Auto Works' }))
    expect(getCurrentUser()).toMatchObject({ shopId: RAZA, shopName: 'Raza Auto Works' })
    expect(router.push).toHaveBeenCalledWith(`/pos/shops/${RAZA}/overview`)
  })

  it('leaves a suspended shop out and says why (D99)', () => {
    signIn()
    setStoredData('admin-shop-suspensions', {
      [RAZA]: {
        at: '2026-10-10T05:00:00Z',
        reason: 'Unpaid invoices',
        byName: 'Areeba Hashmi',
        byEmail: 'admin@bayflow.test',
      },
    })
    render(<ShopsSummaryPage />)
    const table = screen.getByRole('table', { name: 'By shop' })
    expect(within(table).queryByText('Raza Auto Works')).not.toBeInTheDocument()
    expect(within(table).getByText('Lahore Auto Care')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Raza Auto Works is suspended')
  })

  it('is for owners of two or more shops (X-03)', () => {
    signIn({ name: 'Bilal', email: 'bilal.sa@bayflow.test', role: 'SERVICE_ADVISOR' })
    render(<ShopsSummaryPage />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      "You don't have access to this page",
    )
    expect(screen.getByRole('link', { name: 'Go to my home' })).toHaveAttribute(
      'href',
      `/pos/shops/${LAHORE}/bookings`,
    )
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('server render and hydration', () => {
  it.each([
    ['the hub', PosHubPage],
    ['new shop', CreateShopPage],
    ['the summary', ShopsSummaryPage],
  ] as Array<[string, ComponentType]>)(
    '%s renders a skeleton on the server and hydrates without a mismatch',
    async (_, Page) => {
      signIn({ shopId: '', shopName: '' })
      const html = renderToString(<Page />)
      expect(html).toContain('aria-busy="true"')

      const container = document.createElement('div')
      container.innerHTML = html
      document.body.append(container)
      const onRecoverableError = vi.fn()
      const root = await act(async () => hydrateRoot(container, <Page />, { onRecoverableError }))
      expect(onRecoverableError).not.toHaveBeenCalled()
      expect(container.querySelector('[aria-busy="true"]')).toBeNull()
      act(() => root.unmount())
      container.remove()
    },
  )
})
