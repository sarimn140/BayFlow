'use client'

import { CalendarClock, Info } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'

import { OnboardingSteps } from '@/components/auth/onboarding-steps'
import { FormSection } from '@/components/layout/form-section'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
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
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { slotLabel } from '@/lib/booking-slots'
import {
  getCurrentUser,
  getShops,
  getTeamMembers,
  saveShop,
  saveTeamMember,
  setCurrentUser,
  type MockShop,
} from '@/lib/mock-data'

import {
  DEFAULT_CLOSE_MINUTES,
  DEFAULT_OPEN_MINUTES,
  DEFAULT_WORKING_HOURS,
  SHOP_FIELDS,
  SHOP_LIMITS,
  SLOT_CAPACITY_MAX,
  SLOT_CAPACITY_MIN,
  SLOT_DURATIONS,
  durationLabel,
  newShopSlug,
  parseCapacity,
  plural,
  slotsPerDay,
  validateShop,
  weeklyHours,
  workspacesOf,
  type ShopErrors,
  type ShopField,
} from './hub-data'

/** The control each field's error points at (the first invalid one gets the focus). */
const FIELD_ID: Record<ShopField, string> = {
  name: 'shopName',
  address: 'address',
  city: 'city',
  phone: 'phone',
  slotDuration: 'slotDuration',
  slotCapacity: 'slotCapacity',
}

/** Every new shop's hours, in a few lines ("Monday to Saturday", "Sunday"). */
const DEFAULT_WEEK = weeklyHours(DEFAULT_WORKING_HOURS)

function FormField({
  id,
  label,
  description,
  error,
  children,
}: {
  id: string
  label: string
  description?: ReactNode
  error?: string
  children: ReactNode
}) {
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      {children}
      {description ? (
        <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
      ) : null}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </Field>
  )
}

/**
 * S-03 Create shop / O-05 Create an additional shop (spec 10): the shop's details, its opening
 * hours, booking slots and directory listing, then "Create shop". Anyone signed in may create one
 * and becomes its Owner (D17). Someone without a shop yet gets the first-run variant (UX rule R12);
 * the new shop's overview opens with the setup checklist (`?welcome=1`).
 */
