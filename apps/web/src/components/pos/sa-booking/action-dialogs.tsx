'use client'

import { CircleAlert } from 'lucide-react'
import { useId, useRef, useState, type ReactNode } from 'react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
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
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldTitle,
} from '@/components/ui/field'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'

import { initials } from './detail-bits'

/** An action the dialog must show and keep open for (spec 09 §2.9: the input is kept). */
export interface ActionError {
  code: string
  message: string
}

/** Returns `null` when the page handled it (done, or closed with a toast). */
export type ConfirmHandler<T> = (input: T) => ActionError | null

/** Spec 09 §2.9: an assignee who is inactive or no longer has the role. */
export const MEMBER_NOT_ELIGIBLE: ActionError = {
  code: 'MEMBER_NOT_ELIGIBLE',
  message: 'That person can’t be assigned — they may be inactive or have another role.',
}

interface ControlledDialog {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Lets the page move focus to the next step after a successful action. */
  onCloseAutoFocus?: (event: Event) => void
}

/** "Every error alert shows a small muted line 'Code: …'" (spec 09 §2.9). */
export function ActionErrorAlert({ error }: { error: ActionError }) {
  return (
    <Alert variant="destructive">
      <CircleAlert aria-hidden="true" />
      <AlertTitle>{error.message}</AlertTitle>
      <AlertDescription>
        <span className="text-xs text-muted-foreground">Code: {error.code}</span>
      </AlertDescription>
    </Alert>
  )
}

/* ------------------------------------------------------------------ assign a member -------- */

export interface MemberOption {
  id: string
  name: string
  openJobs: number
}

function openJobsText(count: number): string {
  if (count === 0) return 'No open jobs'
  return count === 1 ? '1 open job' : `${count} open jobs`
}

/**
 * `assign-technician` / `assign-parts-person` (spec 09 §4.6): a required pick of the shop's active
 * members of that role, each with their open jobs.
 */
export function AssignMemberDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  title,
  description,
  groupLabel,
  members,
  defaultMemberId,
  emptyMessage,
  onConfirm,
}: ControlledDialog & {
  title: string
  description: ReactNode
  /** Names the radio group, e.g. "Technicians". */
  groupLabel: string
  members: ReadonlyArray<MemberOption>
  defaultMemberId?: string
  emptyMessage: string
  onConfirm: ConfirmHandler<string>
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <AssignMemberBody
          title={title}
          description={description}
          groupLabel={groupLabel}
          members={members}
          defaultMemberId={defaultMemberId}
          emptyMessage={emptyMessage}
          onConfirm={onConfirm}
        />
      </DialogContent>
    </Dialog>
  )
}

function AssignMemberBody({
  title,
  description,
  groupLabel,
  members,
  defaultMemberId,
  emptyMessage,
  onConfirm,
}: {
  title: string
  description: ReactNode
  groupLabel: string
  members: ReadonlyArray<MemberOption>
  defaultMemberId?: string
  emptyMessage: string
  onConfirm: ConfirmHandler<string>
}) {
  const id = useId()
  const [selected, setSelected] = useState(() =>
    members.some((member) => member.id === defaultMemberId)
      ? (defaultMemberId ?? '')
      : (members[0]?.id ?? ''),
  )
  const [error, setError] = useState<ActionError | null>(null)
  const chosen = members.find((member) => member.id === selected)
  // The list is live: the person picked may have been deactivated meanwhile (D19). Say so and
  // let the user choose again, rather than switching the choice behind their back.
  const shownError = error ?? (selected && !chosen ? MEMBER_NOT_ELIGIBLE : null)

  const confirm = () => {
    if (!chosen) return
    setError(onConfirm(chosen.id))
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      {members.length === 0 ? (
        <Alert variant="warning">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{emptyMessage}</AlertDescription>
        </Alert>
      ) : (
        <RadioGroup
          value={selected}
          onValueChange={(value) => {
            setSelected(value)
            setError(null)
          }}
          aria-label={groupLabel}
          className="gap-2"
        >
          {members.map((member) => (
            <FieldLabel key={member.id} htmlFor={`${id}-${member.id}`}>
              <Field orientation="horizontal" className="items-center!">
                <span
                  aria-hidden="true"
                  className="flex size-9 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-muted-foreground"
                >
                  {initials(member.name)}
                </span>
                <FieldContent>
                  <FieldTitle>{member.name}</FieldTitle>
                  <FieldDescription>{openJobsText(member.openJobs)}</FieldDescription>
                </FieldContent>
                <RadioGroupItem value={member.id} id={`${id}-${member.id}`} />
              </Field>
            </FieldLabel>
          ))}
        </RadioGroup>
      )}
      {shownError ? <ActionErrorAlert error={shownError} /> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="button" onClick={confirm} disabled={!chosen}>
          {chosen ? `Assign ${chosen.name}` : 'Assign'}
        </Button>
      </DialogFooter>
    </>
  )
}

/* ------------------------------------------------------------------ confirm -------------- */

/** A forward action that only needs a confirmation (send estimate, revise, complete). */
export function ConfirmActionDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  title,
  description,
  confirmLabel,
  children,
  onConfirm,
}: ControlledDialog & {
  title: string
  description: ReactNode
  confirmLabel: string
  /** A summary of what will happen (version, total, recipient). */
  children?: ReactNode
  onConfirm: ConfirmHandler<void>
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <ConfirmBody
          title={title}
          description={description}
          confirmLabel={confirmLabel}
          onConfirm={onConfirm}
        >
          {children}
        </ConfirmBody>
      </DialogContent>
    </Dialog>
  )
}

