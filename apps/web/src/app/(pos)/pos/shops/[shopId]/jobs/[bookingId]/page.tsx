'use client'

import {
  ArrowLeft,
  CircleAlert,
  ClipboardCheck,
  Play,
  SearchX,
  Send,
  ShieldAlert,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { toast } from 'sonner'

import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { getSaRecord, type SaActivity } from '@/components/pos/sa-booking/sa-records'
import {
  AddLineForm,
  EstimateLines,
  EstimateTotalsWell,
  type NewLine,
} from '@/components/pos/technician/estimate'
import { JobActivity } from '@/components/pos/technician/job-activity'
import {
  attributeSelector,
  countLabel,
  currentReturn,
  estimateNote,
  estimateTotals,
  isOwnJob,
  isQcReturned,
  nextStep,
  ownTechnicianMember,
  parseQcIssue,
  slotSentence,
  technicianAction,
  vehicleLabel,
  type JobAction,
  type JobTone,
} from '@/components/pos/technician/job-model'
import { JobDetailSkeleton } from '@/components/pos/technician/job-skeletons'
import {
  CARD_TITLE,
  JobActionBar,
  PlateTag,
  ReadOnlyBanner,
  ReturnedNotice,
  ToneTile,
} from '@/components/pos/technician/job-ui'
import { StatusBadge } from '@/components/status-badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { Textarea } from '@/components/ui/textarea'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { DEFAULT_SHOP_TZ, formatPKR } from '@/lib/format'
import {
  getBookingById,
  getCurrentUser,
  getShopById,
  getTeamMembers,
  saveBooking,
  type MockBooking,
  type MockEstimateItem,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'
import { cn } from '@/lib/utils'

const ACTIONS: Record<JobAction, { label: string; icon: LucideIcon }> = {
  'start-inspection': { label: 'Start inspection', icon: Play },
  'submit-estimate': { label: 'Submit estimate', icon: Send },
  'start-repair': { label: 'Start repair', icon: Wrench },
  'send-to-qc': { label: 'Finish repair & send to QC', icon: ClipboardCheck },
}

const EYEBROW_INK: Record<JobTone, string> = {
  brand: 'text-brand-blue-ink',
  danger: 'text-danger-ink',
  success: 'text-success-ink',
  neutral: 'text-muted-foreground',
  inspection: 'text-status-inspection-fg',
  repair: 'text-status-repair-qc-fg',
}

const KILOMETRES = new Intl.NumberFormat('en-PK')

/**
 * T-02 Job detail (spec 10): the vehicle and the customer's concern, the next step, inspection
 * notes, the estimate editor (part and labour lines), the QC issue or the declined estimate sent
 * back. Tablet-first: `DetailLayout` keeps one column (next step first) until the page is wide
 * enough for its side column, and the action stays pinned to the bottom until `xl`. A technician
 * opens only their own jobs (D21).
 */
export default function TechnicianJobDetailPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const bookingId = typeof params?.bookingId === 'string' ? params.bookingId : ''

  const ready = useMockStoreReady()
  const stored = useMockStore(() => getBookingById(bookingId))
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const saRecord = useMockStore(() => getSaRecord(bookingId))

  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  // Wait for this browser's stored data: the editor below starts from the stored job, never
  // from the seed copy React hydrates with.
  if (!ready) return <JobDetailSkeleton />

  // D16: the Owner's view of a technician's job is read-only (lib/pos-access).
  const readOnly = sectionAccess(user.role, 'jobs') === 'read'
  // D20: another shop's booking reads as not found, never as someone else's job. D21: so does
  // another technician's job, for a technician (the Owner's view reads every technician's).
  const booking =
    stored &&
    (stored.shopId === shopId || stored.shopSlug === shopId) &&
    (readOnly || isOwnJob(stored, ownTechnicianMember(team, user.email)))
      ? stored
      : undefined

  if (!booking) {
    return (
      <Empty className="border bg-card py-16 sm:py-20">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <SearchX aria-hidden="true" />
          </EmptyMedia>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            We couldn’t find this job
          </h1>
          <EmptyDescription className="text-base">
            It may have been reassigned, or the link is out of date.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild size="lg">
            <Link href={`${base}/jobs`}>
              {readOnly ? 'Back to technician jobs' : 'Back to my jobs'}
            </Link>
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <JobDetail
      key={booking.id}
      booking={booking}
      base={base}
      readOnly={readOnly}
      showTechnician={readOnly || booking.assignedTechnicianName !== user.name}
      returned={currentReturn(booking.status, saRecord.activity)}
      timeZone={shop?.timezone ?? DEFAULT_SHOP_TZ}
    />
  )
}

function JobDetail({
  booking,
  base,
  readOnly,
  showTechnician,
  returned,
  timeZone,
}: {
  booking: MockBooking
  base: string
  readOnly: boolean
  showTechnician: boolean
  /** The service advisor's return of the estimate (T11) that put the job back in inspection. */
  returned: SaActivity | undefined
  timeZone: string
}) {
  const [notes, setNotes] = useState(booking.inspectionNotes || '')
  const [items, setItems] = useState<MockEstimateItem[]>(booking.estimateItems || [])
  const [submitOpen, setSubmitOpen] = useState(false)
  const [qcOpen, setQcOpen] = useState(false)
  const [emptyError, setEmptyError] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const descriptionRef = useRef<HTMLInputElement>(null)
  const nextStepRef = useRef<HTMLHeadingElement>(null)
  const estimateTitleRef = useRef<HTMLHeadingElement>(null)
  /** Set when a confirmed action hands the job to someone else (focus then goes to Next step). */
  const handedOff = useRef(false)

  const status = booking.status
  const editing = !readOnly && status === 'INSPECTING'
  const action = readOnly ? null : technicianAction(status)
  const qcReturned = isQcReturned(booking)
  const qcIssue = parseQcIssue(booking.qcNotes)
  const step = nextStep(booking)
  // The Owner reads the technician's next step, not their own (D16).
  const stepEyebrow = readOnly && technicianAction(status) ? 'Technician’s next step' : step.eyebrow
  const lines = editing ? items : booking.estimateItems
  const totals = estimateTotals(lines)
  const savedNotes = booking.inspectionNotes?.trim()
  const jobsHref = `${base}/jobs`

  const handleAddLineItem = ({ description, type, quantity, unitPrice }: NewLine) => {
    if (!description.trim()) return
    const qty = Number(quantity) || 1
    const price = Number(unitPrice) || 0
    const newItem: MockEstimateItem = {
      id: `est-${Date.now()}`,
      description: description.trim(),
      type,
      quantity: qty,
      unit_price: price,
      total: qty * price,
    }
    const updatedItems = [...items, newItem]
    setItems(updatedItems)

    // Auto save to booking
    const total = updatedItems.reduce((sum, it) => sum + it.total, 0)
    saveBooking({
      ...booking,
      estimateItems: updatedItems,
      estimateTotal: total,
    })
    setAnnouncement(
      `Added ${newItem.description}. ${countLabel(updatedItems.length, 'line', 'lines')}, total ${formatPKR(total)}.`,
    )
  }

  const handleDeleteLineItem = (item: MockEstimateItem) => {
    const updatedItems = items.filter((it) => it.id !== item.id)
    const total = updatedItems.reduce((sum, it) => sum + it.total, 0)
    flushSync(() => {
      setItems(updatedItems)
      saveBooking({
        ...booking,
        estimateItems: updatedItems,
        estimateTotal: total,
      })
      setAnnouncement(
        `Removed ${item.description}. ${countLabel(updatedItems.length, 'line', 'lines')}, total ${formatPKR(total)}.`,
      )
    })
    // The row and its button are gone: focus the line that took its place (or the one before
    // it), or the estimate's title when no line is left.
    const index = items.findIndex((it) => it.id === item.id)
    const neighbour = updatedItems[index] ?? updatedItems[index - 1]
    const nextButton = neighbour
      ? [
          ...document.querySelectorAll<HTMLElement>(
            attributeSelector('data-line-remove', neighbour.id),
          ),
        ].find((button) => button.getClientRects().length > 0)
      : undefined
    ;(nextButton ?? estimateTitleRef.current)?.focus()
  }

  const handleStartInspection = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'INSPECTING',
    }
    saveBooking(updated)
    toast.success('Inspection started', {
      description: 'Write your notes and build the estimate.',
    })
  }

  const handleSubmitEstimate = () => {
    const total = items.reduce((sum, it) => sum + it.total, 0)
    const updated: MockBooking = {
      ...booking,
      status: 'ESTIMATE_REVIEW',
      inspectionNotes: notes,
      estimateItems: items,
      estimateTotal: total,
    }
    saveBooking(updated)
    handedOff.current = true
    setSubmitOpen(false)
    toast.success('Estimate sent to the service advisor', {
      description: `${booking.reference} · ${formatPKR(total)}`,
    })
  }

  const handleStartRepair = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'IN_REPAIR',
    }
    saveBooking(updated)
    toast.success('Repair started', {
      description: 'Send the car to QC when the work is done.',
    })
  }

  const handleSendToQc = () => {
    const updated: MockBooking = {
      ...booking,
      status: 'QC_PENDING',
    }
    saveBooking(updated)
    handedOff.current = true
    setQcOpen(false)
    toast.success('Sent to QC', { description: 'A QC inspector checks the car next.' })
  }

  // An empty estimate can't be submitted (ESTIMATE_EMPTY, spec 09 §2.9): say so and focus the editor.
  const requestSubmit = () => {
    if (items.length === 0) {
      setEmptyError(true)
      descriptionRef.current?.focus()
      return
    }
    setSubmitOpen(true)
  }

  const runAction = (next: JobAction) => {
    if (next === 'start-inspection') handleStartInspection()
    else if (next === 'submit-estimate') requestSubmit()
    else if (next === 'start-repair') handleStartRepair()
    else setQcOpen(true)
  }

  // After a confirmed hand-off the dialog's trigger is gone: focus the new "Next step" instead.
  const focusNextStep = (event: Event) => {
    if (!handedOff.current) return
    handedOff.current = false
    event.preventDefault()
    nextStepRef.current?.focus()
  }

  const actionMeta = action ? ACTIONS[action] : null
  const ActionIcon = actionMeta?.icon
  const primary =
    action && actionMeta && ActionIcon ? (
      <Button size="lg" onClick={() => runAction(action)}>
        <ActionIcon aria-hidden="true" data-icon="inline-start" />
        {action === 'send-to-qc' && qcReturned ? 'Send back to QC' : actionMeta.label}
      </Button>
    ) : null

  const headerMeta = [
    `Booked by ${booking.customerName} for ${slotSentence(booking)}`,
    booking.vehicleColor,
    booking.mileageKm !== undefined ? `${KILOMETRES.format(booking.mileageKm)} km` : null,
    showTechnician && booking.assignedTechnicianName
      ? `Technician: ${booking.assignedTechnicianName}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div
      className={cn(
        'space-y-6',
        // Keep focused controls clear of the bottom action bar (WCAG 2.4.11).
        primary &&
          'max-xl:[&_a]:scroll-mb-28 max-xl:[&_button]:scroll-mb-28 max-xl:[&_input]:scroll-mb-28 max-xl:[&_textarea]:scroll-mb-28',
      )}
    >
      <PageHeader
        back={{ href: jobsHref, label: readOnly ? 'Technician jobs' : 'My jobs' }}
        eyebrow={
          <>
            Job <span className="font-mono">{booking.reference}</span>
          </>
        }
        title={vehicleLabel(booking)}
        badges={
          <>
            <PlateTag plate={booking.licensePlate} size="lg" />
            <StatusBadge status={status} audience="staff" size="md" />
          </>
        }
        description={headerMeta}
      />

      {readOnly ? <ReadOnlyBanner href={`${base}/bookings/${booking.id}`} scope="booking" /> : null}

      {qcReturned ? (
        <Alert variant="destructive">
          <ShieldAlert aria-hidden="true" />
          <AlertTitle>QC sent this job back</AlertTitle>
          <AlertDescription className="space-y-0.5">
            {qcIssue ? (
              <>
                <div className="font-semibold text-foreground">{qcIssue.title}</div>
                {qcIssue.detail ? <div>{qcIssue.detail}</div> : null}
              </>
            ) : (
              <div>Ask the QC inspector what needs fixing.</div>
            )}
          </AlertDescription>
        </Alert>
      ) : null}

      {returned ? (
        <ReturnedNotice
          returned={returned}
          to={readOnly ? (booking.assignedTechnicianName ?? 'the technician') : 'you'}
          timeZone={timeZone}
        />
      ) : null}

      <DetailLayout
        aside={
          <>
            <Card>
              <CardHeader>
                <div className="flex items-start gap-3">
                  <ToneTile icon={step.icon} tone={step.tone} />
                  <div className="min-w-0 space-y-0.5">
                    <p className={cn('text-sm font-semibold', EYEBROW_INK[step.tone])}>
                      {stepEyebrow}
                    </p>
                    <h2 ref={nextStepRef} tabIndex={-1} className={cn(CARD_TITLE, 'outline-none')}>
                      {step.title}
                    </h2>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="gap-4">
                <p className="text-sm text-muted-foreground">{step.body}</p>
                {editing ? (
                  <div className="flex items-baseline justify-between gap-4 rounded-xl bg-layer px-4 py-3 text-sm">
                    <span className="text-muted-foreground">
                      Estimate · {countLabel(lines.length, 'line', 'lines')}
                    </span>
                    <span className="text-base font-bold text-foreground tabular-nums">
                      {formatPKR(totals.total)}
                    </span>
                  </div>
                ) : null}
                {/* Beside the content from `xl`; below it, in the pinned bar (`JobActionBar`). */}
                {primary ? <div className="hidden xl:grid">{primary}</div> : null}
                {!primary && !readOnly ? (
                  <Button asChild variant="outline" size="lg">
                    <Link href={jobsHref}>
                      <ArrowLeft aria-hidden="true" data-icon="inline-start" />
                      Back to my jobs
                    </Link>
                  </Button>
                ) : null}
              </CardContent>
            </Card>

            {booking.qcNotes && !qcReturned ? (
              <Card>
                <CardHeader>
                  <h2 className={CARD_TITLE}>Quality check</h2>
                  <CardAction>
                    {booking.qcPassed ? (
                      <Badge variant="success">Passed</Badge>
                    ) : (
                      <Badge variant="destructive">Sent back</Badge>
                    )}
                  </CardAction>
                </CardHeader>
                <CardContent>
                  {booking.qcPassed || !qcIssue ? (
                    <p className="text-sm text-foreground">{booking.qcNotes}</p>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-foreground">{qcIssue.title}</p>
                      {qcIssue.detail ? (
                        <p className="text-sm text-muted-foreground">{qcIssue.detail}</p>
                      ) : null}
                      <p className="text-sm text-helper">From the last QC round.</p>
                    </>
                  )}
                </CardContent>
              </Card>
            ) : null}
          </>
        }
      >
        <Card>
          <CardHeader>
            <h2 className={CARD_TITLE}>Customer concern</h2>
          </CardHeader>
          <CardContent className="gap-5">
            {booking.customerNotes ? (
              <figure className="space-y-2">
                <blockquote className="rounded-xl bg-layer px-4 py-3 text-base leading-relaxed whitespace-pre-line text-foreground">
                  &ldquo;{booking.customerNotes}&rdquo;
                </blockquote>
                <figcaption className="text-sm text-muted-foreground">
                  {booking.customerName}, when booking
                </figcaption>
              </figure>
            ) : (
              <p className="text-sm text-muted-foreground">
                {booking.customerName} didn’t describe a problem when booking.
              </p>
            )}
            <div className="space-y-2.5">
              <h3 className="text-sm leading-5 font-semibold text-foreground">Work requested</h3>
              <ul className="space-y-2">
                {booking.services.map((service, index) => (
                  <li
                    key={`${index}-${service}`}
                    className="flex items-start gap-2.5 text-base text-foreground"
                  >
                    <Wrench className="mt-1 size-4 shrink-0 text-helper" aria-hidden="true" />
                    {service}
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 id="inspection-notes-title" className={CARD_TITLE}>
              Inspection notes
            </h2>
            <CardDescription id="inspection-notes-description">
              {editing
                ? 'What you found: fault codes, measurements, leaks. The service advisor reads them with the estimate, and they appear on the customer’s report.'
                : 'What the technician found during the inspection.'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {editing ? (
              <>
                <Textarea
                  id="inspection-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  aria-labelledby="inspection-notes-title"
                  aria-describedby="inspection-notes-description inspection-notes-hint"
                  placeholder="For example: front pads at 2 mm, rotor lightly grooved, oil 0.5 L low"
                  className="min-h-32"
                />
                <p id="inspection-notes-hint" className="text-sm text-helper">
                  Saved with the estimate when you submit it.
                </p>
              </>
            ) : savedNotes ? (
              <p className="rounded-xl bg-layer px-4 py-3 text-base leading-relaxed whitespace-pre-line text-foreground">
                {booking.inspectionNotes}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                {status === 'ASSIGNED' && !readOnly
                  ? 'Start the inspection to write your notes.'
                  : 'No inspection notes yet.'}
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="@container gap-0 py-0">
          <CardHeader
            className={cn(
              'pt-(--card-spacing)',
              lines.length > 0 || editing ? 'border-b' : 'pb-(--card-spacing)',
            )}
          >
            <h2 ref={estimateTitleRef} tabIndex={-1} className={cn(CARD_TITLE, 'outline-none')}>
              Estimate
            </h2>
            <CardDescription>{estimateNote(booking, lines.length, readOnly)}</CardDescription>
            {lines.length > 0 ? (
              <CardAction>
                <Badge variant="secondary" className="tabular-nums">
                  {countLabel(lines.length, 'line', 'lines')}
                </Badge>
              </CardAction>
            ) : null}
          </CardHeader>
          {lines.length > 0 ? (
            <>
              <EstimateLines items={lines} onRemove={editing ? handleDeleteLineItem : undefined} />
              <div className="border-t border-border-faint px-5 py-5 sm:px-6">
                <EstimateTotalsWell totals={totals} />
              </div>
            </>
          ) : editing ? (
            <p className="px-5 py-6 text-sm text-muted-foreground sm:px-6">
              No lines yet. Add the first part or labour line below.
            </p>
          ) : null}
          {editing ? (
            <AddLineForm
              onAdd={handleAddLineItem}
              descriptionRef={descriptionRef}
              notice={
                emptyError && items.length === 0 ? (
                  <Alert variant="destructive">
                    <CircleAlert aria-hidden="true" />
                    <AlertTitle>Add at least one part or labour line first.</AlertTitle>
                  </Alert>
                ) : null
              }
            />
          ) : null}
        </Card>

        <JobActivity booking={booking} timeZone={timeZone} />
      </DetailLayout>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {/* Last child, so it rests at the very end of the page when scrolled down. */}
      {primary ? (
        <JobActionBar
          summary={
            editing ? (
              <>
                <span className="font-semibold text-foreground tabular-nums">
                  {formatPKR(totals.total)}
                </span>{' '}
                · {countLabel(lines.length, 'line', 'lines')}
              </>
            ) : (
              <>
                <span className="font-mono font-semibold text-foreground">{booking.reference}</span>{' '}
                · {step.title}
              </>
            )
          }
        >
          {primary}
        </JobActionBar>
      ) : null}

      <Dialog open={submitOpen} onOpenChange={setSubmitOpen}>
        <DialogContent onCloseAutoFocus={focusNextStep}>
          <DialogHeader>
            <DialogTitle>Submit the estimate for {booking.reference}?</DialogTitle>
            <DialogDescription>
              The service advisor reviews it before it goes to {booking.customerName}. You can’t
              change it after you submit.
            </DialogDescription>
          </DialogHeader>
          <EstimateTotalsWell totals={totals} />
          <div className="space-y-1.5">
            <p className="text-sm font-semibold text-foreground">Inspection notes</p>
            {notes.trim() ? (
              <p className="line-clamp-4 text-sm whitespace-pre-line text-muted-foreground">
                {notes}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No notes yet. Notes help the service advisor explain the work to the customer.
              </p>
            )}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" size="lg">
                Keep editing
              </Button>
            </DialogClose>
            <Button size="lg" onClick={handleSubmitEstimate}>
              <Send aria-hidden="true" data-icon="inline-start" />
              Submit estimate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={qcOpen} onOpenChange={setQcOpen}>
        <DialogContent onCloseAutoFocus={focusNextStep}>
          <DialogHeader>
            <DialogTitle>Send {booking.reference} to QC?</DialogTitle>
            <DialogDescription>
              {qcReturned
                ? 'Confirm you fixed the issue QC raised. A QC inspector checks the car again.'
                : 'Confirm the repair is finished. A QC inspector checks the car before it is ready for pick-up.'}
            </DialogDescription>
          </DialogHeader>
          {qcReturned && qcIssue ? (
            <div className="space-y-1 rounded-xl bg-layer p-4 text-sm">
              <p className="font-medium text-foreground">{qcIssue.title}</p>
              <p className="text-muted-foreground">This issue will be marked as fixed.</p>
            </div>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" size="lg">
                Not yet
              </Button>
            </DialogClose>
            <Button size="lg" onClick={handleSendToQc}>
              <ClipboardCheck aria-hidden="true" data-icon="inline-start" />
              Send to QC
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
