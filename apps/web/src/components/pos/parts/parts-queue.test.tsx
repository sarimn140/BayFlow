import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import {
  DEFAULT_USER,
  getBookingById,
  INITIAL_PURCHASE_ORDERS,
  saveBooking,
  savePurchaseOrder,
  setCurrentUser,
} from '@/lib/mock-data'

import { PartsQueue } from './parts-queue'

const SHOP = 'shop-lahore-auto-care'

function renderQueue() {
  return render(
    <TooltipProvider>
      <PartsQueue shopId={SHOP} />
    </TooltipProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  setCurrentUser({
    ...DEFAULT_USER,
    name: 'Usman',
    email: 'usman.parts@bayflow.test',
    role: 'PARTS_PERSON',
  })
})

describe('PP-01 on order (D43)', () => {
  it('names the purchase order a job waits on', () => {
    saveBooking({ ...getBookingById('bk-001')!, status: 'PARTS_ORDERED' })
    savePurchaseOrder({ ...INITIAL_PURCHASE_ORDERS[1]!, bookingId: 'bk-001' })
    renderQueue()

    const onOrder = screen.getByRole('list', { name: /^On order/ })
    const row = within(onOrder).getByRole('link', { name: /BF-2026-001/ })
    expect(row).toHaveTextContent('On PO-2026-002')
    expect(row).toHaveAttribute('href', `/pos/shops/${SHOP}/parts/bk-001`)
  })

  it('says when the delivery is in but the parts are not marked ready yet', () => {
    saveBooking({ ...getBookingById('bk-001')!, status: 'PARTS_ORDERED' })
    savePurchaseOrder({ ...INITIAL_PURCHASE_ORDERS[1]!, bookingId: 'bk-001', status: 'RECEIVED' })
    renderQueue()

    const onOrder = screen.getByRole('list', { name: /^On order/ })
    expect(within(onOrder).getByRole('link', { name: /BF-2026-001/ })).toHaveTextContent(
      'On PO-2026-002 · delivered',
    )
  })

  it('names no order for a job without one', () => {
    saveBooking({ ...getBookingById('bk-001')!, status: 'PARTS_ORDERED' })
    renderQueue()

    const onOrder = screen.getByRole('list', { name: /^On order/ })
    expect(within(onOrder).getByRole('link', { name: /BF-2026-001/ })).not.toHaveTextContent(
      'PO-2026',
    )
  })
})
