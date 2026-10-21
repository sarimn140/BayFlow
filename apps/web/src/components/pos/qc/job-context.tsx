import { Package, RotateCcw, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import type { MockBooking } from '@/lib/mock-data'

import { parseQcIssue } from './qc-data'
import { CardHeading } from './qc-ui'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      {children}
    </section>
  )
}

/** A quoted note in a tinted well (DESIGN.md "Paper"). */
export function NoteWell({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-xl bg-layer px-4 py-3 text-sm leading-6 whitespace-pre-line text-foreground">
      {children}
    </p>
  )
}

/**
 * What the inspector checks against (spec 10 QI-02 "Context"): the customer's concern, the
 * services booked, the approved work and the technician's notes.
 */
export function WorkCard({ booking }: { booking: MockBooking }) {
  const technician = booking.assignedTechnicianName
  const approvedWork = booking.estimateApproved ? booking.estimateItems : []
  return (
    <Card>
      <CardHeader className="border-b">
        <CardHeading>Work to check</CardHeading>
        <CardDescription>
          {technician
            ? `What the customer booked and what ${technician} did.`
            : 'What the customer booked and the work done.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="gap-5">
        {booking.customerNotes ? (
          <Section title="Customer's concern">
            <NoteWell>{booking.customerNotes}</NoteWell>
          </Section>
        ) : null}

        <Section title="Services booked">
          {booking.services.length > 0 ? (
            <ul className="space-y-1.5">
              {booking.services.map((service) => (
                <li key={service} className="flex items-start gap-2 text-sm text-foreground">
                  <Wrench className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
                  {service}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No services on the booking.</p>
          )}
        </Section>

        {approvedWork.length > 0 ? (
          <Section title="Approved work">
            <ul className="divide-y divide-border-faint rounded-xl border border-border-faint">
              {approvedWork.map((line) => (
                <li key={line.id} className="flex items-start justify-between gap-3 px-3 py-2.5">
                  <span className="flex min-w-0 items-start gap-2 text-sm text-foreground">
                    {line.type === 'PART' ? (
                      <Package className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
                    ) : (
                      <Wrench className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
                    )}
                    <span className="min-w-0">
                      {line.description}
                      {line.type === 'PART' && line.quantity > 1 ? (
                        <span className="text-muted-foreground tabular-nums">
                          {' '}
                          × {line.quantity}
                        </span>
                      ) : null}
                    </span>
                  </span>
                  <Badge variant={line.type === 'PART' ? 'info' : 'neutral'}>
                    {line.type === 'PART' ? 'Part' : 'Labour'}
                  </Badge>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {booking.inspectionNotes ? (
          <Section title={technician ? `${technician}'s notes` : "Technician's notes"}>
            <NoteWell>{booking.inspectionNotes}</NoteWell>
          </Section>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** A re-test: the issue the last QC round raised, so the inspector checks that fix first. */
export function PreviousIssueAlert({ booking }: { booking: MockBooking }) {
  const issue = parseQcIssue(booking.qcNotes)
  return (
    <Alert variant="warning" role="note">
      <RotateCcw aria-hidden="true" />
      <AlertTitle>Re-test: this car failed its last QC</AlertTitle>
      <AlertDescription className="space-y-1">
        {issue ? (
          <>
            <span className="block font-semibold">{issue.title}</span>
            {issue.description ? (
              <span className="block whitespace-pre-line">{issue.description}</span>
            ) : null}
          </>
        ) : (
          'Check the fix for the issue raised last time.'
        )}
      </AlertDescription>
    </Alert>
  )
}
