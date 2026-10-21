import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { INITIAL_BOOKINGS, type MockBooking } from '@/lib/mock-data'

import { EstimateCard } from './estimate-card'

function seed(id: string): MockBooking {
  const booking = INITIAL_BOOKINGS.find((candidate) => candidate.id === id)
  if (!booking) throw new Error(`no seed booking ${id}`)
  return { ...booking }
}

describe('EstimateCard', () => {
  it('shows the version, a timestamped state and the totals', () => {
    render(
      <EstimateCard
        booking={seed('bk-002')}
        version={2}
        technician="Hamza"
        saDraftOpen={false}
        times={{ sent: 'Fri, 9 Oct 2026 at 11:15 am' }}
      />,
    )
    const title = screen.getByRole('heading', { level: 2 })
    expect(title).toHaveTextContent('Estimate')
    expect(within(title).getByText('v2')).toBeInTheDocument()
    expect(within(title).getByText('Awaiting approval')).toBeInTheDocument()
    expect(screen.getByText('Sent to Ayesha Khan on Fri, 9 Oct 2026 at 11:15 am')).toBeVisible()
    expect(screen.getByText('Grand total').nextElementSibling).toHaveTextContent('Rs 10,800')
    expect(screen.queryByRole('button', { name: 'Edit estimate' })).toBeNull()
  })

  it('offers the editor from the empty state while the estimate is under review', () => {
    const onEdit = vi.fn()
    const booking: MockBooking = {
      ...seed('bk-002'),
      status: 'ESTIMATE_REVIEW',
      estimateItems: [],
      inspectionNotes: undefined,
    }
    render(
      <EstimateCard
        booking={booking}
        version={1}
        technician="Hamza"
        saDraftOpen={false}
        onEdit={onEdit}
      />,
    )
    expect(screen.getByText('No estimate yet')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Edit estimate' }))
    expect(onEdit).toHaveBeenCalledOnce()
  })

  it('says "No estimate" on a closed booking without lines', () => {
    const booking: MockBooking = { ...seed('bk-004'), status: 'CANCELLED' }
    render(<EstimateCard booking={booking} version={1} saDraftOpen={false} />)
    expect(screen.getByText('No estimate')).toBeVisible()
    expect(screen.getByText('No estimate was written for this booking.')).toBeVisible()
  })
})
