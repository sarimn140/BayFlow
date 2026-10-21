import { act, render, screen, within } from '@testing-library/react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import InventoryPage from '@/app/(pos)/pos/shops/[shopId]/inventory/page'
import {
  DEFAULT_USER,
  adjustPartStock,
  getCurrentUser,
  getServices,
  saveService,
  setCurrentUser,
} from '@/lib/mock-data'

import { useMockStore, useMockStoreReady } from './use-mock-store'

vi.mock('next/navigation', () => ({
  useParams: () => ({ shopId: 'shop-lahore-auto-care' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const SHOP_ID = 'shop-lahore-auto-care'

function ServiceCount() {
  const services = useMockStore(() => getServices(SHOP_ID))
  return <p data-testid="count">{services.length}</p>
}

function SessionBadge() {
  const user = useMockStore(() => getCurrentUser())
  const ready = useMockStoreReady()
  return (
    <p>
      {user.name} · {ready ? 'ready' : 'hydrating'}
    </p>
  )
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  // React reports an uncached getSnapshot ("should be cached to avoid an infinite loop") and
  // hydration mismatches through console.error.
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('useMockStore', () => {
  it('renders the POS inventory page without an update loop and re-renders after a stock adjustment', () => {
    render(<InventoryPage />)
    expect(screen.getByRole('heading', { level: 1, name: /^Inventory$/ })).toBeVisible()

    const onHand = () => within(screen.getByText('OF-TY-01').closest('tr')!).getAllByRole('cell')[2]
    expect(onHand()).toHaveTextContent(/^10$/)

    act(() => {
      adjustPartStock('part-of-01', 5)
    })
    expect(onHand()).toHaveTextContent(/^15$/)
  })

  it('re-renders after a write in this tab and after a write from another tab', () => {
    render(<ServiceCount />)
    const seedCount = getServices(SHOP_ID).length
    expect(screen.getByTestId('count')).toHaveTextContent(String(seedCount))

    act(() => {
      saveService({ ...getServices(SHOP_ID)[0]!, id: 'srv-new', name: 'New service' })
    })
    expect(screen.getByTestId('count')).toHaveTextContent(String(seedCount + 1))

    act(() => {
      // Another tab's write: localStorage changes, then this tab receives a `storage` event.
      localStorage.setItem('bf:services', JSON.stringify(getServices().slice(0, 2)))
      window.dispatchEvent(new StorageEvent('storage', { key: 'bf:services' }))
    })
    expect(screen.getByTestId('count')).toHaveTextContent('2')
  })

  it('hydrates server HTML without a mismatch, then shows the data stored in this browser', async () => {
    setCurrentUser({ ...DEFAULT_USER, name: 'Imran', role: 'TECHNICIAN' })

    // The server has no localStorage: it renders the seed user.
    const html = renderToString(<SessionBadge />)
    expect(html).toContain(DEFAULT_USER.name)
    expect(html).toContain('hydrating')

    const container = document.createElement('div')
    container.innerHTML = html
    document.body.append(container)
    const onRecoverableError = vi.fn()
    const root = await act(async () =>
      hydrateRoot(container, <SessionBadge />, { onRecoverableError }),
    )

    expect(onRecoverableError).not.toHaveBeenCalled()
    expect(container).toHaveTextContent('Imran · ready')

    act(() => root.unmount())
    container.remove()
  })
})
