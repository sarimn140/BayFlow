import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_USER,
  getTeamMembers,
  INITIAL_TEAM,
  setCurrentUser,
  setStoredData,
} from '@/lib/mock-data'

import { TeamManagement } from './team-management'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/pos/shops/shop-lahore-auto-care/team',
  useParams: () => ({ shopId: 'shop-lahore-auto-care' }),
}))

const LAHORE = 'shop-lahore-auto-care'
const RAZA = 'shop-raza-auto-works'

const member = (shopId: string, email: string) =>
  getTeamMembers(shopId).find((m) => m.email === email)

/** A shop whose owner has not added anyone yet (as right after S-03 creates it). */
function ownerOnly(shopId: string) {
  setStoredData(
    'team',
    INITIAL_TEAM.filter((m) => m.shopId !== shopId || m.role === 'OWNER'),
  )
}

/** Opens a member's row menu (the table's copy; phones get the same menu in the list). */
function openMenu(name: string) {
  const buttons = screen.getAllByRole('button', { name: `Actions for ${name}` })
  fireEvent.keyDown(buttons[buttons.length - 1]!, { key: 'Enter' })
}

function openAddSheet() {
  fireEvent.click(screen.getAllByRole('button', { name: 'Add team member' })[0]!)
  return screen.getByRole('dialog', { name: 'Add team member' })
}

function fill(sheet: HTMLElement, label: string, value: string) {
  fireEvent.change(within(sheet).getByLabelText(label), { target: { value } })
}

function submit(sheet: HTMLElement) {
  fireEvent.click(within(sheet).getByRole('button', { name: 'Add team member' }))
}

let consoleError: ReturnType<typeof vi.spyOn>

beforeAll(() => {
  // Radix measures its popovers and radios; jsdom has no layout.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  Element.prototype.scrollIntoView ??= () => {}
})

beforeEach(() => {
  localStorage.clear()
  setCurrentUser(DEFAULT_USER)
  consoleError = vi.spyOn(console, 'error')
})

afterEach(() => {
  expect(consoleError).not.toHaveBeenCalled()
  consoleError.mockRestore()
})

