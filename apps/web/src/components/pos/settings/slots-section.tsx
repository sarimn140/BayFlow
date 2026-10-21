'use client'

import { CircleAlert, Globe, Lock } from 'lucide-react'
import { useState, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import { toast } from 'sonner'

import { FormSection } from '@/components/layout/form-section'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { saveShop, type MockShop } from '@/lib/mock-data'

import { fieldsWithErrors, shownErrors } from './form-errors'
import { SectionFooter } from './section-footer'
import {
  CAPACITY_MAX,
  SLOTS_FIELDS,
  SLOT_LENGTHS,
  slotLengthLabel,
  slotsFromShop,
  timeZoneLabel,
  validateSlots,
  type SlotsDraft,
  type SlotsErrors,
  type SlotsField,
} from './settings-data'

const FIELD_ID: Record<SlotsField, string> = {
  duration: 'slot-length',
  capacity: 'slot-capacity',
}

export interface SlotsSectionProps {
  shop: MockShop
  value: SlotsDraft
  onChange: Dispatch<SetStateAction<SlotsDraft>>
  dirty: boolean
  /** Non-cancelled bookings still to come (`has_future_bookings`, D37). */
  upcoming: number
}

/**
 * O-04 §3 Scheduling: slot length, cars per slot and the read-only time zone (D37, D38). The slot
 * length is locked while bookings are still to come; capacity always saves.
 */
export function SlotsSection({ shop, value, onChange, dirty, upcoming }: SlotsSectionProps) {
  const [flagged, setFlagged] = useState<ReadonlySet<SlotsField>>(() => new Set())
  const [conflict, setConflict] = useState(false)
  const errors: SlotsErrors = shownErrors(validateSlots(value, shop), flagged)
  const locked = upcoming > 0
  const current = Number(value.duration)
  // A saved length off the 15-minute steps (older data) stays selectable until it is changed.
  const lengths = SLOT_LENGTHS.includes(current)
    ? SLOT_LENGTHS
    : [...SLOT_LENGTHS, current].sort((a, b) => a - b)

  const change = (field: SlotsField, text: string) =>
    onChange((existing) => ({ ...existing, [field]: text }))

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (current !== shop.slot_duration_minutes && locked) {
      // D37 409 CONFLICT: keep the capacity edit, put the length back to what is saved.
      setConflict(true)
      onChange((existing) => ({ ...existing, duration: String(shop.slot_duration_minutes) }))
      return
    }
    const invalid = fieldsWithErrors(validateSlots(value, shop), SLOTS_FIELDS)
    setFlagged(new Set(invalid))
    if (invalid[0]) {
      document.getElementById(FIELD_ID[invalid[0]])?.focus()
      return
    }
    const capacity = Number(value.capacity.trim())
    saveShop({ ...shop, slot_duration_minutes: current, slot_capacity: capacity })
    onChange({ duration: String(current), capacity: String(capacity) })
    setConflict(false)
    toast.success('Slots and capacity saved')
  }

  const discard = () => {
    onChange(slotsFromShop(shop))
    setFlagged(new Set())
    setConflict(false)
  }

  const lengthHelp = locked
    ? `Locked while ${upcoming === 1 ? '1 booking is' : `${upcoming.toLocaleString('en')} bookings are`} still to come. Capacity and opening hours can still change.`
    : 'Can only change while the shop has no upcoming bookings.'

  return (
    <form noValidate onSubmit={submit}>
      <FormSection
        title="Slots and capacity"
        description="Customers book fixed-length slots. Capacity is how many cars you take in the same slot."
        footer={<SectionFooter name="slots and capacity" dirty={dirty} onDiscard={discard} />}
      >
        <FieldGroup>
          {conflict ? (
            <Alert variant="destructive">
              <CircleAlert aria-hidden="true" />
              <AlertTitle>Slot length not changed</AlertTitle>
              <AlertDescription>
                Slot duration can&apos;t change while the shop has upcoming bookings. Capacity and
                working hours can still be changed.
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-5 @md/field-group:grid-cols-2">
            <Field data-invalid={Boolean(errors.duration)}>
              <FieldLabel htmlFor={FIELD_ID.duration}>
                Slot length
                {locked ? <Lock className="size-3.5 text-helper" aria-hidden="true" /> : null}
              </FieldLabel>
              <NativeSelect
                id={FIELD_ID.duration}
                value={value.duration}
                onChange={(event) => change('duration', event.target.value)}
                disabled={locked}
                aria-invalid={Boolean(errors.duration)}
                aria-describedby={[
                  `${FIELD_ID.duration}-help`,
                  errors.duration ? `${FIELD_ID.duration}-error` : null,
                ]
                  .filter(Boolean)
                  .join(' ')}
                className="w-full"
              >
                {lengths.map((minutes) => (
                  <NativeSelectOption key={minutes} value={String(minutes)}>
                    {slotLengthLabel(minutes)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <FieldDescription id={`${FIELD_ID.duration}-help`}>{lengthHelp}</FieldDescription>
              {errors.duration ? (
                <FieldError id={`${FIELD_ID.duration}-error`}>{errors.duration}</FieldError>
              ) : null}
            </Field>

            <Field data-invalid={Boolean(errors.capacity)}>
              <FieldLabel htmlFor={FIELD_ID.capacity}>Cars per slot</FieldLabel>
              <Input
                id={FIELD_ID.capacity}
                value={value.capacity}
                onChange={(event) => change('capacity', event.target.value)}
                inputMode="numeric"
                autoComplete="off"
                maxLength={String(CAPACITY_MAX).length + 1}
                aria-invalid={Boolean(errors.capacity)}
                aria-describedby={[
                  `${FIELD_ID.capacity}-help`,
                  errors.capacity ? `${FIELD_ID.capacity}-error` : null,
                ]
                  .filter(Boolean)
                  .join(' ')}
                required
              />
              <FieldDescription id={`${FIELD_ID.capacity}-help`}>
                1 to 50. Applies to every slot from now on; existing bookings are kept.
              </FieldDescription>
              {errors.capacity ? (
                <FieldError id={`${FIELD_ID.capacity}-error`}>{errors.capacity}</FieldError>
              ) : null}
            </Field>
          </div>

          <dl className="space-y-2">
            <dt className="text-sm leading-5 font-medium text-foreground">Time zone</dt>
            <dd className="flex min-h-10.5 items-center gap-2.5 rounded-lg border border-border bg-muted px-3.5 py-2 text-sm text-foreground">
              <Globe className="size-4 shrink-0 text-helper" aria-hidden="true" />
              {timeZoneLabel(shop.timezone)}
            </dd>
            <dd className="text-sm text-muted-foreground">
              Slots, opening hours and booking times all use shop time.
            </dd>
          </dl>
        </FieldGroup>
      </FormSection>
    </form>
  )
}
