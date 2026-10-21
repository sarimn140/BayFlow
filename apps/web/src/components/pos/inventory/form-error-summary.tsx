'use client'

import { CircleAlert } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export interface FormErrorItem {
  /** The field's input id. */
  id: string
  label: string
  message: string
}

/**
 * Spec 09 §5.4: when more than one field fails, a summary above the fields lists them, each a
 * link that moves focus to its field. One failing field needs no summary (its error is enough).
 */
export function FormErrorSummary({
  errors,
  onFocusField,
}: {
  errors: ReadonlyArray<FormErrorItem>
  onFocusField: (id: string) => void
}) {
  if (errors.length < 2) return null
  return (
    <Alert variant="destructive">
      <CircleAlert aria-hidden="true" />
      <AlertTitle>Check {errors.length} fields</AlertTitle>
      <AlertDescription>
        <ul className="mt-1 list-disc space-y-1 pl-4">
          {errors.map((error) => (
            <li key={error.id}>
              <a
                href={`#${error.id}`}
                className="rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                onClick={(event) => {
                  event.preventDefault()
                  onFocusField(error.id)
                }}
              >
                {error.label}
              </a>
              : {error.message}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  )
}
