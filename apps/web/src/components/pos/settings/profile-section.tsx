'use client'

import {
  useState,
  type ComponentProps,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from 'react'
import { toast } from 'sonner'

import { FormSection } from '@/components/layout/form-section'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { saveShop, type MockShop } from '@/lib/mock-data'

import { fieldsWithErrors, shownErrors } from './form-errors'
import { SectionFooter } from './section-footer'
import {
  ADDRESS_MAX,
  CITY_MAX,
  PROFILE_FIELDS,
  SHOP_NAME_MAX,
  normaliseProfile,
  profileFromShop,
  validateProfile,
  type ProfileDraft,
  type ProfileErrors,
  type ProfileField,
} from './settings-data'

const FIELD_ID: Record<ProfileField, string> = {
  name: 'shop-name',
  address: 'shop-address',
  city: 'shop-city',
  phone: 'shop-phone',
}

export interface ProfileSectionProps {
  shop: MockShop
  value: ProfileDraft
  onChange: Dispatch<SetStateAction<ProfileDraft>>
  dirty: boolean
}

/** O-04 §1 Shop profile: name, address, city and phone (`ShopUpdate`). */
export function ProfileSection({ shop, value, onChange, dirty }: ProfileSectionProps) {
  const [flagged, setFlagged] = useState<ReadonlySet<ProfileField>>(() => new Set())
  const errors: ProfileErrors = shownErrors(validateProfile(value), flagged)

  const change = (field: ProfileField, text: string) =>
    onChange((current) => ({ ...current, [field]: text }))

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const invalid = fieldsWithErrors(validateProfile(value), PROFILE_FIELDS)
    setFlagged(new Set(invalid))
    if (invalid[0]) {
      document.getElementById(FIELD_ID[invalid[0]])?.focus()
      return
    }
    const clean = normaliseProfile(value)
    saveShop({ ...shop, ...clean })
    onChange(clean)
    toast.success('Shop profile saved')
  }

  const discard = () => {
    onChange(profileFromShop(shop))
    setFlagged(new Set())
  }

  return (
    <form noValidate onSubmit={submit}>
      <FormSection
        title="Shop profile"
        description="Shown on your public page and to customers on their bookings."
        footer={<SectionFooter name="the shop profile" dirty={dirty} onDiscard={discard} />}
      >
        <FieldGroup>
          <TextField
            field="name"
            label="Shop name"
            value={value.name}
            error={errors.name}
            onValueChange={change}
            maxLength={SHOP_NAME_MAX}
            autoComplete="organization"
          />
          <TextField
            field="address"
            label="Street address"
            value={value.address}
            error={errors.address}
            onValueChange={change}
            maxLength={ADDRESS_MAX}
            autoComplete="street-address"
          />
          <div className="grid gap-5 @md/field-group:grid-cols-2">
            <TextField
              field="city"
              label="City"
              value={value.city}
              error={errors.city}
              onValueChange={change}
              maxLength={CITY_MAX}
              autoComplete="address-level2"
            />
            <TextField
              field="phone"
              label="Phone"
              description="03XX-XXXXXXX or +92…"
              value={value.phone}
              error={errors.phone}
              onValueChange={change}
              type="tel"
              inputMode="tel"
              maxLength={21}
              autoComplete="tel"
            />
          </div>
        </FieldGroup>
      </FormSection>
    </form>
  )
}

function TextField({
  field,
  label,
  description,
  value,
  error,
  onValueChange,
  ...inputProps
}: {
  field: ProfileField
  label: string
  description?: string
  value: string
  error?: string
  onValueChange: (field: ProfileField, value: string) => void
} & Omit<ComponentProps<typeof Input>, 'id' | 'value' | 'onChange'>) {
  const id = FIELD_ID[field]
  const describedBy =
    [description ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean).join(' ') ||
    undefined
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        value={value}
        onChange={(event) => onValueChange(field, event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy}
        required
        {...inputProps}
      />
      {description ? <FieldDescription id={`${id}-help`}>{description}</FieldDescription> : null}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </Field>
  )
}
