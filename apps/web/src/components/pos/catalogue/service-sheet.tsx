'use client'

import { Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { fieldsWithErrors, shownErrors } from '@/components/pos/settings/form-errors'
import type { MockService } from '@/lib/mock-data'

import {
  NEW_SERVICE_DRAFT,
  SERVICE_DESCRIPTION_MAX,
  SERVICE_FIELDS,
  SERVICE_NAME_MAX,
  draftFromService,
  suggestionsFor,
  validateService,
  type ServiceDraft,
  type ServiceErrors,
  type ServiceField,
  type ServiceSuggestion,
} from './catalogue-data'

const FIELD_ID: Record<ServiceField, string> = {
  name: 'service-name',
  description: 'service-description',
  duration: 'service-duration',
  price: 'service-price',
}

/** Keeps the 36px chip's look while giving it a 44px tall touch target. */
const TALL_TARGET = 'relative after:absolute after:inset-x-0 after:-inset-y-1'

export interface ServiceSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The service being edited; `null` adds a new one. */
  service: MockService | null
  /** The shop's services: the duplicate-name rule (409 `CONFLICT`) and the suggestions. */
  services: ReadonlyArray<MockService>
  /** A new value each time the sheet opens, so the form starts from the right values. */
  formKey: number
  onSubmit: (draft: ServiceDraft) => void
}

/** O-03 "Add service" / "Edit": a right sheet with the `ServiceCreate` fields (spec 10). */
export function ServiceSheet({
  open,
  onOpenChange,
  service,
  services,
  formKey,
  onSubmit,
}: ServiceSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        onOpenAutoFocus={(event) => {
          // Start on the name, not on the first suggestion chip.
          event.preventDefault()
          document.getElementById(FIELD_ID.name)?.focus()
        }}
      >
        <ServiceForm key={formKey} service={service} services={services} onSubmit={onSubmit} />
      </SheetContent>
    </Sheet>
  )
}

