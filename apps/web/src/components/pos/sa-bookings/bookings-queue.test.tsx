import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BookingsQueue } from './bookings-queue'

const nav = vi.hoisted(() => ({ params: new URLSearchParams() }))

vi.mock('next/navigation', () => ({
  useSearchParams: () => nav.params,
  usePathname: () => '/pos/shops/shop-lahore-auto-care/bookings',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const PATH = '/pos/shops/shop-lahore-auto-care/bookings'

// A fresh element each time, so React re-renders and reads the mocked search params again.
const queue = () => (
  <BookingsQueue shopId="shop-lahore-auto-care" walkInHref="/book/lahore-auto-care" />
)

/** Open the page at `?query`, as a link or a reload would. */
function open(query = '') {
  nav.params = new URLSearchParams(query)
  return render(queue())
}

/** The router reporting a new URL (a link to this page, Back, or our own write landing). */
function routeTo(rerender: (ui: React.ReactElement) => void, query: string) {
  nav.params = new URLSearchParams(query)
  rerender(queue())
}

const tableRefs = () =>
  within(screen.getByRole('table'))
    .getAllByRole('link')
    .map((link) => link.textContent)

let replaceState: ReturnType<typeof vi.spyOn>
let consoleError: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  replaceState = vi.spyOn(window.history, 'replaceState')
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled()
  replaceState.mockRestore()
  consoleError.mockRestore()
})

describe('BookingsQueue (SA-01)', () => {
  it('opens on the advisor queue with counts on the presets', () => {
    open()
    expect(screen.getByRole('radio', { name: 'Needs action 2' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'In progress 3' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: 'All 7' })).not.toBeChecked()
    expect(screen.getByRole('table', { name: 'Bookings that need your action' })).toBeVisible()
    expect(tableRefs()).toEqual(['BF-2026-005', 'BF-2026-004'])
    // Only the advisor's own moves carry the "action needed" chip.
    expect(screen.getAllByText('Your next step:')).toHaveLength(2 * 2) // table and stacked list
  })

  it('honours ?status= from the overview and removes it with one click', () => {
    open('status=AWAITING_CUSTOMER')
    expect(screen.getByRole('radio', { name: 'All 7' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Status: Awaiting customer' })).toBeVisible()
    expect(tableRefs()).toEqual(['BF-2026-002'])

    fireEvent.click(screen.getByRole('button', { name: 'Remove status filter' }))
    expect(replaceState).toHaveBeenLastCalledWith(null, '', `${PATH}?filter=all`)
  })

  it.each([
    ['filter=needs_action', 'Needs action 2', ['BF-2026-005', 'BF-2026-004'], null],
    ['filter=ready', 'All 7', ['BF-2026-005'], 'Status: Ready for pick-up'],
    ['filter=completed', 'All 7', ['BF-2026-006'], 'Status: Completed'],
    ['filter=bogus&status=NOPE', 'Needs action 2', ['BF-2026-005', 'BF-2026-004'], null],
  ])('reads ?%s', (query, pressed, refs, chip) => {
    open(query)
    expect(screen.getByRole('radio', { name: pressed })).toBeChecked()
    expect(tableRefs()).toEqual(refs)
    if (chip) expect(screen.getByRole('button', { name: chip })).toBeVisible()
    else expect(screen.queryByRole('button', { name: 'Remove status filter' })).toBeNull()
  })

  it('writes the preset to the URL and follows the URL when it changes elsewhere', () => {
    const { rerender } = open()
    fireEvent.click(screen.getByRole('radio', { name: 'In progress 3' }))
    expect(replaceState).toHaveBeenLastCalledWith(null, '', `${PATH}?filter=in_progress`)

    routeTo(rerender, 'filter=in_progress')
    expect(screen.getByRole('radio', { name: 'In progress 3' })).toBeChecked()
    expect(tableRefs()).toEqual(['BF-2026-003', 'BF-2026-001', 'BF-2026-002'])

    // The sidebar's "Bookings" link: same page, no query, so back to the default view.
    routeTo(rerender, '')
    expect(screen.getByRole('radio', { name: 'Needs action 2' })).toBeChecked()
  })

  it('keeps every keystroke while the URL catches up, and takes a search from a link', () => {
    const { rerender } = open('filter=all')
    const input = screen.getByRole('searchbox', { name: /Search bookings/ })

    fireEvent.change(input, { target: { value: 'l' } })
    fireEvent.change(input, { target: { value: 'le' } })
    expect(replaceState).toHaveBeenLastCalledWith(null, '', `${PATH}?filter=all&q=le`)

    // Our first write lands after the second keystroke: the field keeps "le".
    routeTo(rerender, 'filter=all&q=l')
    expect(input).toHaveValue('le')
    routeTo(rerender, 'filter=all&q=le')
    expect(input).toHaveValue('le')
    // "le" is in the plates LEE-, LEA- and LEB-.
    expect(tableRefs()).toEqual([
      'BF-2026-002',
      'BF-2026-001',
      'BF-2026-005',
      'BF-2026-006',
      'BF-2026-007',
    ])

    // A link (or Back) with another search replaces what is in the field.
    routeTo(rerender, 'filter=all&q=zainab')
    expect(input).toHaveValue('zainab')
    expect(tableRefs()).toEqual(['BF-2026-004'])
  })

  it('offers the other views when a search only matches there', () => {
    open('q=LEA-22')
    expect(screen.getByText('No bookings match “LEA-22”')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Show all matches' }))
    expect(replaceState).toHaveBeenLastCalledWith(null, '', `${PATH}?filter=all&q=LEA-22`)
  })
})