function ConfirmBody({
  title,
  description,
  confirmLabel,
  children,
  onConfirm,
}: {
  title: string
  description: ReactNode
  confirmLabel: string
  children?: ReactNode
  onConfirm: ConfirmHandler<void>
}) {
  const [error, setError] = useState<ActionError | null>(null)
  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      {children}
      {error ? <ActionErrorAlert error={error} /> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="button" onClick={() => setError(onConfirm())}>
          {confirmLabel}
        </Button>
      </DialogFooter>
    </>
  )
}

/* ------------------------------------------------------------------ text inputs ---------- */

const MAX_TEXT = 500

/**
 * `decline` and `cancel` (spec 09 §4.6, UX rule R6): an `AlertDialog` whose focus starts on the
 * safe button, with a required reason (1–500) and a live counter.
 */
export function ReasonDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  title,
  description,
  reasonLabel,
  placeholder,
  confirmLabel,
  keepLabel,
  onConfirm,
}: ControlledDialog & {
  title: string
  description: string
  reasonLabel: string
  placeholder: string
  confirmLabel: string
  keepLabel: string
  onConfirm: ConfirmHandler<string>
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent onCloseAutoFocus={onCloseAutoFocus}>
        <ReasonBody
          title={title}
          description={description}
          reasonLabel={reasonLabel}
          placeholder={placeholder}
          confirmLabel={confirmLabel}
          keepLabel={keepLabel}
          onConfirm={onConfirm}
        />
      </AlertDialogContent>
    </AlertDialog>
  )
}

function ReasonBody({
  title,
  description,
  reasonLabel,
  placeholder,
  confirmLabel,
  keepLabel,
  onConfirm,
}: {
  title: string
  description: string
  reasonLabel: string
  placeholder: string
  confirmLabel: string
  keepLabel: string
  onConfirm: ConfirmHandler<string>
}) {
  const id = useId()
  const fieldRef = useRef<HTMLTextAreaElement>(null)
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<ActionError | null>(null)

  const confirm = () => {
    if (!reason.trim()) {
      setFieldError('Give a reason. The customer sees it.')
      fieldRef.current?.focus()
      return
    }
    setError(onConfirm(reason.trim()))
  }

  return (
    <>
      <AlertDialogHeader>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        <AlertDialogDescription>{description}</AlertDialogDescription>
      </AlertDialogHeader>
      <Field data-invalid={Boolean(fieldError)}>
        <FieldLabel htmlFor={`${id}-reason`}>{reasonLabel}</FieldLabel>
        <Textarea
          ref={fieldRef}
          id={`${id}-reason`}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value)
            setFieldError(null)
          }}
          maxLength={MAX_TEXT}
          rows={3}
          required
          placeholder={placeholder}
          aria-invalid={Boolean(fieldError)}
          aria-describedby={`${id}-help${fieldError ? ` ${id}-error` : ''}`}
        />
        <FieldDescription id={`${id}-help`} className="tabular-nums">
          Required · {reason.length}/{MAX_TEXT} characters
        </FieldDescription>
        {fieldError ? <FieldError id={`${id}-error`}>{fieldError}</FieldError> : null}
      </Field>
      {error ? <ActionErrorAlert error={error} /> : null}
      <AlertDialogFooter>
        <AlertDialogCancel>{keepLabel}</AlertDialogCancel>
        <Button type="button" variant="destructive" onClick={confirm}>
          {confirmLabel}
        </Button>
      </AlertDialogFooter>
    </>
  )
}

/** `return-to-technician` (spec 09 §4.6): a dialog with an optional note (≤ 500). */
export function NoteDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  title,
  description,
  noteLabel,
  placeholder,
  confirmLabel,
  onConfirm,
}: ControlledDialog & {
  title: string
  description: string
  noteLabel: string
  placeholder: string
  confirmLabel: string
  onConfirm: ConfirmHandler<string>
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" onCloseAutoFocus={onCloseAutoFocus}>
        <NoteBody
          title={title}
          description={description}
          noteLabel={noteLabel}
          placeholder={placeholder}
          confirmLabel={confirmLabel}
          onConfirm={onConfirm}
        />
      </DialogContent>
    </Dialog>
  )
}

function NoteBody({
  title,
  description,
  noteLabel,
  placeholder,
  confirmLabel,
  onConfirm,
}: {
  title: string
  description: string
  noteLabel: string
  placeholder: string
  confirmLabel: string
  onConfirm: ConfirmHandler<string>
}) {
  const id = useId()
  const [note, setNote] = useState('')
  const [error, setError] = useState<ActionError | null>(null)
  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <Field>
        <FieldLabel htmlFor={`${id}-note`}>{noteLabel}</FieldLabel>
        <Textarea
          id={`${id}-note`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={MAX_TEXT}
          rows={3}
          placeholder={placeholder}
          aria-describedby={`${id}-help`}
        />
        <FieldDescription id={`${id}-help`} className="tabular-nums">
          Optional · {note.length}/{MAX_TEXT} characters
        </FieldDescription>
      </Field>
      {error ? <ActionErrorAlert error={error} /> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="outline">
            Cancel
          </Button>
        </DialogClose>
        <Button type="button" onClick={() => setError(onConfirm(note.trim()))}>
          {confirmLabel}
        </Button>
      </DialogFooter>
    </>
  )
}
