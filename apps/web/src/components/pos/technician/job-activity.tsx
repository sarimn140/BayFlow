'use client'

import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { Timeline, type TimelineTone } from '@/components/layout/timeline'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { formatDateTime } from '@/lib/format'
import { bookingHistory, type HistoryActorRole } from '@/lib/mock-booking-history'
import type { MockBooking } from '@/lib/mock-data'
import { statusLabel } from '@/lib/status'

import { countLabel } from './job-model'

const ROLE_NAME: Record<HistoryActorRole, string> = {
  CUSTOMER: 'Customer',
  SERVICE_ADVISOR: 'Service advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts person',
  QC_INSPECTOR: 'QC inspector',
}

/** Past-tense titles for the booking actions (spec 09 §4.6 slugs). */
const EVENT_TITLE: Record<string, string> = {
  create: 'Booking made',
  confirm: 'Booking confirmed',
  'assign-technician': 'Technician assigned',
  'start-inspection': 'Inspection started',
  'submit-estimate': 'Estimate submitted',
  'send-estimate': 'Estimate sent to the customer',
  'approve-estimate': 'Estimate approved',
  'reject-estimate': 'Estimate declined',
  'assign-parts-person': 'Parts person assigned',
  'order-parts': 'Parts ordered',
  'mark-parts-ready': 'Parts ready',
  'allocate-parts': 'Parts allocated, repair started',
  'send-to-qc': 'Sent to QC',
  'pick-qc': 'QC started',
  'pass-qc': 'Passed QC',
  complete: 'Booking completed',
  cancel: 'Booking cancelled',
}

function toneOf(status: MockBooking['status']): TimelineTone {
  if (status === 'ESTIMATE_APPROVED' || status === 'READY_FOR_PICKUP' || status === 'COMPLETED') {
    return 'success'
  }
  if (status === 'ESTIMATE_REJECTED' || status === 'CANCELLED') return 'danger'
  return 'default'
}

/**
 * T-02 item 8, the booking's activity, collapsed by default (spec 10 T-02). Reads the same mock
 * history as notifications and the admin timeline, newest first.
 */
export function JobActivity({ booking, timeZone }: { booking: MockBooking; timeZone: string }) {
  const [open, setOpen] = useState(false)
  const steps = [...bookingHistory(booking)].reverse()
  if (steps.length === 0) return null

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="gap-0 py-0">
        <h2>
          <CollapsibleTrigger className="group flex min-h-16 w-full items-center gap-3 px-5 py-4 text-left transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:px-6">
            <span className="min-w-0 flex-1">
              <span className="block text-lg leading-7 font-semibold text-foreground">
                Activity
              </span>
              <span className="block text-sm font-normal text-muted-foreground">
                {countLabel(steps.length, 'update', 'updates')}, newest first
              </span>
            </span>
            <ChevronDown
              className="size-5 shrink-0 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-180"
              aria-hidden="true"
            />
          </CollapsibleTrigger>
        </h2>
        <CollapsibleContent>
          <div className="border-t border-border-faint px-5 py-5 sm:px-6">
            <Timeline
              aria-label="Job activity"
              items={steps.map((step) => ({
                id: `${step.status}-${step.at}`,
                title: EVENT_TITLE[step.action] ?? statusLabel(step.status, 'staff'),
                description: `${step.actorName} · ${ROLE_NAME[step.actorRole]}`,
                time: <time dateTime={step.at}>{formatDateTime(step.at, timeZone)}</time>,
                tone: toneOf(step.status),
              }))}
            />
          </div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
