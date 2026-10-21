'use client'

import { CircleAlert, CircleCheck, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useId, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { AdminActionError } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

const REASON_MIN = 5
const REASON_MAX = 500

/** Runs an admin action and turns the API's refusals into the dialog's error (spec 19 §1). */
function attempt(run: () => void, success: string): string | null {
  try {
    run()
    toast.success(success)
    return null
  } catch (error) {
    if (error instanceof AdminActionError) return error.message
    throw error
  }
}

/** The API's refusal (409 / 403 / 422), inside the dialog, with the user's input kept. */
function RefusalAlert({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <CircleAlert aria-hidden="true" />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

/**
 * A restricting action that needs a written reason (suspend a shop, deactivate an account): the
 * consequences are listed before the reason field, and the dialog stays open until it succeeds.
 * Focus starts on Cancel (Radix `AlertDialog`); a reason that is too short is flagged on the field
 * and focused, and a refusal from the API shows above the buttons.
 */
export function ReasonDialog({
  trigger,
  title,
  description,
  consequences,
  warning,
  confirmLabel,
  success,
  onConfirm,
  icon: Icon = TriangleAlert,
}: {
  trigger: ReactNode
  title: string
  description: string
  consequences: ReadonlyArray<string>
  warning?: string | null
  confirmLabel: string
  success: string
  onConfirm: (reason: string) => void
  /** The dialog's icon tile (danger tint); defaults to a warning triangle. */
  icon?: LucideIcon
}) {
  const id = useId()
  const reasonRef = useRef<HTMLTextAreaElement>(null)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const length = reason.trim().length
  const tooShort = length < REASON_MIN

  const confirm = () => {
    if (tooShort || length > REASON_MAX) {
      setError(`Give a reason of ${REASON_MIN} to ${REASON_MAX} characters.`)
      setRefusal(null)
      reasonRef.current?.focus()
      return
    }
    const refused = attempt(() => onConfirm(reason), success)
    if (refused) {
      setRefusal(refused)
      return
    }
    setOpen(false)
    setReason('')
    setError(null)
    setRefusal(null)
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setError(null)
          setRefusal(null)
        }
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      {/* Tall on small phones (consequences, warning, field): the primitive scrolls inside. */}
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia className="bg-danger-subtle text-danger-ink">
            <Icon aria-hidden="true" />
          </AlertDialogMedia>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <div className="rounded-xl bg-layer px-4 py-3.5">
          <p className="text-sm font-semibold text-foreground">What happens</p>
          <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
            {consequences.map((line) => (
              <li key={line} className="flex gap-2.5">
                <span
                  aria-hidden="true"
                  className="mt-[7px] size-1.5 shrink-0 rounded-full bg-subtle-foreground"
                />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
        {warning && (
          <Alert variant="warning">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>{warning}</AlertDescription>
          </Alert>
        )}
        <Field data-invalid={Boolean(error)}>
          <FieldLabel htmlFor={`${id}-reason`}>Reason</FieldLabel>
          <Textarea
            ref={reasonRef}
            id={`${id}-reason`}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value)
              setError(null)
            }}
            maxLength={REASON_MAX}
            rows={3}
            aria-invalid={Boolean(error)}
            aria-describedby={`${id}-help${error ? ` ${id}-error` : ''}`}
          />
          <FieldDescription id={`${id}-help`} className="flex items-start justify-between gap-4">
            <span>
              {REASON_MIN} to {REASON_MAX} characters. Recorded in the audit log and shown to other
              admins.
            </span>
            <span className="shrink-0 tabular-nums">
              {length}/{REASON_MAX}
            </span>
          </FieldDescription>
          {error && <FieldError id={`${id}-error`}>{error}</FieldError>}
        </Field>
        {refusal && <RefusalAlert message={refusal} />}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button variant="destructive" onClick={confirm}>
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

/** A reversible action that needs only a confirmation (reactivate, grant or revoke admin). */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  success,
  destructive = false,
  onConfirm,
  icon,
}: {
  trigger: ReactNode
  title: string
  description: string
  confirmLabel: string
  success: string
  destructive?: boolean
  onConfirm: () => void
  /** The dialog's icon tile; defaults to a warning triangle (destructive) or a check. */
  icon?: LucideIcon
}) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const Icon = icon ?? (destructive ? TriangleAlert : CircleCheck)

  const confirm = () => {
    const refused = attempt(onConfirm, success)
    if (refused) {
      setError(refused)
      return
    }
    setOpen(false)
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setError(null)
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia
            className={cn(
              destructive
                ? 'bg-danger-subtle text-danger-ink'
                : 'bg-brand-blue-subtle text-brand-blue-ink',
            )}
          >
            <Icon aria-hidden="true" />
          </AlertDialogMedia>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {error && <RefusalAlert message={error} />}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button variant={destructive ? 'destructive' : 'default'} onClick={confirm}>
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