function ServiceForm({
  service,
  services,
  onSubmit,
}: Pick<ServiceSheetProps, 'service' | 'services' | 'onSubmit'>) {
  const isNew = service === null
  const [draft, setDraft] = useState<ServiceDraft>(() =>
    service ? draftFromService(service) : NEW_SERVICE_DRAFT,
  )
  const [flagged, setFlagged] = useState<ReadonlySet<ServiceField>>(() => new Set())
  const [announcement, setAnnouncement] = useState('')
  const suggestions = isNew ? suggestionsFor(services) : []
  const errors: ServiceErrors = shownErrors(validateService(draft, services, service?.id), flagged)

  const update = <K extends keyof ServiceDraft>(key: K, value: ServiceDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }))

  const applySuggestion = (suggestion: ServiceSuggestion) => {
    setDraft((current) => ({
      ...current,
      name: suggestion.name,
      description: suggestion.description,
      duration: String(suggestion.minutes),
    }))
    setAnnouncement(`Filled in ${suggestion.name}. Add a base price or leave it blank.`)
  }

  const describe = (field: ServiceField, help?: string) =>
    [help, errors[field] ? `${FIELD_ID[field]}-error` : null].filter(Boolean).join(' ') || undefined

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const invalid = fieldsWithErrors(validateService(draft, services, service?.id), SERVICE_FIELDS)
    setFlagged(new Set(invalid))
    if (invalid[0]) {
      document.getElementById(FIELD_ID[invalid[0]])?.focus()
      return
    }
    onSubmit(draft)
  }

  return (
    <form noValidate onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <SheetHeader>
        <SheetTitle>{isNew ? 'Add a service' : 'Edit service'}</SheetTitle>
        <SheetDescription>
          {isNew
            ? 'Customers see the name, description, time and price when they book online.'
            : 'Changes apply to new bookings. Bookings already made keep the name and price they were booked with.'}
        </SheetDescription>
      </SheetHeader>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
        <FieldGroup>
          {suggestions.length > 0 ? (
            <div className="space-y-2.5">
              <p id="service-suggestions" className="text-sm font-medium text-foreground">
                Start from a common service
              </p>
              <div
                role="group"
                aria-labelledby="service-suggestions"
                className="flex flex-wrap gap-2"
              >
                {suggestions.map((suggestion) => (
                  <Button
                    key={suggestion.name}
                    type="button"
                    variant="outline"
                    size="sm"
                    className={TALL_TARGET}
                    onClick={() => applySuggestion(suggestion)}
                  >
                    <Plus data-icon="inline-start" aria-hidden="true" />
                    {suggestion.name}
                  </Button>
                ))}
              </div>
              <p className="sr-only" aria-live="polite">
                {announcement}
              </p>
            </div>
          ) : null}

          <Field data-invalid={Boolean(errors.name)}>
            <FieldLabel htmlFor={FIELD_ID.name}>Name</FieldLabel>
            <Input
              id={FIELD_ID.name}
              value={draft.name}
              onChange={(event) => update('name', event.target.value)}
              placeholder="e.g. Brake pad replacement"
              autoComplete="off"
              maxLength={SERVICE_NAME_MAX}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={describe('name')}
              required
            />
            {errors.name ? (
              <FieldError id={`${FIELD_ID.name}-error`}>{errors.name}</FieldError>
            ) : null}
          </Field>

          <Field data-invalid={Boolean(errors.description)}>
            <FieldLabel htmlFor={FIELD_ID.description}>
              Description <span className="font-normal text-helper">(optional)</span>
            </FieldLabel>
            <Textarea
              id={FIELD_ID.description}
              value={draft.description}
              onChange={(event) => update('description', event.target.value)}
              rows={3}
              maxLength={SERVICE_DESCRIPTION_MAX}
              aria-invalid={Boolean(errors.description)}
              aria-describedby={describe('description', 'service-description-help')}
            />
            <FieldDescription id="service-description-help" className="flex justify-between gap-3">
              <span>What&apos;s included, in a sentence or two.</span>
              <span className="shrink-0 tabular-nums">
                {draft.description.length.toLocaleString('en')} / 1,000
              </span>
            </FieldDescription>
            {errors.description ? (
              <FieldError id={`${FIELD_ID.description}-error`}>{errors.description}</FieldError>
            ) : null}
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field data-invalid={Boolean(errors.duration)}>
              <FieldLabel htmlFor={FIELD_ID.duration}>Estimated duration</FieldLabel>
              <InputGroup>
                <InputGroupInput
                  id={FIELD_ID.duration}
                  value={draft.duration}
                  onChange={(event) => update('duration', event.target.value)}
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={6}
                  aria-invalid={Boolean(errors.duration)}
                  aria-describedby={describe('duration', 'service-duration-help')}
                  required
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupText>min</InputGroupText>
                </InputGroupAddon>
              </InputGroup>
              <FieldDescription id="service-duration-help">5 to 10,080 minutes.</FieldDescription>
              {errors.duration ? (
                <FieldError id={`${FIELD_ID.duration}-error`}>{errors.duration}</FieldError>
              ) : null}
            </Field>

            <Field data-invalid={Boolean(errors.price)}>
              <FieldLabel htmlFor={FIELD_ID.price}>
                Base price <span className="font-normal text-helper">(optional)</span>
              </FieldLabel>
              <InputGroup>
                <InputGroupAddon>
                  <InputGroupText>Rs</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id={FIELD_ID.price}
                  value={draft.price}
                  onChange={(event) => update('price', event.target.value)}
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={16}
                  aria-invalid={Boolean(errors.price)}
                  aria-describedby={describe('price', 'service-price-help')}
                />
              </InputGroup>
              <FieldDescription id="service-price-help">
                Whole rupees. Leave blank to price after inspection.
              </FieldDescription>
              {errors.price ? (
                <FieldError id={`${FIELD_ID.price}-error`}>{errors.price}</FieldError>
              ) : null}
            </Field>
          </div>

          <Field orientation="horizontal" className="rounded-xl border border-border p-4">
            <FieldContent>
              <FieldLabel htmlFor="service-active">Active</FieldLabel>
              <FieldDescription>
                Active services are on your public page and can be booked online. Turning one off
                hides it from new bookings; bookings already made keep it.
              </FieldDescription>
            </FieldContent>
            <Switch
              id="service-active"
              checked={draft.isActive}
              onCheckedChange={(checked) => update('isActive', checked)}
            />
          </Field>
        </FieldGroup>
      </div>

      <SheetFooter className="flex-row justify-end">
        <SheetClose asChild>
          <Button type="button" variant="outline" className="flex-1 sm:flex-none">
            Cancel
          </Button>
        </SheetClose>
        <Button type="submit" className="flex-1 sm:flex-none">
          {isNew ? 'Add service' : 'Save changes'}
        </Button>
      </SheetFooter>
    </form>
  )
}
