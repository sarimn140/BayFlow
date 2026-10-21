'use client'

import { ChevronDown } from 'lucide-react'
import type { ReactNode, Ref } from 'react'

import { StickyActionBar } from '@/components/layout/detail-layout'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Separator } from '@/components/ui/separator'
import type { BookingStatus } from '@/lib/status'
import { cn } from '@/lib/utils'

import { StatusTile } from './detail-bits'
import type { NextStep } from './next-step'
import { SA_ACTIONS, type ActionBarPlan, type SaActionSlug } from './sa-actions'

export interface Fact {
  label: string
  value: ReactNode
}

function ActionButton({
  slug,
  onAction,
  variant,
  className,
}: {
  slug: SaActionSlug
  onAction: (slug: SaActionSlug) => void
  /** `destructive-outline` for decline and cancel (spec 09 §4.6 rule 3, DESIGN.md §6.15). */
  variant: 'default' | 'outline' | 'destructive-outline'
  className?: string
}) {
  const action = SA_ACTIONS[slug]
  const Icon = action.icon
  return (
    <Button type="button" variant={variant} className={className} onClick={() => onAction(slug)}>
      <Icon data-icon="inline-start" aria-hidden="true" />
      {action.label}
    </Button>
  )
}

/**
 * The side card (spec 10 SA-02, DESIGN.md §6.5): whose turn it is, what to do, the action bar in
 * spec 09 order (one blue primary, outline others, destructive last after a separator) and the
 * booking's key facts. Below `md` a primary action moves to `MobileActionBar`.
 */
export function NextStepCard({
  status,
  step,
  plan,
  onAction,
  facts,
  note,
  headingRef,
}: {
  status: BookingStatus
  step: NextStep
  plan: ActionBarPlan
  onAction: (slug: SaActionSlug) => void
  facts: ReadonlyArray<Fact>
  /** A quoted reason under the description (decline or cancel). */
  note?: ReactNode
  /** Focus lands here after an action, so the new step is announced (spec 09 §4.6 rule 4). */
  headingRef?: Ref<HTMLHeadingElement>
}) {
  // Without a primary there are no other forward actions either (`planActionBar`).
  const forward: SaActionSlug[] = plan.primary ? [plan.primary, ...plan.secondary] : []
  const hasPrimary = forward.length > 0
  const hasButtons = hasPrimary || plan.destructive.length > 0

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex items-start gap-3">
          <StatusTile status={status} />
          <div className="min-w-0 space-y-0.5">
            <p
              className={cn(
                'text-sm font-semibold',
                step.kind === 'act' ? 'text-brand-blue-ink' : 'text-muted-foreground',
              )}
            >
              {step.label}
            </p>
            <h2
              ref={headingRef}
              tabIndex={-1}
              className="text-lg leading-7 font-semibold text-foreground outline-none"
            >
              {step.title}
            </h2>
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{step.description}</p>
        {note}
      </CardHeader>

      {hasButtons ? (
        <CardContent className={cn('gap-2', hasPrimary && 'max-md:hidden')}>
          {forward.map((slug, index) => (
            <ActionButton
              key={slug}
              slug={slug}
              onAction={onAction}
              variant={index === 0 ? 'default' : 'outline'}
              className="w-full"
            />
          ))}
          {hasPrimary && plan.destructive.length > 0 ? (
            <Separator className="my-1 bg-border-faint" />
          ) : null}
          {plan.destructive.map((slug) => (
            <ActionButton
              key={slug}
              slug={slug}
              onAction={onAction}
              variant="destructive-outline"
              className="w-full"
            />
          ))}
        </CardContent>
      ) : null}

      {facts.length > 0 ? (
        <CardFooter className="border-t">
          <dl className="w-full divide-y divide-border-faint text-sm">
            {facts.map((fact) => (
              <div
                key={fact.label}
                className="flex items-baseline justify-between gap-4 py-2.5 first:pt-0 last:pb-0"
              >
                <dt className="shrink-0 text-muted-foreground">{fact.label}</dt>
                <dd className="min-w-0 text-right font-medium text-foreground tabular-nums">
                  {fact.value}
                </dd>
              </div>
            ))}
          </dl>
        </CardFooter>
      ) : null}
    </Card>
  )
}

/**
 * Phones (DESIGN.md §6.11, spec 10 SA-02 "Mobile"): the primary action pinned to the bottom of
 * the screen, every other action under "More". Nothing renders without a primary, so a lone
 * destructive action never becomes the most prominent button.
 */
export function MobileActionBar({
  plan,
  onAction,
}: {
  plan: ActionBarPlan
  onAction: (slug: SaActionSlug) => void
}) {
  if (!plan.primary) return null
  const hasMore = plan.secondary.length > 0 || plan.destructive.length > 0
  return (
    <StickyActionBar className="md:hidden">
      <ActionButton slug={plan.primary} onAction={onAction} variant="default" className="flex-1" />
      {hasMore ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" aria-label="More actions">
              More
              <ChevronDown data-icon="inline-end" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-56">
            {plan.secondary.map((slug) => {
              const Icon = SA_ACTIONS[slug].icon
              return (
                <DropdownMenuItem key={slug} onSelect={() => onAction(slug)}>
                  <Icon aria-hidden="true" />
                  {SA_ACTIONS[slug].label}
                </DropdownMenuItem>
              )
            })}
            {plan.secondary.length > 0 && plan.destructive.length > 0 ? (
              <DropdownMenuSeparator />
            ) : null}
            {plan.destructive.map((slug) => {
              const Icon = SA_ACTIONS[slug].icon
              return (
                <DropdownMenuItem key={slug} variant="destructive" onSelect={() => onAction(slug)}>
                  <Icon aria-hidden="true" />
                  {SA_ACTIONS[slug].label}
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </StickyActionBar>
  )
}
