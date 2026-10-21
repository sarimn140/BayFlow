import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { SidebarProvider } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  DEFAULT_USER,
  getCurrentUser,
  setCurrentUser,
  type CurrentUserSession,
} from '@/lib/mock-data'

import { PosHeader } from './pos-header'

const nav = vi.hoisted(() => ({ pathname: '/', push: vi.fn() }))

vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: nav.push, replace: vi.fn(), prefetch: vi.fn() }),
  useParams: () => ({}),
}))

const LAHORE = 'shop-lahore-auto-care'
const RAZA = 'shop-raza-auto-works'

const FATIMA: CurrentUserSession = { ...DEFAULT_USER } // Owner of Lahore Auto Care and Raza Auto Works
const BILAL: CurrentUserSession = {
  ...DEFAULT_USER,
  name: 'Bilal',
  email: 'bilal.sa@bayflow.test',
  role: 'SERVICE_ADVISOR',
}

beforeAll(() => {
  // The bell asks `matchMedia` whether it is on a phone; jsdom has none.
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
})

beforeEach(() => {
  localStorage.clear()
  nav.push.mockReset()
})

function renderHeader(user: CurrentUserSession, pathname: string) {
  setCurrentUser(user)
  nav.pathname = pathname
  const wrap = ({ children }: { children: ReactNode }) => (
    <TooltipProvider>
      <SidebarProvider>{children}</SidebarProvider>
    </TooltipProvider>
  )
  return render(<PosHeader />, { wrapper: wrap })
}

/** Opens the shop switcher and returns its items' text. */
function openSwitcher(): string[] {
  fireEvent.keyDown(screen.getByRole('button', { name: /shop menu$/ }), { key: 'Enter' })
  return screen.getAllByRole('menuitem').map((item) => item.textContent?.trim() ?? '')
}

describe('PosHeader: only the signed-in person’s own memberships (D20, D66)', () => {
  it("lists the Owner's two shops, never another tenant's", () => {
    renderHeader(FATIMA, `/pos/shops/${LAHORE}/overview`)
    expect(openSwitcher()).toEqual([
      'All shops summary',
      'Lahore Auto Care',
      'Raza Auto Works',
      'Create new shop',
    ])
  })

  it('lists only the Service Advisor’s own shop, with no summary', () => {
    renderHeader(BILAL, `/pos/shops/${LAHORE}/bookings`)
    expect(openSwitcher()).toEqual(['Lahore Auto Care', 'Create new shop'])
  })

  it("switches to the role the person holds in that shop, and opens that role's home", () => {
    renderHeader({ ...FATIMA, role: 'SERVICE_ADVISOR' }, `/pos/shops/${LAHORE}/bookings`)
    openSwitcher()
    fireEvent.click(screen.getByRole('menuitem', { name: /Raza Auto Works/ }))
    expect(getCurrentUser()).toMatchObject({ shopId: RAZA, role: 'OWNER' })
    expect(nav.push).toHaveBeenCalledWith(`/pos/shops/${RAZA}/overview`)
  })

  it("never names a shop the person doesn't belong to", () => {
    renderHeader(BILAL, `/pos/shops/${RAZA}/bookings`)
    expect(screen.getByRole('button', { name: 'Choose a shop, shop menu' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('Raza Auto Works')
    expect(screen.queryByRole('button', { name: 'Toggle shop navigation' })).toBeNull()
  })

  it('shows "No shop yet" to someone without a shop, not a stranger’s shop', () => {
    renderHeader(
      { ...DEFAULT_USER, name: 'Sana', email: 'sana.new@example.pk', shopId: '', shopName: '' },
      '/pos',
    )
    expect(screen.getByRole('button', { name: 'No shop yet, shop menu' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('Lahore Auto Care')
    expect(openSwitcher()).toEqual(['Workshop hub', 'Create new shop'])
  })

  it('shows the role held in this shop, and offers no role or account switching (D52)', () => {
    renderHeader(BILAL, `/pos/shops/${LAHORE}/bookings`)
    expect(screen.getByText('Your role:')).toBeInTheDocument()
    expect(screen.getByText('Service Advisor')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /role/i })).toBeNull()
    expect(screen.queryByText(/Owner \(Fatima\)/)).toBeNull()
  })

  it('names the logo link and the switcher by their visible text first (WCAG 2.5.3)', () => {
    renderHeader(FATIMA, `/pos/shops/${LAHORE}/overview`)
    expect(screen.getByRole('link', { name: 'BayFlow POS home' })).toHaveAttribute('href', '/pos')
    expect(screen.getByRole('button', { name: 'Lahore Auto Care, shop menu' })).toBeInTheDocument()
  })
})