export function CreateShopForm() {
  const router = useRouter()
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const shops = useMockStore(getShops)
  const team = useMockStore(getTeamMembers)

  const [name, setName] = useState('')
  const [city, setCity] = useState('Lahore')
  const [address, setAddress] = useState('')
  const [phone, setPhone] = useState('')
  const [slotDuration, setSlotDuration] = useState('60')
  const [slotCapacity, setSlotCapacity] = useState('2')
  const [isListed, setIsListed] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errors, setErrors] = useState<ShopErrors>({})
  /** The variant the page opened as, kept while the new shop is saved and its overview opens. */
  const [openedAs, setOpenedAs] = useState<{ firstRun: boolean; isCustomer: boolean } | null>(null)

  // The variant and the greeting come from this browser's session: wait for it (no flash).
  if (!ready) return <CreateShopSkeleton />

  const { firstRun, isCustomer } = openedAs ?? {
    firstRun: workspacesOf(user.email, team, shops).length === 0,
    isCustomer: user.role === 'CUSTOMER',
  }
  const firstName = user.name.trim().split(/\s+/)[0] || 'there'
  const draft = { name, address, city, phone, slotDuration, slotCapacity }

  const describe = (field: ShopField, hasDescription = false) => {
    const id = FIELD_ID[field]
    return (
      [hasDescription ? `${id}-description` : null, errors[field] ? `${id}-error` : null]
        .filter(Boolean)
        .join(' ') || undefined
    )
  }

  /** Errors appear on submit; once a field shows one, it is re-checked as the user fixes it. */
  const change =
    (field: ShopField, setValue: (value: string) => void) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = event.target.value
      setValue(value)
      if (!errors[field]) return
      const next = validateShop({ ...draft, [field]: value })
      setErrors((current) => ({ ...current, [field]: next[field] }))
    }

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (isSubmitting) return
    const found = validateShop(draft)
    setErrors(found)
    const first = SHOP_FIELDS.find((field) => found[field])
    if (first) {
      e.currentTarget.querySelector<HTMLElement>(`#${FIELD_ID[first]}`)?.focus()
      return
    }

    setIsSubmitting(true)
    // Saving makes the creator an Owner; the page keeps its greeting until the overview opens.
    setOpenedAs({ firstRun, isCustomer })

    // A taken slug gets a suffix, so a new shop never replaces an existing one.
    const slug = newShopSlug(name, getShops())
    const id = `shop-${slug}`

    const newShop: MockShop = {
      id,
      slug,
      name: name.trim(),
      city: city.trim(),
      address: address.trim() || 'Main Workshop Boulevard',
      phone: phone.trim() || '+92 42 35001122',
      rating: null,
      slot_duration_minutes: Number(slotDuration) || 60,
      slot_capacity: Number(slotCapacity) || 2,
      timezone: 'Asia/Karachi',
      is_listed: isListed,
      working_hours: DEFAULT_WORKING_HOURS.map((row) => ({ ...row })),
    }

    saveShop(newShop)
    // D17: the creator becomes the shop's Owner, a membership like any other (the switcher, the
    // all-shops summary and the hub list read memberships).
    saveTeamMember({
      id: `mbr-${id}-owner`,
      shopId: id,
      name: user.name,
      email: user.email,
      role: 'OWNER',
      is_active: true,
    })

    // Update active user shop
    setCurrentUser({
      ...user,
      shopId: id,
      shopName: newShop.name,
      role: 'OWNER',
    })

    // The button stays "Creating shop…" until the overview replaces this page, so a second
    // click while it loads cannot create the shop twice.
    setTimeout(() => {
      router.push(`/pos/shops/${id}/overview?welcome=1`)
    }, 400)
  }

  return (
    <>
      <PageHeader
        back={{ href: '/pos', label: 'Workshop hub' }}
        eyebrow={firstRun ? `Welcome, ${firstName}` : 'New shop'}
        title={firstRun ? 'Let’s set up your first shop' : 'Create a new shop'}
        description={
          firstRun
            ? 'Start with your shop’s details and booking slots. Next, you’ll add your team, then your services and parts.'
            : 'Each shop has its own team, services, booking slots and inventory.'
        }
      />

      {firstRun ? (
        <div className="max-w-xl">
          <OnboardingSteps current={1} />
        </div>
      ) : null}

      {isCustomer ? (
        <Alert variant="info" role="note">
          <Info aria-hidden="true" />
          <AlertDescription>
            Looking for your bookings? <Link href="/bookings">Go to My bookings</Link>
          </AlertDescription>
        </Alert>
      ) : null}

      <form noValidate onSubmit={handleSubmit} aria-label="New shop" className="space-y-8">
        <FormSection
          title="Shop details"
          description="Customers see these on your shop’s page and when they book."
        >
          <FieldGroup>
            <FormField id="shopName" label="Shop name" error={errors.name}>
              <Input
                id="shopName"
                name="organization"
                autoComplete="organization"
                placeholder="Apex Precision Motors"
                value={name}
                onChange={change('name', setName)}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={describe('name')}
                maxLength={SHOP_LIMITS.name}
                required
              />
            </FormField>
            <FormField id="address" label="Street address" error={errors.address}>
              <Input
                id="address"
                name="street-address"
                autoComplete="street-address"
                placeholder="Plot 14, Main Boulevard, Phase 5"
                value={address}
                onChange={change('address', setAddress)}
                aria-invalid={Boolean(errors.address)}
                aria-describedby={describe('address')}
                maxLength={SHOP_LIMITS.address}
                required
              />
            </FormField>
            <div className="grid gap-5 @md/field-group:grid-cols-2">
              <FormField id="city" label="City" error={errors.city}>
                <Input
                  id="city"
                  name="address-level2"
                  autoComplete="address-level2"
                  placeholder="Lahore"
                  value={city}
                  onChange={change('city', setCity)}
                  aria-invalid={Boolean(errors.city)}
                  aria-describedby={describe('city')}
                  maxLength={SHOP_LIMITS.city}
                  required
                />
              </FormField>
              <FormField
                id="phone"
                label="Phone"
                description="The number customers call, like 042 3578 9011."
                error={errors.phone}
              >
                <Input
                  id="phone"
                  name="tel"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="+92 42 35789011"
                  value={phone}
                  onChange={change('phone', setPhone)}
                  aria-invalid={Boolean(errors.phone)}
                  aria-describedby={describe('phone', true)}
                  maxLength={SHOP_LIMITS.phoneMax}
                  required
                />
              </FormField>
            </div>
          </FieldGroup>
        </FormSection>

        <FormSection
          title="Opening hours"
          description="Every new shop starts with these hours. Change them for each day in Shop settings."
        >
          <dl className="divide-y divide-border-faint text-sm">
            {DEFAULT_WEEK.map((line) => (
              <div
                key={line.days}
                className="flex items-center justify-between gap-4 py-3 first:pt-0"
              >
                <dt className="text-muted-foreground">{line.days}</dt>
                <dd className="text-right font-medium text-foreground tabular-nums">
                  {line.hours ?? <Badge variant="neutral">Closed</Badge>}
                </dd>
              </div>
            ))}
            <div className="flex items-center justify-between gap-4 py-3 last:pb-0">
              <dt className="text-muted-foreground">Time zone</dt>
              <dd className="text-right font-medium text-foreground">Asia/Karachi (PKT)</dd>
            </div>
          </dl>
        </FormSection>

        <FormSection
          title="Booking slots"
          description="Customers book a slot on your calendar. Choose how long a slot is and how many cars you take in at once."
        >
          <FieldGroup>
            <div className="grid gap-5 @md/field-group:grid-cols-2">
              <FormField
                id="slotDuration"
                label="Slot length"
                description="One hour suits most intakes and diagnostics."
                error={errors.slotDuration}
              >
                <NativeSelect
                  id="slotDuration"
                  className="w-full"
                  value={slotDuration}
                  onChange={change('slotDuration', setSlotDuration)}
                  aria-invalid={Boolean(errors.slotDuration)}
                  aria-describedby={describe('slotDuration', true)}
                >
                  {SLOT_DURATIONS.map((minutes) => (
                    <NativeSelectOption key={minutes} value={String(minutes)}>
                      {durationLabel(minutes)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </FormField>
              <FormField
                id="slotCapacity"
                label="Cars per slot"
                description={`How many cars you take in at once, from ${SLOT_CAPACITY_MIN} to ${SLOT_CAPACITY_MAX}.`}
                error={errors.slotCapacity}
              >
                <Input
                  id="slotCapacity"
                  type="number"
                  inputMode="numeric"
                  min={SLOT_CAPACITY_MIN}
                  max={SLOT_CAPACITY_MAX}
                  step={1}
                  value={slotCapacity}
                  onChange={change('slotCapacity', setSlotCapacity)}
                  aria-invalid={Boolean(errors.slotCapacity)}
                  aria-describedby={describe('slotCapacity', true)}
                  required
                />
              </FormField>
            </div>
            <SlotPreview duration={Number(slotDuration)} capacity={parseCapacity(slotCapacity)} />
          </FieldGroup>
        </FormSection>

        <FormSection
          title="Directory listing"
          description="The BayFlow directory is where customers find shops and book them online."
        >
          <Field orientation="horizontal">
            <FieldContent>
              <FieldLabel htmlFor="isListed">Show on the BayFlow shop directory</FieldLabel>
              <FieldDescription id="isListed-description">
                Your shop appears once it has at least one active service. You can hide it again in
                Shop settings.
              </FieldDescription>
            </FieldContent>
            <Switch
              id="isListed"
              checked={isListed}
              onCheckedChange={setIsListed}
              aria-describedby="isListed-description"
            />
          </Field>
        </FormSection>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
          <Button asChild variant="outline" size="lg" className="w-full sm:w-auto">
            <Link href="/pos">Cancel</Link>
          </Button>
          <Button type="submit" size="lg" disabled={isSubmitting} className="w-full sm:w-auto">
            {isSubmitting ? (
              <>
                <Spinner aria-hidden="true" />
                Creating shop…
              </>
            ) : (
              'Create shop'
            )}
          </Button>
        </div>
      </form>
    </>
  )
}

/** S-03 "Slots" preview: what the chosen length and capacity give on an open day. */
function SlotPreview({ duration, capacity }: { duration: number; capacity: number | null }) {
  const slots = slotsPerDay(duration)
  const openHours = `${slotLabel(DEFAULT_OPEN_MINUTES)} and ${slotLabel(DEFAULT_CLOSE_MINUTES)}`
  return (
    <div aria-live="polite" className="flex items-start gap-3 rounded-xl bg-layer p-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-card text-brand-blue-ink">
        <CalendarClock className="size-[18px]" aria-hidden="true" />
      </span>
      <div className="min-w-0 space-y-0.5 text-sm">
        <p className="font-semibold text-foreground">
          {capacity === null
            ? `${plural(slots, 'slot')} on each open day`
            : `Up to ${plural(slots * capacity, 'booking')} on each open day`}
        </p>
        <p className="text-muted-foreground">
          {plural(slots, 'slot')} of {durationLabel(duration)} between {openHours}
          {capacity === null ? '.' : `, ${plural(capacity, 'car')} in each.`}
        </p>
      </div>
    </div>
  )
}

/** Loading state shaped like the page (DESIGN.md §6.9): the header, then the form sections. */
function CreateShopSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-5 w-32 rounded-full" />
        <Skeleton className="h-4 w-28 rounded-full" />
        <Skeleton className="h-10 w-72 max-w-full" />
        <Skeleton className="h-5 w-full max-w-lg" />
      </div>
      {['h-72', 'h-44', 'h-60', 'h-28'].map((height) => (
        <div
          key={height}
          className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-8"
        >
          <div className="space-y-2 lg:pt-2">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-full max-w-64" />
          </div>
          <Skeleton className={`${height} rounded-2xl`} />
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}
