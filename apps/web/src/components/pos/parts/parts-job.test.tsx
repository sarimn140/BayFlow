import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import {
  DEFAULT_USER,
  getBookingById,
  getPurchaseOrders,
  INITIAL_PARTS,
  INITIAL_PURCHASE_ORDERS,
  saveBooking,
  setCurrentUser,
  setStoredData,
} from '@/lib/mock-data'

import { PartsJob } from './parts-job'

const SHOP = 'shop-lahore-auto-care'

beforeEach(() => {
  localStorage.clear()
  setCurrentUser({
    ...DEFAULT_USER,
    name: 'Usman',
    email: 'usman.parts@bayflow.test',
    role: 'PARTS_PERSON',
  })
})

describe('PP-02 ordering the missing parts (D43)', () => {
  it('raises a purchase order linked to the job, then opens that order', () => {
    // BF-2026-001 waits for its parts, and the front brake pads are out of stock.
    saveBooking({ ...getBookingById('bk-001')!, status: 'PARTS_PENDING' })
    setStoredData(
      'inventory',
      INITIAL_PARTS.map((part) => (part.id === 'part-bp-01' ? { ...part, on_hand: 0 } : part)),
    )
    render(
      <TooltipProvider>
        <PartsJob shopId={SHOP} bookingId="bk-001" />
      </TooltipProvider>,
    )

    fireEvent.click(screen.getAllByRole('button', { name: 'Order missing parts' })[0]!)
    const dialog = screen.getByRole('dialog', { name: /Order missing parts for/ })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create purchase order' }))

    const orders = getPurchaseOrders(SHOP)
    expect(orders).toHaveLength(INITIAL_PURCHASE_ORDERS.length + 1)
    const order = orders[0]!
    expect(order).toMatchObject({
      shopId: SHOP,
      bookingId: 'bk-001',
      status: 'ORDERED',
      items: [{ part_sku: 'BP-FR-02', quantity: 1 }],
    })
    // A number no other order of the shop uses (saving would replace that order).
    expect(INITIAL_PURCHASE_ORDERS.map((po) => po.po_number)).not.toContain(order.po_number)
    expect(getBookingById('bk-001')?.status).toBe('PARTS_ORDERED')

    const links = screen.getAllByRole('link', { name: `Open ${order.po_number}` })
    for (const link of links) {
      expect(link).toHaveAttribute('href', `/pos/shops/${SHOP}/purchase-orders/${order.id}`)
    }
  })
})