describe('O-02 team management', () => {
  it("waits for this browser's data, then lists the team; the owner's row has no menu", () => {
    expect(renderToString(<TeamManagement shopId={LAHORE} />)).toContain('Loading the team…')

    render(<TeamManagement shopId={LAHORE} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Team' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Members' })).toBeInTheDocument()
    expect(screen.getByText('7 members · all active')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actions for Fatima Raza' })).toBeNull()
    expect(screen.getAllByRole('button', { name: 'Actions for Bilal' }).length).toBeGreaterThan(0)
  })

  it('checks the fields, refuses a current member and adds a new one', () => {
    render(<TeamManagement shopId={LAHORE} />)
    const sheet = openAddSheet()

    submit(sheet)
    expect(within(sheet).getByText('Enter their full name.')).toBeInTheDocument()
    expect(within(sheet).getByText('Enter their e-mail address.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Full name')).toHaveFocus()

    fill(sheet, 'Full name', 'Kamran Abbasi')
    fill(sheet, 'E-mail', 'IMRAN.tech@bayflow.test')
    submit(sheet)
    expect(within(sheet).getByText('Already a member of this shop.')).toBeInTheDocument()

    fill(sheet, 'E-mail', 'kamran@bayflow.test')
    fill(sheet, 'Initial password', 'short')
    submit(sheet)
    expect(within(sheet).getByText('Use 12 to 128 characters.')).toBeInTheDocument()
    expect(getTeamMembers(LAHORE)).toHaveLength(7)

    fill(sheet, 'Initial password', 'a-long-enough-password')
    fireEvent.click(within(sheet).getByRole('radio', { name: /Parts Person/ }))
    submit(sheet)

    expect(member(LAHORE, 'kamran@bayflow.test')).toMatchObject({
      name: 'Kamran Abbasi',
      role: 'PARTS_PERSON',
      is_active: true,
      shopId: LAHORE,
    })
    expect(screen.queryByRole('dialog', { name: 'Add team member' })).toBeNull()
    expect(screen.getByText('8 members · all active')).toBeInTheDocument()
  })

  it('adds an existing account as a membership only, keeping its name (D18)', () => {
    ownerOnly(RAZA)
    render(<TeamManagement shopId={RAZA} />)
    // Only the owner so far: the first-use prompt.
    expect(screen.getByText('Add your team')).toBeInTheDocument()

    const sheet = openAddSheet()
    fill(sheet, 'Full name', 'Someone Else')
    fill(sheet, 'E-mail', 'imran.tech@bayflow.test')
    fill(sheet, 'Initial password', '')
    submit(sheet)

    expect(member(RAZA, 'imran.tech@bayflow.test')).toMatchObject({
      name: 'Imran',
      role: 'TECHNICIAN',
    })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'This e-mail already has a BayFlow account — we added them to Raza Auto Works as Technician. Their existing password is unchanged.',
    )
  })

  it("returns focus to the header's button when the first-use prompt that opened the sheet is gone", async () => {
    ownerOnly(RAZA)
    render(<TeamManagement shopId={RAZA} />)
    const prompt = within(
      screen.getByText('Add your team').closest('[data-slot=empty]')!,
    ).getByRole('button', { name: 'Add team member' })
    prompt.focus()
    fireEvent.click(prompt)

    const sheet = screen.getByRole('dialog', { name: 'Add team member' })
    fill(sheet, 'Full name', 'Kamran Abbasi')
    fill(sheet, 'E-mail', 'kamran@bayflow.test')
    submit(sheet)

    expect(screen.queryByText('Add your team')).toBeNull()
    // Radix moves focus on close in a timeout.
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: 'Add team member' })[0]).toHaveFocus(),
    )
  })

  it('deactivates after a confirmation and reactivates', () => {
    render(<TeamManagement shopId={LAHORE} />)
    openMenu('Imran')
    fireEvent.click(screen.getByRole('menuitem', { name: /Deactivate/ }))

    const confirm = screen.getByRole('alertdialog', { name: 'Deactivate Imran?' })
    expect(confirm).toHaveTextContent(
      'Imran loses access to Lahore Auto Care immediately. Their 2 open jobs stay assigned — reassign them from each booking.',
    )
    // R6: focus starts on the safe option.
    expect(within(confirm).getByRole('button', { name: 'Cancel' })).toHaveFocus()
    fireEvent.click(within(confirm).getByRole('button', { name: 'Deactivate' }))
    expect(member(LAHORE, 'imran.tech@bayflow.test')?.is_active).toBe(false)
    expect(screen.getByText('7 members · 1 inactive')).toBeInTheDocument()

    openMenu('Imran')
    fireEvent.click(screen.getByRole('menuitem', { name: /Reactivate/ }))
    const reactivate = screen.getByRole('alertdialog', { name: 'Reactivate Imran?' })
    fireEvent.click(within(reactivate).getByRole('button', { name: 'Reactivate' }))
    expect(member(LAHORE, 'imran.tech@bayflow.test')?.is_active).toBe(true)
  })

  it('changes a role in a dialog', () => {
    render(<TeamManagement shopId={LAHORE} />)
    openMenu('Hamza')
    fireEvent.click(screen.getByRole('menuitem', { name: /Change role/ }))

    const dialog = screen.getByRole('dialog', { name: "Change Hamza's role" })
    expect(within(dialog).getByRole('radio', { name: /Technician/ })).toBeChecked()
    fireEvent.click(within(dialog).getByRole('radio', { name: /QC Inspector/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save role' }))

    expect(member(LAHORE, 'hamza.tech@bayflow.test')?.role).toBe('QC_INSPECTOR')
    expect(screen.queryByRole('dialog', { name: "Change Hamza's role" })).toBeNull()
  })

  it("shows no actions to someone who doesn't manage the team", () => {
    setCurrentUser({
      ...DEFAULT_USER,
      name: 'Bilal',
      email: 'bilal.sa@bayflow.test',
      role: 'SERVICE_ADVISOR',
    })
    render(<TeamManagement shopId={LAHORE} />)
    expect(screen.queryByRole('button', { name: 'Add team member' })).toBeNull()
    expect(screen.queryByRole('button', { name: /^Actions for/ })).toBeNull()
  })

  it("says so when the shop doesn't exist, instead of showing another shop's team (D20)", () => {
    render(<TeamManagement shopId="no-such-shop" />)
    expect(
      screen.getByRole('heading', { level: 1, name: "We couldn't find that shop" }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Members')).toBeNull()
  })
})
