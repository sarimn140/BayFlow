import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BOOKING_STATUSES, BOOKING_STATUS_META } from '@/lib/status'

import { StatusBadge } from './status-badge'

describe('StatusBadge', () => {
  it('shows the customer label in the portal', () => {
    render(<StatusBadge status="AWAITING_CUSTOMER" audience="customer" />)
    const badge = screen.getByText('Estimate awaiting your approval')
    expect(badge).toHaveAttribute('data-status', 'AWAITING_CUSTOMER')
    expect(badge).toHaveTextContent('Status: Estimate awaiting your approval')
  })

  it('shows the staff label in the POS', () => {
    render(<StatusBadge status="QC_PENDING" audience="staff" />)
    expect(screen.getByText('QC pending')).toHaveAttribute('data-status', 'QC_PENDING')
  })

  it('colours by phase, with the red override for a rejected estimate', () => {
    const { container } = render(
      <>
        <StatusBadge status="AWAITING_CUSTOMER" audience="staff" />
        <StatusBadge status="ESTIMATE_REJECTED" audience="staff" />
      </>,
    )
    const [awaiting, rejected] = container.querySelectorAll('[data-slot="badge"]')
    expect(awaiting).toHaveAttribute('data-variant', 'estimate')
    expect(rejected).toHaveAttribute('data-variant', 'estimate-rejected')
  })

  it('renders every status with an icon hidden from assistive technology', () => {
    for (const status of BOOKING_STATUSES) {
      const { container, unmount } = render(<StatusBadge status={status} audience="staff" />)
      expect(container).toHaveTextContent(BOOKING_STATUS_META[status].staffLabel)
      expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
      unmount()
    }
  })
})
