import { Check, ChevronRight, CircleCheckBig, Rocket } from 'lucide-react'
import Link from 'next/link'

import { Card, CardAction, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import type { SetupState } from './overview-data'
import { plural } from './overview-data'

export interface SetupChecklistProps {
  shopName: string
  setup: SetupState
  activeServices: number
  staffCount: number
  partsCount: number
  base: string
}

/**
 * First-run checklist (spec 10 O-01, UX rule R12): add services → O-03, add the team → O-02,
 * add parts → PP-03, list the shop → O-04. Each step shows whether it is done.
 */
export function SetupChecklist({
  shopName,
  setup,
  activeServices,
  staffCount,
  partsCount,
  base,
}: SetupChecklistProps) {
  const steps = [
    {
      key: 'services',
      title: 'Add services',
      done: setup.hasServices,
      doneText: `${plural(activeServices, 'active service')} customers can book`,
      todoText: 'Add what customers can book, with a price and a duration.',
      href: `${base}/services`,
    },
    {
      key: 'team',
      title: 'Add your team',
      done: setup.hasTeam,
      doneText: `${plural(staffCount, 'team member')} besides you`,
      todoText: 'Invite advisors, technicians, parts staff and QC inspectors.',
      href: `${base}/team`,
    },
    {
      key: 'parts',
      title: 'Add parts',
      done: setup.hasParts,
      doneText: `${plural(partsCount, 'part')} in your inventory`,
      todoText: 'Enter your opening stock of parts and fluids.',
      href: `${base}/inventory`,
    },
    {
      key: 'listing',
      title: 'List your shop',
      done: setup.isListed,
      doneText: 'Shown in the BayFlow shop directory',
      todoText: 'Show your shop in the directory so customers can find it.',
      href: `${base}/settings`,
    },
  ]
  const doneCount = steps.filter((s) => s.done).length
  const allDone = doneCount === steps.length

  return (
    <Card className={cn(!allDone && 'border-brand-blue/30')}>
      <CardHeader>
        <CardHeading id="setup-title">
          {allDone ? (
            <CircleCheckBig className="size-5 text-success-ink" aria-hidden="true" />
          ) : (
            <Rocket className="size-5 text-brand-blue-ink" aria-hidden="true" />
          )}
          {allDone ? 'Your shop is ready' : `Set up ${shopName}`}
        </CardHeading>
        <CardDescription>
          {allDone
            ? 'Services, team, parts and the directory listing are all in place.'
            : 'Finish these steps so customers can book you and your team can get to work.'}
        </CardDescription>
        <CardAction>
          <p className="text-sm font-semibold text-foreground tabular-nums">
            {doneCount} of {steps.length} done
          </p>
        </CardAction>
      </CardHeader>
      <CardContent className="gap-5">
        <Progress
          value={(doneCount / steps.length) * 100}
          aria-labelledby="setup-title"
          aria-valuenow={doneCount}
          aria-valuemax={steps.length}
          aria-valuetext={`${doneCount} of ${steps.length} steps done`}
        />
        <ol className="grid gap-3 @xl/overview:grid-cols-2 @4xl/overview:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step.key}>
              <Link
                href={step.href}
                className="group flex h-full items-start gap-3 rounded-2xl border border-border bg-card p-4 transition-colors duration-150 outline-none hover:border-brand-blue/40 hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
              >
                {step.done ? (
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-green text-brand-green-foreground">
                    <Check className="size-4" aria-hidden="true" />
                  </span>
                ) : (
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full border-2 border-border-medium text-sm font-semibold text-muted-foreground tabular-nums">
                    {index + 1}
                  </span>
                )}
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="block text-sm font-semibold text-foreground">
                    <span className="sr-only">{step.done ? 'Done: ' : 'To do: '}</span>
                    {step.title}
                  </span>
                  <span className="block text-sm text-muted-foreground">
                    {step.done ? step.doneText : step.todoText}
                  </span>
                </span>
                <ChevronRight
                  className="mt-1.5 size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}
