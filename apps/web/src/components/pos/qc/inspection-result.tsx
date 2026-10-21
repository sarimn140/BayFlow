import { Check, Eye, Info, Lock, ShieldCheck, ShieldX } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { DetailLayout } from '@/components/layout/detail-layout'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import type { MockBooking, MockTeamMember } from '@/lib/mock-data'
import { BOOKING_STATUS_META, statusLabel } from '@/lib/status'

import { NoteWell, WorkCard } from './job-context'
import {
  QC_CHECKLIST,
  inspectedAgo,
  isInQc,
  memberName,
  parseQcIssue,
  pickedByOther,
  qcResultOf,
  sinceLabel,
  waitedFor,
  type QcResult,
} from './qc-data'
import { CardHeading } from './qc-ui'

/** Moves focus to the result banner when it replaces the form the inspector just submitted. */
const focusOnMount = (element: HTMLElement | null) => {
  element?.focus()
}

/** "Passed by Hina · 2 days ago", or "Raised just now" when no inspector is recorded. */
function byLine(verb: string, inspector: string | null, when: string): string {
  if (inspector) return when ? `${verb} by ${inspector} · ${when}` : `${verb} by ${inspector}`
  return when ? `${verb} ${when}` : verb
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium text-foreground">{children}</dd>
    </div>
  )
}

export interface InspectionReadOnlyProps {
  booking: MockBooking
  team: ReadonlyArray<MockTeamMember>
  now: Date
  timeZone: string
  /** The Owner's view (D16): QC actions are for QC inspectors only. */
  readOnly: boolean
  myId: string | undefined
  /** This inspector just passed or failed the job: say so and keep focus on the result. */
  justActed: QcResult | null
  queueHref: string
}

/**
 * QI-02 when the checklist is not this viewer's to fill (spec 10): the QC result after a pass or a
 * fail, another inspector's job, the Owner's read-only view, or a job that is not in QC.
 */
