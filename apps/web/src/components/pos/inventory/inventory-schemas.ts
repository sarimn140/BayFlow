import { z } from 'zod'

import type { MockPart } from '@/lib/mock-data'

import { adjustmentError } from './inventory-model'

/**
 * The part form (E-44 / E-45 `PartCreate` / `PartUpdate`) and the stock adjustment form (E-46
 * `StockAdjustmentCreate`). Limits are spec 03's, as listed in spec 09 §2.10. Every value stays a
 * string while it is edited; the screen converts the numbers when it saves.
 */

/** `ck_parts_sku_format` (spec 02): upper case, starts with a letter or digit. */
export const SKU_PATTERN = /^[A-Z0-9][A-Z0-9._/-]{0,39}$/

/** A whole number typed by a person: spaces and thousands separators are ignored. */
function wholeNumber({
  required,
  invalid,
  min = 0,
  minMessage = invalid,
  max,
  maxMessage,
}: {
  required: string
  invalid: string
  min?: number
  minMessage?: string
  max: number
  maxMessage: string
}) {
  return z
    .string()
    .trim()
    .overwrite((value) => value.replace(/[,\s]/g, ''))
    .min(1, required)
    .regex(/^\d+$/, invalid)
    .refine((value) => !/^\d+$/.test(value) || Number(value) >= min, minMessage)
    .refine((value) => !/^\d+$/.test(value) || Number(value) <= max, maxMessage)
}

export const partSchema = z.object({
  sku: z
    .string()
    .trim()
    .toUpperCase()
    .min(1, 'Enter the SKU.')
    .max(40, 'Use at most 40 characters.')
    .regex(SKU_PATTERN, 'Use letters, numbers and . _ / - only, starting with a letter or number.'),
  name: z.string().trim().min(1, 'Enter the part name.').max(120, 'Use at most 120 characters.'),
  category: z.string().trim().max(60, 'Use at most 60 characters.'),
  unit_cost: wholeNumber({
    required: 'Enter the unit cost.',
    invalid: 'Enter whole rupees, like 3500.',
    max: 9_999_999_999,
    maxMessage: 'Enter Rs 9,999,999,999 or less.',
  }),
  reorder_level: wholeNumber({
    required: 'Enter a reorder level (0 or more).',
    invalid: 'Enter a whole number, like 5.',
    max: 100_000,
    maxMessage: 'Enter 100,000 or less.',
  }),
})

export type PartFormValues = z.input<typeof partSchema>

export const adjustSchema = z.object({
  direction: z.enum(['add', 'remove']),
  quantity: wholeNumber({
    required: 'Enter how many units.',
    invalid: 'Enter a whole number, like 5.',
    min: 1,
    minMessage: 'Enter 1 or more.',
    max: 100_000,
    maxMessage: 'Enter 100,000 or less.',
  }),
  reason: z
    .string()
    .trim()
    .min(1, 'Say why the stock changed.')
    .max(500, 'Use at most 500 characters.'),
})

export type AdjustFormValues = z.input<typeof adjustSchema>

/** The signed `quantity_delta` of the form; 0 while the quantity is not a whole number. */
export function signedDelta(values: Pick<AdjustFormValues, 'direction' | 'quantity'>): number {
  const text = values.quantity.replace(/[,\s]/g, '')
  if (!/^\d+$/.test(text)) return 0
  const quantity = Number(text)
  return values.direction === 'remove' ? -quantity : quantity
}

/**
 * `adjustSchema` plus the stock rule for this part (409 `INSUFFICIENT_STOCK`), so a refused change
 * is flagged on the quantity together with any other field error.
 */
export function adjustSchemaFor(part: Pick<MockPart, 'on_hand' | 'reserved'>) {
  return adjustSchema.superRefine((values, ctx) => {
    const delta = signedDelta(values)
    if (delta === 0) return
    const problem = adjustmentError(part, delta)
    if (problem) ctx.addIssue({ code: 'custom', path: ['quantity'], message: problem })
  })
}
