import { Circle, CircleCheck } from 'lucide-react'

import { cn } from '@/lib/utils'

/** D10: passwords are 12–128 characters. */
export const PASSWORD_MIN = 12
export const PASSWORD_MAX = 128

export type PasswordScore = 0 | 1 | 2 | 3 | 4

/** 0 empty · 1 too short · 2 fair · 3 good · 4 strong (length first, then character variety). */
export function passwordScore(password: string): PasswordScore {
  if (!password) return 0
  if (password.length < PASSWORD_MIN || password.length > PASSWORD_MAX) return 1
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(password)).length
  let score = 2
  if (password.length >= 16) score += 1
  if (classes >= 3) score += 1
  return Math.min(score, 4) as PasswordScore
}

const LABEL = ['', 'Too short', 'Fair', 'Good', 'Strong'] as const
const FILL = ['', 'bg-danger-ink', 'bg-warning-ink', 'bg-brand-blue', 'bg-success-ink'] as const
const INK = ['', 'text-danger-ink', 'text-warning-ink', 'text-brand-blue-ink', 'text-success-ink']

/**
 * Strength meter plus the one hard rule (D10). The rule is the field's helper text; the strength
 * word is announced politely as it changes. Colour is never the only signal: the bar length and the
 * word say the same thing.
 */
export function PasswordStrength({ password, id }: { password: string; id?: string }) {
  const score = passwordScore(password)
  const longEnough = password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX

  return (
    <div id={id} className="space-y-2 pt-0.5">
      <div className="flex gap-1.5" aria-hidden="true">
        {[1, 2, 3, 4].map((step) => (
          <span
            key={step}
            className={cn(
              'h-1.5 flex-1 rounded-full transition-colors duration-200 ease-out',
              score >= step ? FILL[score] : 'bg-layer-accent',
            )}
          />
        ))}
      </div>
      <div className="flex items-center justify-between gap-3 text-xs">
        <span
          className={cn(
            'inline-flex items-center gap-1.5',
            longEnough ? 'text-success-ink' : 'text-muted-foreground',
          )}
        >
          {longEnough ? (
            <CircleCheck className="size-3.5" aria-hidden="true" />
          ) : (
            <Circle className="size-3.5" aria-hidden="true" />
          )}
          {PASSWORD_MIN} to {PASSWORD_MAX} characters
        </span>
        <span aria-live="polite" className={cn('font-medium', INK[score])}>
          {score > 0 && <span className="sr-only">Password strength: </span>}
          {LABEL[score]}
        </span>
      </div>
    </div>
  )
}
