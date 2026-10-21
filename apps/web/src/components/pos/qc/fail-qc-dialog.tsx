'use client'

import { Undo2 } from 'lucide-react'
import { useId, type FormEvent } from 'react'

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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

import { ISSUE_DESCRIPTION_MAX, ISSUE_TITLE_MAX, type IssueErrors } from './qc-data'

export interface FailQcDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  reference: string
  technicianName: string | undefined
  title: string
  description: string
  errors: IssueErrors
  onTitleChange: (value: string) => void
  onDescriptionChange: (value: string) => void
  /** Validates and fails QC; returns the field to fix, or null when QC was failed. */
  onConfirm: () => 'title' | 'description' | null
}

/**
 * `fail-qc` (spec 09 §4.6, spec 10 QI-02): an `AlertDialog` whose issue title and description are
 * both required and prefilled from the failed checks. Focus starts on Cancel; the destructive
 * confirm comes last.
 */
export function FailQcDialog({
  open,
  onOpenChange,
  reference,
  technicianName,
  title,
  description,
  errors,
  onTitleChange,
  onDescriptionChange,
  onConfirm,
}: FailQcDialogProps) {
  const id = useId()
  const titleId = `${id}-title`
  const descriptionId = `${id}-description`
  const technician = technicianName ?? 'the technician'

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const invalid = onConfirm()
    if (invalid) document.getElementById(invalid === 'title' ? titleId : descriptionId)?.focus()
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <form noValidate onSubmit={submit} className="grid min-w-0 gap-5">
          <AlertDialogHeader>
            <AlertDialogTitle>Fail QC for {reference}?</AlertDialogTitle>
            <AlertDialogDescription>
              The car goes back to {technician} in repair with this issue. It returns to the QC
              queue for a re-test once it is fixed.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <FieldGroup>
            <Field data-invalid={errors.title ? true : undefined}>
              <FieldLabel htmlFor={titleId}>Issue title</FieldLabel>
              <Input
                id={titleId}
                value={title}
                onChange={(event) => onTitleChange(event.target.value)}
                maxLength={ISSUE_TITLE_MAX}
                autoComplete="off"
                aria-invalid={errors.title ? true : undefined}
                aria-describedby={`${titleId}-hint${errors.title ? ` ${titleId}-error` : ''}`}
              />
              <FieldDescription id={`${titleId}-hint`}>
                {technicianName ? `${technicianName} sees` : 'The technician sees'} this first.{' '}
                <span className="tabular-nums">
                  {title.length}/{ISSUE_TITLE_MAX}
                </span>
              </FieldDescription>
              {errors.title ? (
                <FieldError id={`${titleId}-error`}>{errors.title}</FieldError>
              ) : null}
            </Field>

            <Field data-invalid={errors.description ? true : undefined}>
              <FieldLabel htmlFor={descriptionId}>What needs fixing</FieldLabel>
              <Textarea
                id={descriptionId}
                value={description}
                onChange={(event) => onDescriptionChange(event.target.value)}
                maxLength={ISSUE_DESCRIPTION_MAX}
                rows={5}
                placeholder="Where the problem is, what you saw and what to redo"
                aria-invalid={errors.description ? true : undefined}
                aria-describedby={`${descriptionId}-hint${errors.description ? ` ${descriptionId}-error` : ''}`}
              />
              <FieldDescription id={`${descriptionId}-hint`}>
                <span className="tabular-nums">
                  {description.length}/{ISSUE_DESCRIPTION_MAX.toLocaleString('en')}
                </span>
              </FieldDescription>
              {errors.description ? (
                <FieldError id={`${descriptionId}-error`}>{errors.description}</FieldError>
              ) : null}
            </Field>
          </FieldGroup>

          <AlertDialogFooter>
            <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
            <Button type="submit" variant="destructive">
              <Undo2 aria-hidden="true" />
              Fail QC and return to {technician}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}
