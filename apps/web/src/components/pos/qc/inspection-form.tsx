'use client'

import { Check, ShieldCheck, ShieldX, X } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { DetailLayout, StickyActionBar, detailLayoutOnly } from '@/components/layout/detail-layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
import type { MockBooking } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { FailQcDialog } from './fail-qc-dialog'
import { PreviousIssueAlert, WorkCard } from './job-context'
import { PassFailControl } from './pass-fail-control'
import {
  ITEM_NOTE_MAX,
  NOTES_MAX,
  QC_CHECKLIST,
  checklistProgress,
  clearDraft,
  isRetest,
  issueDescriptionFrom,
  issueTitleFrom,
  passBlocker,
  plural,
  readDraft,
  validateIssue,
  writeDraft,
  type ChecklistProgress,
  type IssueErrors,
  type QcAnswer,
  type QcChecklistKey,
  type QcDraft,
} from './qc-data'
import { CardHeading } from './qc-ui'

/** The row's number until it is answered, then a check or a cross (decorative). */
function StepMarker({ index, answer }: { index: number; answer: QcAnswer | undefined }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold tabular-nums',
        answer === 'pass' && 'bg-success-subtle text-success-ink',
        answer === 'fail' && 'bg-danger-subtle text-danger-ink',
        answer === undefined && 'border border-border-medium bg-card text-muted-foreground',
      )}
    >
      {answer === 'pass' ? (
        <Check className="size-4" />
      ) : answer === 'fail' ? (
        <X className="size-4" />
      ) : (
        index + 1
      )}
    </span>
  )
}

function ProgressSummary({ progress }: { progress: ChecklistProgress }) {
  const label = `${progress.answered} of ${progress.total} checks done`
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
        <span className="font-semibold text-foreground tabular-nums">{label}</span>
        {progress.failed > 0 ? (
          <span className="inline-flex items-center gap-1 font-medium text-danger-ink tabular-nums">
            <X className="size-4" aria-hidden="true" />
            {progress.failed} failed
          </span>
        ) : null}
      </div>
      <Progress
        value={Math.round((progress.answered / progress.total) * 100)}
        aria-label="Checklist progress"
        getValueLabel={() => label}
      />
    </div>
  )
}

/** The hint under a check; "Customer complaint resolved" quotes what the customer booked for. */
function hintFor(item: (typeof QC_CHECKLIST)[number], booking: MockBooking): string {
  if (item.key !== 'complaint_resolved') return item.hint
  if (booking.customerNotes) return `The customer said: “${booking.customerNotes}”`
  if (booking.services.length > 0) return `Booked for: ${booking.services.join(', ')}.`
  return item.hint
}

export interface InspectionFormProps {
  booking: MockBooking
  /** E-37 `pass-qc`; false when the job can no longer be passed (it left QC meanwhile). */
  onPass: (notes: string) => boolean
  /** E-37 `fail-qc`; false when the job can no longer be failed. */
  onFail: (title: string, description: string) => boolean
}

/**
 * QI-02's checklist form (spec 10): one Pass / Fail per D46 check with an optional note on a fail,
 * optional inspection notes, then Pass QC (every check passed) or Fail QC (an issue for the
 * technician). The form is kept in `sessionStorage` per booking until QC is passed or failed (R9).
 * Mounted on the client only, after the mock store is ready, so the stored draft is safe to read.
 */
