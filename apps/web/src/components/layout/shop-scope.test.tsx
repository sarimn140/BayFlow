import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { SidebarProvider } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { suspendShop } from '@/lib/mock-admin'
import { DEFAULT_USER, setCurrentUser, type CurrentUserSession } from '@/lib/mock-data'

import { ShopScope } from './shop-scope'

const nav = vi.hoisted(() => ({ pathname: '/' }))

vi.mock('next/navigation', () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
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
const AYESHA: CurrentUserSession = {
  ...DEFAULT_USER,
  name: 'Ayesha Khan',
  email: 'ayesha.customer@bayflow.test',
  role: 'CUSTOMER',
}

beforeAll(() => {
  // The shop sidebar asks `matchMedia` whether it is on a phone; jsdom has none.
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
})

/** The shop layout at `path`, signed in as `user`, with the page's content as a marker. */
function openShopPage(user: CurrentUserSession, path: string) {
  setCurrentUser(user)
  nav.pathname = path
  const shopId = path.split('/')[3]!
  const wrap = ({ children }: { children: ReactNode }) => (
    <TooltipProvider>
      <SidebarProvider>{children}</SidebarProvider>
    </TooltipProvider>
  )
  return render(
    <ShopScope shopId={shopId}>
      <p>The page content</p>
    </ShopScope>,
    { wrapper: wrap },
  )
}

const notFound = () =>
  screen.queryByRole('heading', { level: 1, name: "We couldn't find that shop" })

describe('ShopScope: only the shop’s own members get in (D20)', () => {
  it('opens each of the Owner’s shops, with the shop navigation', () => {
    for (const shop of [LAHORE, RAZA]) {
      const { unmount } = openShopPage(FATIMA, `/pos/shops/${shop}/overview`)
      expect(screen.getByText('The page content')).toBeInTheDocument()
      expect(screen.getByRole('navigation', { name: 'Shop navigation' })).toBeInTheDocument()
      unmount()
    }
  })

  it("keeps the Owner's read-only views of the other roles (D16)", () => {
    openShopPage(FATIMA, `/pos/shops/${LAHORE}/jobs`)
    expect(screen.getByText('The page content')).toBeInTheDocument()
  })

  it("gives another shop's staff the 404 view, without the shop's name or navigation", () => {
    openShopPage(BILAL, `/pos/shops/${RAZA}/bookings`)
    expect(notFound()).toBeInTheDocument()
    expect(screen.queryByText('The page content')).toBeNull()
    expect(screen.queryByRole('navigation', { name: 'Shop navigation' })).toBeNull()
    expect(document.body.textContent).not.toContain('Raza Auto Works')
  })

  it('never lets a customer into a shop', () => {
    openShopPage(AYESHA, `/pos/shops/${LAHORE}/overview`)
    expect(notFound()).toBeInTheDocument()
    expect(screen.queryByText('The page content')).toBeNull()
    expect(screen.getByRole('link', { name: 'Go to my bookings' })).toHaveAttribute(
      'href',
      '/bookings',
    )
  })

  it('answers an unknown shop exactly like a shop the person is not in', () => {
    openShopPage(FATIMA, '/pos/shops/shop-does-not-exist/overview')
    expect(notFound()).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to my shops' })).toHaveAttribute('href', '/pos')
  })

  it("lets a member into their own role's sections", () => {
    openShopPage(BILAL, `/pos/shops/${LAHORE}/bookings`)
    expect(screen.getByText('The page content')).toBeInTheDocument()
  })

  it("judges a section by the membership's role, not the role the session claims", () => {
    // Bilal's session says Owner, but in Lahore Auto Care he is its Service Advisor.
    openShopPage({ ...BILAL, role: 'OWNER' }, `/pos/shops/${LAHORE}/overview`)
    expect(
      screen.getByRole('heading', { level: 1, name: "You don't have access to this page" }),
    ).toBeInTheDocument()
    expect(screen.queryByText('The page content')).toBeNull()
  })

  it('shows a suspended shop as suspended to its members only (D96)', () => {
    suspendShop(RAZA, 'Unpaid invoices for three months.', {
      name: 'Areeba Hashmi',
      email: 'admin@bayflow.test',
    })
    const { unmount } = openShopPage(FATIMA, `/pos/shops/${RAZA}/overview`)
    expect(
      screen.getByRole('heading', { level: 1, name: 'This shop is suspended' }),
    ).toBeInTheDocument()
    unmount()

    openShopPage(BILAL, `/pos/shops/${RAZA}/overview`)
    expect(notFound()).toBeInTheDocument()
    expect(screen.queryByText('This shop is suspended')).toBeNull()
  })
})
