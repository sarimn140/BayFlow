'use client'

import { Check } from 'lucide-react'
import Link from 'next/link'

import { cn } from '@/lib/utils'

export const WIZARD_STEPS = ['shop', 'services', 'time', 'details', 'review'] as const
export type WizardStep = (typeof WIZARD_STEPS)[number]

const LABEL: Record<WizardStep, string> = {
  shop: 'Workshop',
  services: 'Services',
  time: 'Date & time',
  details: 'Your details',
  review: 'Review',
}

/**
 * The wizard's progress (spec 10 P-03 "Shell"): an ordered list in a labelled nav, the current
 * step marked with `aria-current="step"`, completed steps clickable. Below `md` only the current
 * step shows its label (the others keep theirs for screen readers). The connectors stretch and
 * shrink, so the bar fills its row on a laptop and still fits a 320px phone.
 */
export function BookingSteps({
  current,
  hrefFor,
}: {
  current: WizardStep
  /** Where a completed step links to; the shop step always goes back to the directory. */
  hrefFor?: (step: WizardStep) => string
}) {
  const currentIndex = WIZARD_STEPS.indexOf(current)
  return (
    <nav aria-label="Booking steps">
      <ol className="flex w-full max-w-4xl items-center gap-1.5 sm:gap-3">
        {WIZARD_STEPS.map((step, index) => {
          const done = index < currentIndex
          const isCurrent = index === currentIndex
          const last = index === WIZARD_STEPS.length - 1
          const href = done ? (step === 'shop' ? '/book' : hrefFor?.(step)) : undefined
          const content = (
            <>
              <span
                className={cn(
                  'flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-semibold transition-colors sm:size-8',
                  done && 'border-brand-green bg-brand-green text-white',
                  isCurrent &&
                    'border-brand-blue bg-brand-blue text-white shadow-md ring-4 shadow-brand-blue/25 ring-brand-blue/15',
                  !done && !isCurrent && 'border-border bg-card text-muted-foreground',
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : index + 1}
              </span>
              {isCurrent ? (
                <span className="min-w-0 truncate text-sm font-semibold text-foreground">
                  {LABEL[step]}
                </span>
              ) : (
                <>
                  <span className="hidden text-sm font-semibold whitespace-nowrap text-muted-foreground transition-colors group-hover/step:text-foreground md:inline">
                    {LABEL[step]}
                    {done && <span className="sr-only"> (done)</span>}
                  </span>
                  <span className="sr-only md:hidden">
                    {LABEL[step]}
                    {done && ' (done)'}
                  </span>
                </>
              )}
            </>
          )
          return (
            <li
              key={step}
              aria-current={isCurrent ? 'step' : undefined}
              className={cn(
                'flex items-center gap-1.5 sm:gap-3',
                !last && 'flex-auto',
                isCurrent && 'min-w-0',
              )}
            >
              {href ? (
                <Link
                  href={href}
                  className="group/step flex min-w-0 items-center gap-2 rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {content}
                </Link>
              ) : (
                <span className="flex min-w-0 items-center gap-2">{content}</span>
              )}
              {!last && (
                <span
                  aria-hidden
                  className={cn(
                    'h-0.5 min-w-2 flex-1 rounded-full',
                    done ? 'bg-brand-green' : 'bg-border',
                  )}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
