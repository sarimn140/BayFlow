import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { hydrateRoot } from 'react-dom/client'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import InventoryPage from '@/app/(pos)/pos/shops/[shopId]/inventory/page'
import {
  DEFAULT_USER,
  getInventory,
  INITIAL_PARTS,
  setCurrentUser,
  setStoredData,
  type MockPart,
} from '@/lib/mock-data'

const SHOP = 'shop-lahore-auto-care'

/** Stock operations are the Parts Person's (D44); the seed's signed-in user is the Owner. */
const USMAN = {
  ...DEFAULT_USER,
  name: 'Usman',
  email: 'usman.parts@bayflow.test',
  role: 'PARTS_PERSON' as const,
}

vi.mock('next/navigation', () => ({
  useParams: () => ({ shopId: 'shop-lahore-auto-care' }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/pos/shops/shop-lahore-auto-care/inventory',
}))

/** The seed parts with some stock changed, as this browser's stored data. */
function stageParts(changes: Record<string, Partial<MockPart>>) {
  setStoredData(
    'inventory',
    INITIAL_PARTS.map((part) => ({ ...part, ...changes[part.id] })),
  )
}

const stored = (id: string) => getInventory().find((part) => part.id === id)

/** The table row of a part (the phone list shows the SKU together with the category). */
const row = (sku: string) => screen.getByText(sku).closest('tr')!

function openRowAction(sku: string, action: 'Adjust stock' | 'Edit part') {
  const trigger = within(row(sku)).getByRole('button', { name: /^Actions for/ })
  fireEvent.keyDown(trigger, { key: 'Enter' })
  fireEvent.click(screen.getByRole('menuitem', { name: action }))
  return screen.getByRole('dialog', { name: action === 'Edit part' ? 'Edit part' : 'Adjust stock' })
}

const type = (field: HTMLElement, value: string) => fireEvent.change(field, { target: { value } })

let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('PP-03 inventory', () => {
  it('shows the stock value, each part’s on hand, reserved and available stock, and its state', () => {
    stageParts({ 'part-oil-01': { on_hand: 3, reserved: 1 }, 'part-br-01': { on_hand: 0 } })
    render(<InventoryPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Inventory' })).toBeVisible()
    // 153,200 at seed − 5 engine oil × 6,800 − 2 rotors × 12,000.
    expect(screen.getByText('Rs 95,200')).toBeInTheDocument()
    expect(screen.getByText('1 running low · 1 out of stock')).toBeInTheDocument()

    const oil = within(row('OIL-SYN-4L')).getAllByRole('cell')
    expect(oil.slice(2, 5).map((cell) => cell.textContent)).toEqual(['3', '1', '2'])
    expect(within(row('OIL-SYN-4L')).getByText('Low stock')).toBeInTheDocument()
    expect(within(row('BR-VENT-01')).getByText('Out of stock')).toBeInTheDocument()
    expect(within(row('OF-TY-01')).getByText('In stock')).toBeInTheDocument()

    expect(screen.getByRole('radio', { name: 'All 6' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Low stock 1' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'Out of stock 1' })).toBeInTheDocument()
  })

  it('filters by stock state and by search, and clears a search that finds nothing', () => {
    stageParts({ 'part-br-01': { on_hand: 0 } })
    render(<InventoryPage />)

    fireEvent.click(screen.getByRole('radio', { name: 'Out of stock 1' }))
    expect(screen.getByText('BR-VENT-01')).toBeInTheDocument()
    expect(screen.queryByText('OF-TY-01')).toBeNull()
    expect(screen.getByText(/^Showing/)).toHaveTextContent('Showing 1 of 6 parts')

    fireEvent.click(screen.getByRole('radio', { name: 'Low stock 0' }))
    expect(screen.getByText('Nothing is running low')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: 'All 6' }))
    type(screen.getByRole('searchbox', { name: 'Search parts' }), 'filters')
    expect(screen.getByText('OF-TY-01')).toBeInTheDocument()
    expect(screen.getByText('AF-CAB-01')).toBeInTheDocument()
    expect(screen.queryByText('BP-FR-02')).toBeNull()

    fireEvent.click(screen.getByRole('radio', { name: 'Out of stock 1' }))
    type(screen.getByRole('searchbox', { name: 'Search parts' }), 'zzz')
    expect(screen.getByText('No parts match “zzz”')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all parts' }))
    expect(screen.getByRole('searchbox', { name: 'Search parts' })).toHaveValue('')
    expect(screen.getByRole('radio', { name: 'All 6' })).toBeChecked()
    expect(screen.getByText('BP-FR-02')).toBeInTheDocument()
  })

  it('adds a part at 0 on hand and refuses a SKU another part uses', async () => {
    render(<InventoryPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Add part' }))
    const sheet = screen.getByRole('dialog', { name: 'Add part' })
    expect(sheet).toHaveTextContent('New parts start at 0 on hand.')
    expect(within(sheet).queryByLabelText(/on hand/i)).toBeNull()

    fireEvent.click(within(sheet).getByRole('button', { name: 'Add part' }))
    expect(await within(sheet).findByText('Check 3 fields')).toBeInTheDocument()
    expect(within(sheet).getAllByText('Enter the SKU.')).not.toHaveLength(0)

    type(within(sheet).getByLabelText('SKU'), 'of-ty-01')
    type(within(sheet).getByLabelText('Part name'), 'Oil filter, second brand')
    type(within(sheet).getByLabelText('Unit cost'), '2,500')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Add part' }))
    expect(
      await within(sheet).findByText(
        'OF-TY-01 is already used by Oil Filter Cartridge (Toyota/Honda).',
      ),
    ).toBeInTheDocument()
    expect(getInventory(SHOP)).toHaveLength(6)
    expect(stored('part-of-01')).toMatchObject({ name: 'Oil Filter Cartridge (Toyota/Honda)' })

    type(within(sheet).getByLabelText('SKU'), 'wb-26in')
    type(within(sheet).getByLabelText('Part name'), 'Wiper Blade 26 inch')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Filters' }))
    type(within(sheet).getByLabelText('Reorder level'), '0')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Add part' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    const added = getInventory().find((part) => part.sku === 'WB-26IN')
    expect(added).toMatchObject({
      shopId: SHOP,
      name: 'Wiper Blade 26 inch',
      category: 'Filters',
      on_hand: 0,
      reserved: 0,
      reorder_level: 0,
      unit_price: 2500,
    })
    expect(within(row('WB-26IN')).getByText('Out of stock')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add part' })).toHaveFocus())
  })

  it('adjusts stock with a reason and refuses leaving less than is reserved', async () => {
    setCurrentUser(USMAN)
    render(<InventoryPage />)
    const sheet = openRowAction('BP-FR-02', 'Adjust stock')
    expect(within(sheet).getByLabelText('Quantity')).toHaveFocus()

    fireEvent.click(within(sheet).getByRole('radio', { name: 'Remove stock' }))
    type(within(sheet).getByLabelText('Quantity'), '4')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Damaged or faulty' }))
    expect(within(sheet).getByLabelText('Reason')).toHaveValue('Damaged or faulty')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Remove 4 units' }))
    expect(
      await within(sheet).findByText(
        'That adjustment would leave less stock on hand than is reserved for jobs, or below zero.',
      ),
    ).toBeInTheDocument()
    expect(stored('part-bp-01')?.on_hand).toBe(4)

    type(within(sheet).getByLabelText('Quantity'), '3')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Remove 3 units' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(stored('part-bp-01')).toMatchObject({ on_hand: 1, reserved: 1 })
    expect(within(row('BP-FR-02')).getByText('Out of stock')).toBeInTheDocument()
    // The sheet has no trigger of its own: focus goes back to the row's menu button.
    await waitFor(() =>
      expect(within(row('BP-FR-02')).getByRole('button', { name: /^Actions for/ })).toHaveFocus(),
    )
  })

  it('needs a quantity above 0 and a reason before adding stock', async () => {
    setCurrentUser(USMAN)
    render(<InventoryPage />)
    const sheet = openRowAction('OF-TY-01', 'Adjust stock')
    type(within(sheet).getByLabelText('Quantity'), '0')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Apply adjustment' }))
    expect(await within(sheet).findByText('Check 2 fields')).toBeInTheDocument()
    expect(within(sheet).getAllByText('Enter 1 or more.')).not.toHaveLength(0)
    expect(within(sheet).getAllByText('Say why the stock changed.')).not.toHaveLength(0)
    expect(stored('part-of-01')?.on_hand).toBe(10)

    type(within(sheet).getByLabelText('Quantity'), '5')
    type(within(sheet).getByLabelText('Reason'), 'Delivery received')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Add 5 units' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(stored('part-of-01')?.on_hand).toBe(15)
  })

  it('edits a part’s catalogue fields and keeps its stock', async () => {
    render(<InventoryPage />)
    const sheet = openRowAction('OF-TY-01', 'Edit part')
    const sku = within(sheet).getByLabelText<HTMLInputElement>('SKU')
    expect(sku).toHaveValue('OF-TY-01')
    // Focused, but not selected: typing must not replace the SKU by accident.
    expect(sku).toHaveFocus()
    expect(sku.selectionEnd! - sku.selectionStart!).toBe(0)

    type(within(sheet).getByLabelText('Part name'), 'Oil Filter (Toyota/Honda)')
    type(within(sheet).getByLabelText('Unit cost'), '1650')
    type(within(sheet).getByLabelText('Reorder level'), '0')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    expect(stored('part-of-01')).toMatchObject({
      sku: 'OF-TY-01',
      name: 'Oil Filter (Toyota/Honda)',
      unit_price: 1650,
      reorder_level: 0,
      on_hand: 10,
      reserved: 0,
    })
    expect(getInventory(SHOP)).toHaveLength(6)
  })

  it('lets the Owner edit the catalogue but not the stock (D44)', () => {
    // The seed's signed-in user is Fatima, the Owner.
    render(<InventoryPage />)
    expect(screen.getByText('Catalogue only')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Stock operations are done by Parts Persons; you can edit the parts catalogue.',
      ),
    ).toBeInTheDocument()

    const trigger = within(row('OF-TY-01')).getByRole('button', { name: /^Actions for/ })
    fireEvent.keyDown(trigger, { key: 'Enter' })
    expect(screen.getByRole('menuitem', { name: 'Edit part' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Adjust stock' })).toBeNull()
    fireEvent.keyDown(screen.getByRole('menuitem', { name: 'Edit part' }), { key: 'Escape' })

    fireEvent.click(screen.getByRole('button', { name: 'Add part' }))
    expect(screen.getByRole('dialog', { name: 'Add part' })).toHaveTextContent(
      'New parts start at 0 on hand. Your Parts Person sets the opening stock.',
    )
  })

  it('gives the Parts Person stock operations without the Owner’s notice', () => {
    setCurrentUser(USMAN)
    render(<InventoryPage />)
    expect(screen.queryByText('Catalogue only')).toBeNull()
    fireEvent.keyDown(within(row('OF-TY-01')).getByRole('button', { name: /^Actions for/ }), {
      key: 'Enter',
    })
    expect(screen.getByRole('menuitem', { name: 'Adjust stock' })).toBeInTheDocument()
  })

  it('checks a SKU inside this shop only, and never changes another shop’s part (D20)', async () => {
    const elsewhere = INITIAL_PARTS.filter((part) => part.sku === 'FLT-OIL-01')
    expect(elsewhere.length).toBeGreaterThan(1)
    expect(elsewhere.some((part) => part.shopId === SHOP)).toBe(false)

    render(<InventoryPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Add part' }))
    const sheet = screen.getByRole('dialog', { name: 'Add part' })
    type(within(sheet).getByLabelText('SKU'), 'FLT-OIL-01')
    type(within(sheet).getByLabelText('Part name'), 'Oil filter')
    type(within(sheet).getByLabelText('Unit cost'), '900')
    fireEvent.click(within(sheet).getByRole('button', { name: 'Add part' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    expect(getInventory(SHOP).filter((part) => part.sku === 'FLT-OIL-01')).toHaveLength(1)
    for (const part of elsewhere) expect(stored(part.id)).toEqual(part)
  })

  it('shows a skeleton while hydrating, then this browser’s stock without a mismatch', async () => {
    stageParts({ 'part-of-01': { on_hand: 42 } })

    // The server has no localStorage: it renders the skeleton, not the seed counts.
    const html = renderToString(<InventoryPage />)
    expect(html).toContain('Loading inventory')
    expect(html).not.toContain('OF-TY-01')

    const container = document.createElement('div')
    container.innerHTML = html
    document.body.append(container)
    const onRecoverableError = vi.fn()
    const root = await act(async () =>
      hydrateRoot(container, <InventoryPage />, { onRecoverableError }),
    )

    expect(onRecoverableError).not.toHaveBeenCalled()
    const cells = within(within(container).getByText('OF-TY-01').closest('tr')!).getAllByRole(
      'cell',
    )
    expect(cells[2]).toHaveTextContent(/^42$/)

    act(() => root.unmount())
    container.remove()
  })
})
