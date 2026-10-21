import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { BookingStatus } from '@/lib/status'

import { MobileActionBar, NextStepCard } from './next-step-card'
import { planActionBar, saAllowedActions } from './sa-actions'

const step = {
  kind: 'act' as const,
  label: 'Next step',
  title: 'Confirm the booking',
  description: 'Confirm it to put it on the schedule.',
}

const plan = (status: BookingStatus) => planActionBar(saAllowedActions(status))

describe('NextStepCard', () => {
  it('shows one primary, then outline actions, destructive last (spec 09 §4.6)', () => {
    const onAction = vi.fn()
    render(
      <NextStepCard
        status="ESTIMATE_REJECTED"
        step={step}
        plan={plan('ESTIMATE_REJECTED')}
        onAction={onAction}
        facts={[{ label: 'Slot', value: 'Fri, 9 Oct 2026 · 11:00 am' }]}
      />,
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons.map((button) => button.textContent)).toEqual([
      'Revise estimate',
      'Return to technician',
      'Cancel booking',
    ])
    // The destructive action is the outline pill in the danger ink (DESIGN.md §6.15).
    expect(buttons.map((button) => button.getAttribute('data-variant'))).toEqual([
      'default',
      'outline',
      'destructive-outline',
    ])
    expect(screen.getByRole('heading', { level: 2, name: 'Confirm the booking' })).toBeVisible()
    expect(screen.getByText('Fri, 9 Oct 2026 · 11:00 am')).toBeInTheDocument()

    fireEvent.click(buttons[2] as HTMLElement)
    expect(onAction).toHaveBeenCalledWith('cancel')
  })

  it('renders no buttons on a closed booking', () => {
    render(
      <NextStepCard
        status="COMPLETED"
        step={{ ...step, kind: 'done' }}
        plan={plan('COMPLETED')}
        onAction={vi.fn()}
        facts={[]}
      />,
    )
    expect(screen.queryAllByRole('button')).toEqual([])
  })
})

describe('MobileActionBar', () => {
  it('pins the primary action and offers the rest under More', () => {
    render(<MobileActionBar plan={plan('PENDING')} onAction={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Confirm booking' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More actions' })).toBeInTheDocument()
  })

  it('never pins a lone destructive action', () => {
    const { container } = render(
      <MobileActionBar plan={plan('AWAITING_CUSTOMER')} onAction={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