export function InspectionForm({ booking, onPass, onFail }: InspectionFormProps) {
  const id = useId()
  const [draft, setDraft] = useState<QcDraft>(() => readDraft(booking.id))
  const [attempted, setAttempted] = useState(false)
  const [failOpen, setFailOpen] = useState(false)
  const [issue, setIssue] = useState({ title: '', description: '' })
  const [issueEdited, setIssueEdited] = useState(false)
  const [issueErrors, setIssueErrors] = useState<IssueErrors>({})

  const technician = booking.assignedTechnicianName
  const progress = checklistProgress(draft.answers)
  const blocker = attempted ? passBlocker(draft.answers) : null
  const blockerText =
    blocker === 'incomplete'
      ? `Answer every check before you pass QC: ${plural(progress.total - progress.answered, 'check')} left.`
      : blocker === 'failed'
        ? `${plural(progress.failed, 'check')} failed. Use Fail QC to send the car back${technician ? ` to ${technician}` : ''}.`
        : null
  const rowId = (key: QcChecklistKey) => `${id}-${key}`

  // Keep the form across visits until QC is passed or failed (R9); both clear it.
  useEffect(() => {
    writeDraft(booking.id, draft)
  }, [booking.id, draft])

  // Any change to the form prefills the fail dialog's issue from it again.
  const setAnswer = (key: QcChecklistKey, answer: QcAnswer) => {
    setDraft((prev) => ({ ...prev, answers: { ...prev.answers, [key]: answer } }))
    setIssueEdited(false)
  }
  const setItemNote = (key: QcChecklistKey, note: string) => {
    setDraft((prev) => ({ ...prev, itemNotes: { ...prev.itemNotes, [key]: note } }))
    setIssueEdited(false)
  }
  const setNotes = (notes: string) => {
    setDraft((prev) => ({ ...prev, notes }))
    setIssueEdited(false)
  }

  const handlePass = () => {
    setAttempted(true)
    const reason = passBlocker(draft.answers)
    if (reason === 'incomplete') {
      const first = QC_CHECKLIST.find((item) => draft.answers[item.key] === undefined)
      const radio = first ? document.getElementById(`${rowId(first.key)}-pass`) : null
      radio?.scrollIntoView({ block: 'center' })
      radio?.focus({ preventScroll: true })
      return
    }
    if (reason === 'failed') return
    if (onPass(draft.notes.trim())) clearDraft(booking.id)
  }

  const openFail = () => {
    if (!issueEdited) {
      setIssue({
        title: issueTitleFrom(draft.answers),
        description: issueDescriptionFrom(draft.answers, draft.itemNotes, draft.notes),
      })
    }
    setIssueErrors({})
    setFailOpen(true)
  }

  const confirmFail = (): 'title' | 'description' | null => {
    const errors = validateIssue(issue.title, issue.description)
    setIssueErrors(errors)
    if (errors.title) return 'title'
    if (errors.description) return 'description'
    if (onFail(issue.title.trim(), issue.description.trim())) {
      clearDraft(booking.id)
      setFailOpen(false)
    }
    return null
  }

  const passButton = (
    <Button size="lg" onClick={handlePass}>
      <ShieldCheck aria-hidden="true" />
      Pass QC
    </Button>
  )
  const failButton = (
    <Button size="lg" variant="destructive-outline" onClick={openFail}>
      <ShieldX aria-hidden="true" />
      Fail QC
    </Button>
  )

  return (
    <>
      <DetailLayout
        aside={
          <>
            {/* Two columns: the decision beside the checklist. One column: the pinned bar below. */}
            <Card className={detailLayoutOnly.twoColumns}>
              <CardHeader>
                <CardHeading>Your decision</CardHeading>
                <CardDescription>Every check must pass before you can pass QC.</CardDescription>
              </CardHeader>
              <CardContent className="gap-4">
                <ProgressSummary progress={progress} />
                {blockerText ? (
                  <p role="alert" className="text-sm font-medium text-destructive">
                    {blockerText}
                  </p>
                ) : null}
                <div className="grid gap-2">
                  {passButton}
                  {failButton}
                </div>
                <p className="text-sm text-muted-foreground">
                  Pass QC marks the car ready for pick-up and tells the service advisor. Fail QC
                  sends it back to {technician ?? 'the technician'} with the issue.
                </p>
              </CardContent>
            </Card>
            <WorkCard booking={booking} />
          </>
        }
        // The checklist is the task: first on phones and tablets, the job's context after it.
        asideFirstOnMobile={false}
      >
        {isRetest(booking) ? <PreviousIssueAlert booking={booking} /> : null}
        <Card className="@container/checklist gap-0 py-0">
          <CardHeader className="border-b pt-(--card-spacing)">
            <CardHeading id={`${id}-checklist`}>Checklist</CardHeading>
            <CardDescription>
              Check each item on the car and choose Pass or Fail. Add a note when something fails.
            </CardDescription>
          </CardHeader>
          <ol className="divide-y divide-border-faint" aria-labelledby={`${id}-checklist`}>
            {QC_CHECKLIST.map((item, index) => {
              const base = rowId(item.key)
              const answer = draft.answers[item.key]
              const invalid = attempted && answer === undefined
              const note = draft.itemNotes[item.key] ?? ''
              return (
                <li key={item.key} className="px-5 py-5 sm:px-6">
                  <div className="flex flex-col gap-4 @xl/checklist:flex-row @xl/checklist:items-center @xl/checklist:justify-between @xl/checklist:gap-6">
                    <div className="flex min-w-0 gap-3">
                      <StepMarker index={index} answer={answer} />
                      <div className="min-w-0 space-y-1 pt-1">
                        <h3
                          id={`${base}-label`}
                          className="text-base leading-6 font-semibold text-foreground"
                        >
                          {item.label}
                        </h3>
                        <p id={`${base}-hint`} className="text-sm text-muted-foreground">
                          {hintFor(item, booking)}
                        </p>
                      </div>
                    </div>
                    <PassFailControl
                      id={base}
                      value={answer}
                      onValueChange={(value) => setAnswer(item.key, value)}
                      labelledBy={`${base}-label`}
                      describedBy={`${base}-hint${invalid ? ` ${base}-error` : ''}`}
                      invalid={invalid}
                      className="@xl/checklist:w-64"
                    />
                  </div>
                  {invalid ? (
                    <p
                      id={`${base}-error`}
                      className="mt-3 text-sm font-medium text-destructive @xl/checklist:pl-11"
                    >
                      Choose Pass or Fail.
                    </p>
                  ) : null}
                  {answer === 'fail' ? (
                    <Field className="mt-4 @xl/checklist:pl-11">
                      <FieldLabel htmlFor={`${base}-note`}>
                        What did you find?
                        <span className="font-normal text-muted-foreground">Optional</span>
                      </FieldLabel>
                      <Textarea
                        id={`${base}-note`}
                        value={note}
                        onChange={(event) => setItemNote(item.key, event.target.value)}
                        maxLength={ITEM_NOTE_MAX}
                        rows={2}
                        placeholder="Where it is and what you saw"
                        className="min-h-20"
                        aria-describedby={`${base}-note-hint`}
                      />
                      <FieldDescription id={`${base}-note-hint`}>
                        Added to the issue for {technician ?? 'the technician'} when you fail QC.{' '}
                        <span className="tabular-nums">
                          {note.length}/{ITEM_NOTE_MAX}
                        </span>
                      </FieldDescription>
                    </Field>
                  ) : null}
                </li>
              )
            })}
          </ol>
        </Card>

        <Card>
          <CardHeader>
            <CardHeading id={`${id}-notes-title`}>Inspection notes</CardHeading>
            <CardDescription id={`${id}-notes-hint`}>
              Optional. Saved on the booking when you pass QC, where the service advisor and the
              customer can read them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Textarea
              value={draft.notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={NOTES_MAX}
              rows={4}
              placeholder="Road-test route, tyre pressures, anything the next person should know"
              aria-labelledby={`${id}-notes-title`}
              aria-describedby={`${id}-notes-hint ${id}-notes-count`}
            />
            <p id={`${id}-notes-count`} className="text-xs text-helper tabular-nums">
              {draft.notes.length}/{NOTES_MAX.toLocaleString('en')}
            </p>
          </CardContent>
        </Card>

        {/* Pinned on phones and tablets too (the checklist is long), until the decision card
            shows beside it. */}
        <StickyActionBar
          role="region"
          aria-label="QC decision"
          pinnedUntil="xl"
          className={cn(
            'flex-col items-stretch gap-3 md:flex-row md:items-center md:justify-between',
            detailLayoutOnly.oneColumn,
          )}
        >
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-foreground tabular-nums">
              {progress.answered} of {progress.total} checks done
              {progress.failed > 0 ? (
                <span className="text-danger-ink"> · {progress.failed} failed</span>
              ) : null}
            </p>
            {blockerText ? (
              <p role="alert" className="text-sm font-medium text-destructive">
                {blockerText}
              </p>
            ) : null}
          </div>
          <div className="grid grid-cols-2 gap-2 md:flex md:shrink-0">
            {failButton}
            {passButton}
          </div>
        </StickyActionBar>
      </DetailLayout>

      <FailQcDialog
        open={failOpen}
        onOpenChange={setFailOpen}
        reference={booking.reference}
        technicianName={technician}
        title={issue.title}
        description={issue.description}
        errors={issueErrors}
        onTitleChange={(title) => {
          setIssue((prev) => ({ ...prev, title }))
          setIssueEdited(true)
        }}
        onDescriptionChange={(description) => {
          setIssue((prev) => ({ ...prev, description }))
          setIssueEdited(true)
        }}
        onConfirm={confirmFail}
      />
    </>
  )
}
