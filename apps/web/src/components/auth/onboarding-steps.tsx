import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

export const ONBOARDING_STEPS = ['Your account', 'Your shop', 'Your team'] as const

/**
 * Owner onboarding (spec 10 P-05 → S-03 → O-02): register, then create the shop, then add the
 * team. Drawn like the booking wizard's steps: the current step is a blue disc with a halo, done
 * steps are green with a check. Where the steps have less than 28rem (phones, the narrow form
 * column at `lg`), only the current label shows; screen readers always hear every label.
 */
export function OnboardingSteps({ current }: { current: number }) {
  return (
    <ol aria-label="Setup steps" className="@container flex items-center gap-2 @md:gap-3">
      {ONBOARDING_STEPS.map((label, index) => {
        const state = index < current ? 'done' : index === current ? 'current' : 'next'
        return (
          <li
            key={label}
            aria-current={state === 'current' ? 'step' : undefined}
            className="flex min-w-0 items-center gap-2 not-last:flex-1 @md:gap-3"
          >
            <span
              aria-hidden="true"
              className={cn(
                'flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold',
                state === 'current' &&
                  'border-brand-blue bg-brand-blue text-brand-blue-foreground shadow-md ring-4 shadow-brand-blue/25 ring-brand-blue/15',
                state === 'done' && 'border-brand-green bg-brand-green text-brand-green-foreground',
                state === 'next' && 'border-border-medium bg-card text-muted-foreground',
              )}
            >
              {state === 'done' ? <Check className="size-4" /> : index + 1}
            </span>
            <span
              className={cn(
                'text-sm whitespace-nowrap',
                state === 'current'
                  ? 'font-semibold text-foreground'
                  : 'text-muted-foreground @max-md:sr-only',
              )}
            >
              <span className="sr-only">
                Step {index + 1} of {ONBOARDING_STEPS.length}:{' '}
              </span>
              {label}
              {state === 'done' && <span className="sr-only"> (done)</span>}
            </span>
            {index < ONBOARDING_STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className={cn(
                  'h-0.5 min-w-4 flex-1 rounded-full',
                  state === 'done' ? 'bg-brand-green' : 'bg-border',
                )}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
