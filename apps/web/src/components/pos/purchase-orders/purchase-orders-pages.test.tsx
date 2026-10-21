import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PurchaseOrderDetailPage from '@/app/(pos)/pos/shops/[shopId]/purchase-orders/[poId]/page'
import PurchaseOrdersPage from '@/app/(pos)/pos/shops/[shopId]/purchase-orders/page'
import {
  DEFAULT_USER,
  INITIAL_PURCHASE_ORDERS,
  getInventory,
  getPurchaseOrders,
  savePurchaseOrder,
  setCurrentUser,
} from '@/lib/mock-data'

const SHOP = 'shop-lahore-auto-care'
const nav = vi.hoisted(() => ({ params: {} as Record<string, string> }))

vi.mock('next/navigation', () => ({
  useParams: () => nav.params,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => `/pos/shops/${nav.params.shopId}/purchase-orders`,
}))

const PARTS_PERSON = {
  ...DEFAULT_USER,
  name: 'Usman',
  email: 'usman.parts@bayflow.test',
  role: 'PARTS_PERSON' as const,
}

function onHand(sku: string): number | undefined {
  return getInventory().find((part) => part.sku === sku)?.on_hand
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  setCurrentUser(PARTS_PERSON)
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('PP-04 purchase orders', () => {
  beforeEach(() => {
    nav.params = { shopId: SHOP }
  })

  it('shows the open orders by default, and every order under All', () => {
    render(<PurchaseOrdersPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'Purchase orders' })).toBeInTheDocument()
    expect(screen.getAllByText('PO-2026-002').length).toBeGreaterThan(0)
    expect(screen.queryByText('PO-2026-001')).toBeNull()

    fireEvent.click(screen.getByRole('radio', { name: /^all/i }))
    expect(screen.getAllByText('PO-2026-001').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PO-2026-002').length).toBeGreaterThan(0)
  })

  it('creates a restock order for the chosen part at its catalogue cost', () => {
    render(<PurchaseOrdersPage />)
    fireEvent.click(screen.getByRole('button', { name: 'New purchase order' }))
    const dialog = screen.getByRole('dialog', { name: 'New purchase order' })
    expect(within(dialog).getByLabelText('Unit cost')).toHaveValue(1500)
    fireEvent.change(within(dialog).getByLabelText('Quantity'), { target: { value: '6' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create purchase order' }))

    const created = getPurchaseOrders()[0]!
    expect(created).toMatchObject({
      shopId: SHOP,
      supplier: 'Shell Lubricants Direct',
      status: 'ORDERED',
      items: [
        {
          part_sku: 'OF-TY-01',
          part_name: 'Oil Filter Cartridge (Toyota/Honda)',
          quantity: 6,
          unit_price: 1500,
        },
      ],
      total_amount: 9000,
    })
    expect(created.po_number).toMatch(/^PO-2026-\d{3,}$/)
    expect(INITIAL_PURCHASE_ORDERS.map((po) => po.po_number)).not.toContain(created.po_number)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getAllByText(created.po_number).length).toBeGreaterThan(0)
    // Creating an order never changes stock; receiving it does.
    expect(onHand('OF-TY-01')).toBe(10)
  })

  it('refuses a quantity of 0 or an empty supplier, and says why', () => {
    render(<PurchaseOrdersPage />)
    fireEvent.click(screen.getByRole('button', { name: 'New purchase order' }))
    const dialog = screen.getByRole('dialog', { name: 'New purchase order' })
    fireEvent.change(within(dialog).getByLabelText('Supplier'), { target: { value: ' ' } })
    fireEvent.change(within(dialog).getByLabelText('Quantity'), { target: { value: '0' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create purchase order' }))

    expect(within(dialog).getByText('Enter the supplier’s name.')).toBeInTheDocument()
    expect(within(dialog).getByText('Enter a whole number from 1 to 10,000.')).toBeInTheDocument()
    expect(document.activeElement).toBe(within(dialog).getByLabelText('Supplier'))
    expect(getPurchaseOrders()).toHaveLength(INITIAL_PURCHASE_ORDERS.length)
  })

  it('gives the Owner a read-only list (D16)', () => {
    setCurrentUser(DEFAULT_USER)
    render(<PurchaseOrdersPage />)
    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New purchase order' })).toBeNull()
    expect(screen.queryByRole('link', { name: /^receive/i })).toBeNull()
    expect(screen.getByRole('link', { name: 'View PO-2026-002' })).toBeInTheDocument()
  })

  it('names the job an order was raised for, and opens it where the role acts (D43)', () => {
    savePurchaseOrder({ ...INITIAL_PURCHASE_ORDERS[1]!, bookingId: 'bk-001' })
    const { unmount } = render(<PurchaseOrdersPage />)
    expect(screen.getByRole('link', { name: 'BF-2026-001' })).toHaveAttribute(
      'href',
      `/pos/shops/${SHOP}/parts/bk-001`,
    )
    unmount()

    setCurrentUser(DEFAULT_USER)
    render(<PurchaseOrdersPage />)
    expect(screen.getByRole('link', { name: 'BF-2026-001' })).toHaveAttribute(
      'href',
      `/pos/shops/${SHOP}/bookings/bk-001`,
    )
  })
})

describe('PP-05 purchase order detail', () => {
  beforeEach(() => {
    nav.params = { shopId: SHOP, poId: 'po-1002' }
  })

  it('receives every line into stock after confirming', () => {
    render(<PurchaseOrderDetailPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Receive into stock' }))

    const dialog = screen.getByRole('dialog', { name: 'Receive PO-2026-002 into stock?' })
    expect(within(dialog).getByText('Vented Brake Rotors Pair')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm receipt' }))

    expect(onHand('BR-VENT-01')).toBe(2 + 4)
    expect(onHand('SP-IRID-04')).toBe(6 + 8)
    expect(getPurchaseOrders().find((po) => po.id === 'po-1002')!.status).toBe('RECEIVED')
    expect(screen.getByText('Delivery received')).toBeInTheDocument()
    expect(screen.getByText('12 units added to inventory.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive into stock' })).toBeNull()
  })

  it('changes nothing when the receipt is cancelled', () => {
    render(<PurchaseOrderDetailPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Receive into stock' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onHand('BR-VENT-01')).toBe(2)
    expect(getPurchaseOrders().find((po) => po.id === 'po-1002')!.status).toBe('ORDERED')
    expect(screen.getByRole('button', { name: 'Receive into stock' })).toBeInTheDocument()
  })

  it('does not offer to receive a received order', () => {
    nav.params = { shopId: SHOP, poId: 'po-1001' }
    render(<PurchaseOrderDetailPage />)
    expect(screen.getByRole('heading', { level: 1, name: 'PO-2026-001' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive into stock' })).toBeNull()
  })

  it('shows the Owner the order read-only (D16)', () => {
    setCurrentUser(DEFAULT_USER)
    render(<PurchaseOrderDetailPage />)
    expect(screen.getByText('Read-only view')).toBeInTheDocument()
    expect(screen.getByText('Awaiting delivery')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive into stock' })).toBeNull()
  })

  it('links the job the order was raised for, or says it is a general restock', () => {
    savePurchaseOrder({ ...INITIAL_PURCHASE_ORDERS[1]!, bookingId: 'bk-001' })
    const { unmount } = render(<PurchaseOrderDetailPage />)
    expect(screen.getByRole('link', { name: 'BF-2026-001' })).toHaveAttribute(
      'href',
      `/pos/shops/${SHOP}/parts/bk-001`,
    )
    expect(screen.getByText('2022 Honda Civic Oriel')).toBeInTheDocument()
    unmount()

    nav.params = { shopId: SHOP, poId: 'po-1001' }
    render(<PurchaseOrderDetailPage />)
    expect(screen.getByText('General restock')).toBeInTheDocument()
  })

  it('says when the order does not exist', () => {
    nav.params = { shopId: SHOP, poId: 'po-missing' }
    render(<PurchaseOrderDetailPage />)
    expect(
      screen.getByRole('heading', { level: 1, name: 'We couldn’t find this purchase order' }),
    ).toBeInTheDocument()
  })

  it('opens an order saved in this browser without flashing "not found"', async () => {
    savePurchaseOrder({ ...INITIAL_PURCHASE_ORDERS[1]!, id: 'po-new', po_number: 'PO-2026-777' })
    nav.params = { shopId: SHOP, poId: 'po-new' }

    // The server has no localStorage: it renders the loading state, never "not found".
    const html = renderToString(<PurchaseOrderDetailPage />)
    expect(html).toContain('Loading the purchase order')
    expect(html).not.toContain('find this purchase order')

    const container = document.createElement('div')
    container.innerHTML = html
    document.body.append(container)
    const onRecoverableError = vi.fn()
    const root = await act(async () =>
      hydrateRoot(container, <PurchaseOrderDetailPage />, { onRecoverableError }),
    )
    expect(onRecoverableError).not.toHaveBeenCalled()
    expect(
      within(container).getByRole('heading', { level: 1, name: 'PO-2026-777' }),
    ).toBeInTheDocument()

    act(() => root.unmount())
    container.remove()
  })
})
