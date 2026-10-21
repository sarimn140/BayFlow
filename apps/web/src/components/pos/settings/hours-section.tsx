'use client'

import { Copy } from 'lucide-react'
import { useState, type Dispatch, type FormEvent, type SetStateAction } from 'react'
import { toast } from 'sonner'

import { FormSection } from '@/components/layout/form-section'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Switch } from '@/components/ui/switch'
import { saveShop, type MockShop } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { shownErrors } from './form-errors'
import { SectionFooter } from './section-footer'
import {
  copyMondayToOpenDays,
  defaultHours,
  hoursFromShop,
  hoursToShop,
  safeTimeZone,
  timeOptions,
  validateHours,
  type DayHours,
  type HoursErrors,
  type Weekday,
} from './settings-data'

/** Keeps a 36px button's look while giving it a 44px tall touch target. */
const TALL_TARGET = 'relative after:absolute after:inset-x-0 after:-inset-y-1'

const rowId = (day: Weekday, part: 'open' | 'opens' | 'closes' | 'error') =>
  `hours-${day.toLowerCase()}-${part}`

export interface HoursSectionProps {
  shop: MockShop
  value: ReadonlyArray<DayHours>
  onChange: Dispatch<SetStateAction<DayHours[]>>
  dirty: boolean
}

/**
 * O-04 §4 Working hours: Monday to Sunday, each with an Open switch and opening and closing times
 * on the shop's slot grid (D37), plus "Copy Monday". Always editable; existing bookings are kept.
 */
export function HoursSection({ shop, value, onChange, dirty }: HoursSectionProps) {
  const [flagged, setFlagged] = useState<ReadonlySet<Weekday>>(() => new Set())
  const slot = shop.slot_duration_minutes
  const errors: HoursErrors = shownErrors(validateHours(value, slot), flagged)
  const monday = value[0]

  const setRow = (index: number, patch: Partial<DayHours>) =>
    onChange((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))

  /** A day that opens without times takes Monday's (or the first open day's) hours. */
  const toggleDay = (index: number, open: boolean) =>
    onChange((rows) =>
      rows.map((row, i) => {
        if (i !== index) return row
        if (open && (!row.opens || !row.closes))
          return { ...row, open, ...defaultHours(rows, slot) }
        return { ...row, open }
      }),
    )

  const copyMonday = () => {
    if (!monday?.open) return
    if (validateHours([monday], slot)[monday.day]) {
      setFlagged((days) => new Set(days).add(monday.day))
      document.getElementById(rowId(monday.day, 'opens'))?.focus()
      return
    }
    const targets = value.filter((row, i) => i > 0 && row.open).length
    if (targets === 0) {
      toast.info('Open another day first, then copy Monday to it.')
      return
    }
    onChange((rows) => copyMondayToOpenDays(rows))
    toast.success(
      `Monday's hours copied to ${targets === 1 ? '1 day' : `${targets} days`}. Save to apply them.`,
    )
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const found = validateHours(value, slot)
    const invalid = value.filter((row) => found[row.day]).map((row) => row.day)
    setFlagged(new Set(invalid))
    if (invalid[0]) {
      document.getElementById(rowId(invalid[0], 'opens'))?.focus()
      return
    }
    saveShop({ ...shop, working_hours: hoursToShop(value) })
    toast.success('Opening hours saved')
  }

  const discard = () => {
    onChange(hoursFromShop(shop))
    setFlagged(new Set())
  }

  return (
    <form noValidate onSubmit={submit}>
      <FormSection
        title="Opening hours"
        description={`When customers can book. Times follow your ${slot}-minute slots. Changes apply to new bookings; bookings already made are kept.`}
        footer={<SectionFooter name="the opening hours" dirty={dirty} onDiscard={discard} />}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            Times are shop local time ({safeTimeZone(shop.timezone)}).
          </p>
          {monday?.open ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={TALL_TARGET}
              onClick={copyMonday}
            >
              <Copy data-icon="inline-start" aria-hidden="true" />
              Copy Monday to all open days
            </Button>
          ) : null}
        </div>

        <ul className="mt-4 divide-y divide-border-faint border-t border-border-faint">
          {value.map((row, index) => (
            <HoursRow
              key={row.day}
              row={row}
              slot={slot}
              error={errors[row.day]}
              onToggle={(open) => toggleDay(index, open)}
              onTime={(part, time) =>
                setRow(index, part === 'opens' ? { opens: time } : { closes: time })
              }
            />
          ))}
        </ul>
      </FormSection>
    </form>
  )
}

function HoursRow({
  row,
  slot,
  error,
  onToggle,
  onTime,
}: {
  row: DayHours
  slot: number
  error?: string
  onToggle: (open: boolean) => void
  onTime: (part: 'opens' | 'closes', time: string) => void
}) {
  const errorId = error ? rowId(row.day, 'error') : undefined
  return (
    <li className="py-3.5 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex min-w-40 flex-1 items-center gap-3">
          <Switch id={rowId(row.day, 'open')} checked={row.open} onCheckedChange={onToggle} />
          <Label
            htmlFor={rowId(row.day, 'open')}
            className={cn('font-semibold', !row.open && 'text-muted-foreground')}
          >
            <span className="sr-only">Open on </span>
            {row.day}
          </Label>
        </div>
        {row.open ? (
          <div
            role="group"
            aria-label={`${row.day} hours`}
            className="flex w-full items-center gap-2 sm:w-auto"
          >
            <TimeSelect
              id={rowId(row.day, 'opens')}
              label={`${row.day} opening time`}
              value={row.opens}
              options={timeOptions(slot, row.opens, 'opens')}
              invalid={Boolean(error)}
              describedBy={errorId}
              onChange={(time) => onTime('opens', time)}
            />
            <span className="text-sm text-muted-foreground" aria-hidden="true">
              to
            </span>
            <TimeSelect
              id={rowId(row.day, 'closes')}
              label={`${row.day} closing time`}
              value={row.closes}
              options={timeOptions(slot, row.closes, 'closes')}
              invalid={Boolean(error)}
              describedBy={errorId}
              onChange={(time) => onTime('closes', time)}
            />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Closed</p>
        )}
      </div>
      {error ? (
        <FieldError id={errorId} className="mt-2">
          {error}
        </FieldError>
      ) : null}
    </li>
  )
}

function TimeSelect({
  id,
  label,
  value,
  options,
  invalid,
  describedBy,
  onChange,
}: {
  id: string
  label: string
  value: string
  options: ReadonlyArray<{ value: string; label: string }>
  invalid: boolean
  describedBy?: string
  onChange: (time: string) => void
}) {
  return (
    <NativeSelect
      id={id}
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-invalid={invalid}
      aria-describedby={describedBy}
      className="min-w-0 flex-1 sm:w-36 sm:flex-none"
    >
      {value ? null : (
        <NativeSelectOption value="" disabled>
          Choose
        </NativeSelectOption>
      )}
      {options.map((option) => (
        <NativeSelectOption key={option.value} value={option.value}>
          {option.label}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  )
}
