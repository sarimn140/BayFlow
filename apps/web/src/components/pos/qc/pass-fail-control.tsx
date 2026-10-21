'use client'

import { Check, X } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'

import { cn } from '@/lib/utils'

import type { QcAnswer } from './qc-data'

const SEGMENT =
  'inline-flex h-12 min-w-0 items-center justify-center gap-2 rounded-full px-4 text-base font-semibold text-muted-foreground transition-colors duration-150 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid disabled:pointer-events-none disabled:opacity-50 data-[state=checked]:shadow-sm data-[state=unchecked]:hover:bg-card data-[state=unchecked]:hover:text-foreground [&_svg]:size-5 [&_svg]:shrink-0'

export interface PassFailControlProps {
  /** Prefix for the two radios' ids (`{id}-pass`, `{id}-fail`), so a row can focus its control. */
  id: string
  value: QcAnswer | undefined
  onValueChange: (value: QcAnswer) => void
  /** The check's title. */
  labelledBy: string
  /** The check's hint and, when shown, its error. */
  describedBy?: string
  invalid?: boolean
  disabled?: boolean
  /** Width: full width by default; the row narrows it once it sits beside the check's text. */
  className?: string
}

/**
 * A checklist row's segmented Pass / Fail choice (spec 10 QI-02): a required radio group with two
 * 48px segments for gloved hands. Pass fills green, Fail fills red; the label and icon carry the
 * state too, never the colour alone.
 */
export function PassFailControl({
  id,
  value,
  onValueChange,
  labelledBy,
  describedBy,
  invalid = false,
  disabled = false,
  className,
}: PassFailControlProps) {
  return (
    <RadioGroupPrimitive.Root
      value={value ?? ''}
      onValueChange={(next) => {
        if (next === 'pass' || next === 'fail') onValueChange(next)
      }}
      orientation="horizontal"
      required
      disabled={disabled}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      aria-invalid={invalid || undefined}
      className={cn(
        'grid w-full shrink-0 grid-cols-2 gap-1 rounded-full border bg-secondary p-1 transition-colors duration-150',
        invalid ? 'border-destructive' : 'border-border-medium',
        className,
      )}
    >
      <RadioGroupPrimitive.Item
        id={`${id}-pass`}
        value="pass"
        className={cn(
          SEGMENT,
          'data-[state=checked]:bg-brand-green data-[state=checked]:text-brand-green-foreground',
        )}
      >
        <Check aria-hidden="true" />
        Pass
      </RadioGroupPrimitive.Item>
      <RadioGroupPrimitive.Item
        id={`${id}-fail`}
        value="fail"
        className={cn(
          SEGMENT,
          'data-[state=checked]:bg-destructive-strong data-[state=checked]:text-destructive-foreground',
        )}
      >
        <X aria-hidden="true" />
        Fail
      </RadioGroupPrimitive.Item>
    </RadioGroupPrimitive.Root>
  )
}
