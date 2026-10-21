'use client'

import { CalendarX2, Clock, Eye, EyeOff, Pencil, ShieldCheck } from 'lucide-react'
import Link from 'next/link'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { useState, type ReactNode } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { serviceIcon } from '@/components/booking/service-icon'
import type { WizardValues } from '@/components/booking/wizard-schema'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import { Textarea } from '@/components/ui/textarea'
import { formatDateKey, type FreeSlot } from '@/lib/booking-slots'
import { formatPKR } from '@/lib/format'
import type { MockService, MockShop } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

// Fields use the primitives' own look (DESIGN.md §4): 42px, 12px corners and the ≥ 3 : 1
// `border-input` edge, with the blue focus halo.

function useFieldError(name: keyof WizardValues): string | undefined {
  const {
    formState: { errors },
  } = useFormContext<WizardValues>()
  return errors[name]?.message
}

function ErrorText({ message }: { message?: string }) {
  return message ? <FieldError>{message}</FieldError> : null
}

/* ---------------------------------------------------------------- W2 · Services ------------- */

export function StepServices({ services }: { services: ReadonlyArray<MockService> }) {
  const { control, register } = useFormContext<WizardValues>()
  const notes = useWatch<WizardValues, 'notes'>({ name: 'notes' })
  const error = useFieldError('serviceIds')
  const notesError = useFieldError('notes')

  return (
    <div className="space-y-8">
      <Controller
        control={control}
        name="serviceIds"
        render={({ field }) => (
          <FieldSet>
            <FieldLegend className="sr-only">Services</FieldLegend>
            <div className="grid gap-3 md:grid-cols-2">
              {services.map((service) => {
                const checked = field.value.includes(service.id)
                const Icon = serviceIcon(service.name)
                const id = `service-${service.id}`
                return (
                  <label
                    key={service.id}
                    htmlFor={id}
                    className={cn(
                      'group/service relative flex cursor-pointer gap-4 rounded-2xl border bg-card p-4 transition-[border-color,box-shadow,background-color] duration-150',
                      checked
                        ? 'border-brand-blue bg-brand-blue-subtle/60 shadow-md ring-1 shadow-brand-blue/10 ring-brand-blue'
                        : 'border-border hover:border-brand-blue/40 hover:shadow-sm',
                    )}
                  >
                    <span
                      className={cn(
                        'flex size-11 shrink-0 items-center justify-center rounded-xl transition-colors',
                        checked
                          ? 'bg-brand-blue text-white'
                          : 'bg-brand-blue-subtle text-brand-blue-ink',
                      )}
                    >
                      <Icon className="size-5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1 space-y-1">
                      <span className="block pr-6 font-semibold text-foreground">
                        {service.name}
                      </span>
                      <span className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                        {service.description}
                      </span>
                      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="size-3.5" aria-hidden />≈{' '}
                          {service.estimated_duration_minutes} min
                        </span>
                        <span className="font-semibold text-foreground">
                          {service.base_price
                            ? `from ${formatPKR(service.base_price)}`
                            : 'Price after inspection'}
                        </span>
                      </span>
                    </span>
                    <Checkbox
                      id={id}
                      checked={checked}
                      onCheckedChange={(next) =>
                        field.onChange(
                          next
                            ? [...field.value, service.id]
                            : field.value.filter((value) => value !== service.id),
                        )
                      }
                      onBlur={field.onBlur}
                      aria-invalid={Boolean(error)}
                      className="absolute top-4 right-4 size-5 rounded-[5px]"
                    />
                  </label>
                )
              })}
            </div>
            <ErrorText message={error} />
          </FieldSet>
        )}
      />

      <Field data-invalid={Boolean(notesError)}>
        <FieldLabel htmlFor="notes">Describe the problem (optional)</FieldLabel>
        <Textarea
          id="notes"
          rows={4}
          maxLength={2000}
          placeholder="Light came on yesterday, car vibrates at idle"
          aria-invalid={Boolean(notesError)}
          className="min-h-28"
          {...register('notes')}
        />
        <FieldDescription className="flex justify-between gap-3">
          <span>The service advisor and technician read this before they inspect your car.</span>
          <span className="shrink-0 tabular-nums">{notes.length.toLocaleString('en')} / 2,000</span>
        </FieldDescription>
        <ErrorText message={notesError} />
      </Field>
    </div>
  )
}

/* ---------------------------------------------------------------- W3 · Time ----------------- */

const toKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
const fromKey = (key: string) => {
  const [y, m, d] = key.split('-').map(Number) as [number, number, number]
  return new Date(y, m - 1, d)
}