export function InspectionReadOnly({
  booking,
  team,
  now,
  timeZone,
  readOnly,
  myId,
  justActed,
  queueHref,
}: InspectionReadOnlyProps) {
  const result = qcResultOf(booking)
  const technician = booking.assignedTechnicianName ?? 'the technician'
  const inspector = memberName(booking.qcInspectorId, team)
  const when = inspectedAgo(booking, now)
  const since = sinceLabel(booking.updatedAt, now, timeZone)
  // Its own cell in the alert's grid (under the text), clear of the description's link styles.
  const backToQueue = (
    <div className="col-start-2 mt-3">
      <Button asChild variant="outline">
        <Link href={queueHref}>Back to QC queue</Link>
      </Button>
    </div>
  )
  const leaving = justActed ? ' Taking you back to the QC queue…' : ''

  let banner: ReactNode
  if (result === 'passed') {
    banner = (
      <Alert
        variant="success"
        role="status"
        tabIndex={-1}
        ref={justActed ? focusOnMount : undefined}
        className="outline-none"
      >
        <ShieldCheck aria-hidden="true" />
        <AlertTitle>{justActed ? 'QC passed' : 'This car passed QC'}</AlertTitle>
        <AlertDescription>
          {booking.status === 'COMPLETED'
            ? 'The customer has collected it.'
            : 'It is ready for pick-up and the service advisor has been told.'}
          {leaving}
        </AlertDescription>
        {backToQueue}
      </Alert>
    )
  } else if (result === 'failed') {
    banner = (
      <Alert
        variant="destructive"
        role="status"
        tabIndex={-1}
        ref={justActed ? focusOnMount : undefined}
        className="outline-none"
      >
        <ShieldX aria-hidden="true" />
        <AlertTitle>
          {justActed
            ? `QC failed: returned to ${technician}`
            : `Failed QC, back with ${technician}`}
        </AlertTitle>
        <AlertDescription>
          It returns to the QC queue for a re-test once {technician} sends it again.{leaving}
        </AlertDescription>
        {backToQueue}
      </Alert>
    )
  } else if (isInQc(booking.status) && readOnly) {
    banner = (
      <Alert variant="info" role="note">
        <Eye aria-hidden="true" />
        <AlertTitle>Read-only view</AlertTitle>
        <AlertDescription>
          QC inspectors pick, pass and fail jobs.{' '}
          {booking.status === 'QC_PENDING'
            ? `This car is waiting for an inspector${since ? ` since ${since}` : ''}.`
            : `${inspector ?? 'An inspector'} is inspecting it${since ? ` since ${since}` : ''}.`}
        </AlertDescription>
      </Alert>
    )
  } else if (pickedByOther(booking, myId)) {
    banner = (
      <Alert variant="info" role="note">
        <Lock aria-hidden="true" />
        <AlertTitle>{inspector ?? 'Another inspector'} is inspecting this job</AlertTitle>
        <AlertDescription>
          {since ? `Inspecting since ${since}. ` : ''}Only the inspector who picked a job can pass
          or fail it.
        </AlertDescription>
      </Alert>
    )
  } else {
    const terminal = BOOKING_STATUS_META[booking.status].terminal
    banner = (
      <Alert variant="info" role="note">
        <Info aria-hidden="true" />
        <AlertTitle>Not in the QC queue</AlertTitle>
        <AlertDescription>
          {booking.reference} is {statusLabel(booking.status, 'staff').toLowerCase()}.
          {terminal ? '' : ' It joins the QC queue when the technician sends it to QC.'}
        </AlertDescription>
      </Alert>
    )
  }

  let main: ReactNode
  if (result === 'passed') {
    main = (
      <Card>
        <CardHeader className="border-b">
          <CardHeading>QC result</CardHeading>
          <CardDescription>{byLine('Passed', inspector, when)}</CardDescription>
        </CardHeader>
        <CardContent className="gap-5">
          <ul className="space-y-2" aria-label="Checklist">
            {QC_CHECKLIST.map((item) => (
              <li key={item.key} className="flex items-center gap-3 text-sm text-foreground">
                <span
                  aria-hidden="true"
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success-subtle text-success-ink"
                >
                  <Check className="size-4" />
                </span>
                <span className="min-w-0 flex-1">{item.label}</span>
                <span className="font-medium text-success-ink">Passed</span>
              </li>
            ))}
          </ul>
          <section className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Inspection notes</h3>
            {booking.qcNotes ? (
              <NoteWell>{booking.qcNotes}</NoteWell>
            ) : (
              <p className="text-sm text-muted-foreground">No notes were added.</p>
            )}
          </section>
        </CardContent>
      </Card>
    )
  } else if (result === 'failed') {
    const issue = parseQcIssue(booking.qcNotes)
    main = (
      <Card>
        <CardHeader className="border-b">
          <CardHeading>Issue for {technician}</CardHeading>
          <CardDescription>{byLine('Raised', inspector, when)}</CardDescription>
        </CardHeader>
        <CardContent className="gap-3">
          {issue ? (
            <>
              <p className="text-base font-semibold text-foreground">{issue.title}</p>
              {issue.description ? <NoteWell>{issue.description}</NoteWell> : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No issue details were recorded.</p>
          )}
        </CardContent>
      </Card>
    )
  } else {
    main = (
      <Card>
        <CardHeader className="border-b">
          <CardHeading>QC status</CardHeading>
        </CardHeader>
        <CardContent>
          <dl className="divide-y divide-border-faint text-sm">
            <DetailRow label="Status">
              <StatusBadge status={booking.status} audience="staff" />
            </DetailRow>
            {booking.status === 'QC_PENDING' ? (
              <DetailRow label="Waiting">{waitedFor(booking.updatedAt, now) || '—'}</DetailRow>
            ) : null}
            {booking.status === 'QC_IN_PROGRESS' ? (
              <>
                <DetailRow label="QC inspector">{inspector ?? 'Not recorded'}</DetailRow>
                <DetailRow label="Picked">{since || '—'}</DetailRow>
              </>
            ) : null}
            <DetailRow label="Technician">
              {booking.assignedTechnicianName ?? 'Not assigned'}
            </DetailRow>
          </dl>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      {banner}
      <DetailLayout aside={<WorkCard booking={booking} />} asideFirstOnMobile={false}>
        {main}
      </DetailLayout>
    </>
  )
}