const PERIODS: ReadonlyArray<[string, (start: number) => boolean]> = [
  ['Morning', (start) => start < 12 * 60],
  ['Afternoon', (start) => start >= 12 * 60 && start < 17 * 60],
  ['Evening', (start) => start >= 17 * 60],
]

export function StepTime({
  shop,
  openDates,
  slots,
  nextDateWithSlots,
}: {
  shop: MockShop
  openDates: ReadonlyArray<string>
  slots: ReadonlyArray<FreeSlot>
  /** The next open day after the selected one that still has a free slot. */
  nextDateWithSlots: string | null
}) {
  const { control, setValue, clearErrors } = useFormContext<WizardValues>()
  const date = useWatch<WizardValues, 'date'>({ name: 'date' })
  const time = useWatch<WizardValues, 'time'>({ name: 'time' })
  const dateError = useFieldError('date')
  const timeError = useFieldError('time')
  const open = new Set(openDates)
  const first = openDates[0]
  const last = openDates.at(-1)
  const taken = Boolean(time) && !slots.some((slot) => slot.time === time)

  const pickDate = (key: string) => {
    setValue('date', key, { shouldDirty: true })
    setValue('time', '', { shouldDirty: true })
    clearErrors(['date', 'time'])
  }

  // The calendar and the times sit side by side only where both fit comfortably: from `md` while
  // the summary is hidden, then again from `xl` once the summary column has room to spare.
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[auto_minmax(0,1fr)] lg:grid-cols-1 xl:grid-cols-[auto_minmax(0,1fr)]">
      <div className="min-w-0 sm:flex sm:flex-col sm:items-center md:block lg:flex xl:block">
        {/* Full width on phones (the day cells grow to share the row), its natural size from sm. */}
        <div className="w-full rounded-2xl border border-border bg-card p-1 shadow-xs sm:w-fit sm:p-2">
          <Calendar
            mode="single"
            weekStartsOn={1}
            selected={date ? fromKey(date) : undefined}
            onSelect={(day) => day && pickDate(toKey(day))}
            defaultMonth={date ? fromKey(date) : first ? fromKey(first) : undefined}
            startMonth={first ? fromKey(first) : undefined}
            endMonth={last ? fromKey(last) : undefined}
            disabled={(day) => !open.has(toKey(day))}
            classNames={{ root: 'rdp-root w-full sm:w-fit' }}
            className="p-2 [--cell-size:min(2.6rem,calc((100vw_-_7rem)/7))] sm:p-3 sm:[--cell-size:2.6rem] [&_button[data-selected-single=true]]:bg-brand-blue! [&_button[data-selected-single=true]]:text-white!"
          />
        </div>
        <ErrorText message={dateError} />
      </div>

      <div className="min-w-0 space-y-4">
        <div>
          <h3 className="text-xl font-bold text-foreground">
            {date ? `Free times on ${formatDateKey(date)}` : 'Pick a day'}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Times are shop local time ({shop.timezone}). Each visit books a{' '}
            {shop.slot_duration_minutes}-minute slot.
          </p>
        </div>

        {taken && (
          <p
            role="alert"
            className="rounded-xl border border-attention-border bg-attention px-4 py-3 text-sm text-foreground"
          >
            <span className="font-semibold text-cta">That time was just taken.</span> Please pick
            another.
          </p>
        )}

        {date && slots.length === 0 ? (
          <Empty className="rounded-2xl border border-dashed border-border py-10">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <CalendarX2 />
              </EmptyMedia>
              <EmptyTitle>No free times on {formatDateKey(date)}</EmptyTitle>
              <EmptyDescription>
                Every slot that day is booked or has already started.
              </EmptyDescription>
            </EmptyHeader>
            {nextDateWithSlots && (
              <EmptyContent>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-full"
                  onClick={() => pickDate(nextDateWithSlots)}
                >
                  Next open day: {formatDateKey(nextDateWithSlots)}
                </Button>
              </EmptyContent>
            )}
          </Empty>
        ) : (
          <Controller
            control={control}
            name="time"
            render={({ field }) => (
              <RadioGroupPrimitive.Root
                value={taken ? '' : field.value}
                onValueChange={field.onChange}
                aria-label={date ? `Free times on ${formatDateKey(date)}` : 'Free times'}
                aria-invalid={Boolean(timeError)}
                className="space-y-5"
              >
                {PERIODS.map(([period, inPeriod]) => {
                  const group = slots.filter((slot) => inPeriod(slot.start))
                  if (group.length === 0) return null
                  return (
                    <div key={period} className="space-y-2">
                      <p className="text-sm font-semibold text-foreground">{period}</p>
                      <div className="grid grid-cols-3 gap-2 sm:grid-cols-[repeat(auto-fill,minmax(6.25rem,1fr))]">
                        {group.map((slot) => (
                          <RadioGroupPrimitive.Item
                            key={slot.time}
                            value={slot.time}
                            className="flex h-12 min-w-0 flex-col items-center justify-center gap-0.5 rounded-xl border border-input bg-card px-2 text-sm font-semibold whitespace-nowrap text-foreground shadow-xs transition-colors outline-none hover:border-brand-blue hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid data-[state=checked]:border-brand-blue data-[state=checked]:bg-brand-blue data-[state=checked]:text-white data-[state=checked]:shadow-md data-[state=checked]:shadow-brand-blue/25"
                          >
                            {slot.time}
                            {slot.remaining === 1 && (
                              <span className="text-xs leading-none font-medium opacity-80">
                                1 left
                              </span>
                            )}
                          </RadioGroupPrimitive.Item>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </RadioGroupPrimitive.Root>
            )}
          />
        )}
        <ErrorText message={timeError} />
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- W4 · Details -------------- */

function TextField({
  name,
  label,
  description,
  className,
  ...input
}: {
  name: keyof WizardValues
  label: string
  description?: ReactNode
  className?: string
} & Omit<React.ComponentProps<'input'>, 'name' | 'className'>) {
  const { register } = useFormContext<WizardValues>()
  const error = useFieldError(name)
  return (
    <Field data-invalid={Boolean(error)} className={className}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} aria-invalid={Boolean(error)} {...input} {...register(name)} />
      {description && <FieldDescription>{description}</FieldDescription>}
      <ErrorText message={error} />
    </Field>
  )
}

export function StepDetails({
  signedInAs,
  onSignOut,
  loginHref,
}: {
  signedInAs: { name: string; email: string } | null
  onSignOut: () => void
  loginHref: string
}) {
  const { register } = useFormContext<WizardValues>()
  const [showPassword, setShowPassword] = useState(false)
  const passwordError = useFieldError('password')
  const mileageError = useFieldError('mileage')
  const registrationError = useFieldError('registration')
  const registration = register('registration')

  return (
    <div className="space-y-10">
      <FieldSet>
        <FieldLegend>Your details</FieldLegend>
        {signedInAs ? (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-muted/50 p-4">
            <Avatar className="size-10">
              <AvatarFallback className="bg-brand-blue text-sm font-semibold text-white">
                {signedInAs.name
                  .split(/\s+/)
                  .map((part) => part[0])
                  .join('')
                  .slice(0, 2)
                  .toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <p className="min-w-0 flex-1 text-sm">
              Booking as <span className="font-semibold text-foreground">{signedInAs.name}</span>
              <span className="block truncate text-muted-foreground">{signedInAs.email}</span>
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="rounded-full"
              onClick={onSignOut}
            >
              Not you? Log out
            </Button>
          </div>
        ) : (
          <FieldGroup className="grid gap-5 sm:grid-cols-2">
            <TextField name="fullName" label="Full name" autoComplete="name" />
            <TextField
              name="email"
              label="E-mail"
              type="email"
              autoComplete="email"
              inputMode="email"
              spellCheck={false}
            />
            <Field data-invalid={Boolean(passwordError)} className="sm:col-span-2">
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <InputGroup>
                <InputGroupInput
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  aria-invalid={Boolean(passwordError)}
                  {...register('password')}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton
                    size="icon-sm"
                    className="rounded-full"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((shown) => !shown)}
                  >
                    {showPassword ? <EyeOff /> : <Eye />}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
              <FieldDescription>
                At least 12 characters. Create a password to track your booking. Already have a
                BayFlow account? Enter your existing password, or{' '}
                <Link
                  href={loginHref}
                  className="font-semibold text-brand-blue-ink underline-offset-4 hover:underline"
                >
                  log in instead
                </Link>
                .
              </FieldDescription>
              <ErrorText message={passwordError} />
            </Field>
          </FieldGroup>
        )}
        <TextField
          name="phone"
          label="Phone (optional)"
          type="tel"
          autoComplete="tel"
          inputMode="tel"
          placeholder="+92 300 1234567"
          description="Helps the shop find your booking when you call."
          className="sm:max-w-[calc(50%-0.625rem)]"
        />
      </FieldSet>

      <FieldSet>
        <FieldLegend>Your vehicle</FieldLegend>
        <FieldGroup className="grid gap-5 sm:grid-cols-2">
          <Field data-invalid={Boolean(registrationError)}>
            <FieldLabel htmlFor="registration">Registration number</FieldLabel>
            <Input
              id="registration"
              autoComplete="off"
              spellCheck={false}
              placeholder="LEA-1234"
              aria-invalid={Boolean(registrationError)}
              className="font-mono uppercase"
              {...registration}
              onChange={(event) => {
                event.target.value = event.target.value.toUpperCase()
                void registration.onChange(event)
              }}
            />
            <ErrorText message={registrationError} />
          </Field>
          <TextField name="make" label="Make" placeholder="Toyota" autoComplete="off" />
          <TextField name="model" label="Model" placeholder="Corolla" autoComplete="off" />
          <TextField
            name="year"
            label="Year"
            inputMode="numeric"
            placeholder="2020"
            maxLength={4}
          />
          <TextField
            name="color"
            label="Colour (optional)"
            placeholder="White"
            autoComplete="off"
          />
          <Field data-invalid={Boolean(mileageError)}>
            <FieldLabel htmlFor="mileage">Mileage (optional)</FieldLabel>
            <InputGroup>
              <InputGroupInput
                id="mileage"
                inputMode="numeric"
                placeholder="45000"
                aria-invalid={Boolean(mileageError)}
                {...register('mileage')}
              />
              <InputGroupAddon align="inline-end">
                <InputGroupText>km</InputGroupText>
              </InputGroupAddon>
            </InputGroup>
            <ErrorText message={mileageError} />
          </Field>
        </FieldGroup>
      </FieldSet>
    </div>
  )
}

/* ---------------------------------------------------------------- W5 · Review --------------- */

function ReviewSection({
  title,
  onEdit,
  children,
}: {
  title: string
  onEdit: () => void
  children: ReactNode
}) {
  return (
    <section className="rounded-2xl border border-border p-4 sm:p-5">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-foreground">{title}</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="rounded-full text-brand-blue-ink"
          onClick={onEdit}
          aria-label={`Edit ${title.toLowerCase()}`}
        >
          <Pencil aria-hidden />
          Edit
        </Button>
      </div>
      <div className="space-y-1 text-sm text-muted-foreground">{children}</div>
    </section>
  )
}

export function StepReview({
  shop,
  services,
  signedInAs,
  onEdit,
}: {
  shop: MockShop
  services: ReadonlyArray<MockService>
  signedInAs: { name: string; email: string } | null
  onEdit: (step: 'services' | 'time' | 'details') => void
}) {
  const values = useWatch<WizardValues>()
  const vehicle = [values.year, values.make, values.model].filter(Boolean).join(' ')
  const name = signedInAs?.name ?? values.fullName
  const email = signedInAs?.email ?? values.email

  return (
    <div className="space-y-4">
      <ReviewSection title="Workshop and time" onEdit={() => onEdit('time')}>
        <p className="font-semibold text-foreground">{shop.name}</p>
        <p>
          {shop.address}, {shop.city}
        </p>
        {values.date && values.time && (
          <p className="pt-1 font-semibold text-brand-blue-ink">
            {formatDateKey(values.date, true)} · {values.time}{' '}
            <span className="font-normal text-muted-foreground">({shop.timezone})</span>
          </p>
        )}
      </ReviewSection>

      <ReviewSection title="Services and notes" onEdit={() => onEdit('services')}>
        <ul className="space-y-1">
          {services.map((s) => (
            <li key={s.id} className="flex justify-between gap-3 text-foreground">
              <span>{s.name}</span>
              <span className="shrink-0 tabular-nums">
                {s.base_price ? formatPKR(s.base_price) : 'Price after inspection'}
              </span>
            </li>
          ))}
        </ul>
        {values.notes?.trim() && (
          <blockquote className="mt-2 rounded-xl bg-muted px-3.5 py-2.5 whitespace-pre-line italic">
            {values.notes.trim()}
          </blockquote>
        )}
      </ReviewSection>

      <ReviewSection title="Your details" onEdit={() => onEdit('details')}>
        <p className="font-semibold text-foreground">{name}</p>
        <p>{email}</p>
        {values.phone?.trim() && <p>{values.phone.trim()}</p>}
        {!signedInAs && (
          <p className="pt-1">Your BayFlow account uses this e-mail and the password you set.</p>
        )}
      </ReviewSection>

      <ReviewSection title="Vehicle" onEdit={() => onEdit('details')}>
        <p className="font-mono font-semibold text-foreground">
          {values.registration?.trim().toUpperCase()}
        </p>
        <p>
          {vehicle}
          {values.color?.trim() && ` · ${values.color.trim()}`}
          {values.mileage?.trim() && ` · ${Number(values.mileage).toLocaleString('en')} km`}
        </p>
      </ReviewSection>

      <p className="flex gap-3 rounded-2xl border border-brand-green/25 bg-brand-green/5 p-4 text-sm leading-relaxed text-foreground">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand-green" aria-hidden />
        The final price comes from the technician&apos;s inspection estimate. You&apos;ll approve it
        online before any work starts.
      </p>
    </div>
  )
}
