'use client'

import {
  Check,
  History,
  PackageCheck,
  Radio,
  Smartphone,
  Store,
  UsersRound,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import { Eyebrow, Handwritten } from '@/components/booking/booking-hero'
import { Logo } from '@/components/layout/logo'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

/**
 * Auth brand panel (spec 10 P-04, P-05) in the landing page's language: a pale blue panel with
 * grid paper and a soft blue glow, one extra-bold line with a handwritten word, and the story for
 * the page: on log-in a sample booking's hand-offs, on registration what an owner gets. Every
 * statement is a product fact (no customer counts, ratings or uptime).
 *
 * Shown from `lg`, pinned to the viewport. Laptop screens are short, so the story sheds detail as
 * the viewport gets shorter instead of being cut off: at 940px and less the spacing tightens, then
 * the secondary lines go (880px), the sentence (760px), the eyebrow (680px) and the card (560px).
 */
export function AuthShowcase() {
  const pathname = usePathname()
  const isRegister = pathname?.startsWith('/register') ?? false

  return (
    <aside
      aria-label="About BayFlow"
      className="hidden lg:sticky lg:top-0 lg:flex lg:h-dvh lg:min-w-0 lg:p-4"
    >
      <div className="relative isolate flex w-full flex-col overflow-hidden rounded-3xl border border-border bg-canvas">
        {/* Decoration: grid paper fading out downwards and a soft brand glow, as on the landing hero */}
        <div
          aria-hidden="true"
          className="bg-grid-pattern pointer-events-none absolute inset-0 -z-10 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-56 -right-44 -z-10 size-[600px] rounded-full bg-brand-blue/10 blur-3xl"
        />

        <div className="flex flex-1 flex-col gap-8 p-10 xl:px-14 [@media(max-height:940px)]:gap-6 [@media(max-height:940px)]:py-8 xl:[@media(min-height:941px)]:py-12">
          <Link
            href="/"
            aria-label="BayFlow home"
            className="flex min-h-10 w-fit items-center rounded-lg outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
          >
            <Logo />
          </Link>

          <div className="my-auto">{isRegister ? <OwnerStory /> : <HandoffStory />}</div>
        </div>
      </div>
    </aside>
  )
}

/** Eyebrow, the big line (not a heading: the page's `h1` is the form's title) and one sentence. */
function StoryIntro({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: ReactNode
  description: string
}) {
  return (
    <div className="space-y-5 [@media(max-height:940px)]:space-y-4">
      <div className="[@media(max-height:680px)]:hidden">
        <Eyebrow>{eyebrow}</Eyebrow>
      </div>
      <p className="max-w-xl text-5xl leading-[1.08] font-extrabold tracking-tight text-foreground">
        {title}
      </p>
      <p className="max-w-md text-base leading-relaxed text-muted-foreground xl:text-lg [@media(max-height:760px)]:hidden">
        {description}
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------------------------------ */
/* Log-in: a sample booking moving through the workshop                                        */
/* ------------------------------------------------------------------------------------------ */

type Phase = 'intake' | 'inspection' | 'estimate' | 'parts' | 'repair-qc' | 'handover'

/** The phase's soft fill, border and ink (spec 09 §3.3), as on the status chips. */
const PHASE_NODE: Record<Phase, string> = {
  intake: 'border-status-intake-border bg-status-intake-bg text-status-intake-fg',
  inspection: 'border-status-inspection-border bg-status-inspection-bg text-status-inspection-fg',
  estimate: 'border-status-estimate-border bg-status-estimate-bg text-status-estimate-fg',
  parts: 'border-status-parts-border bg-status-parts-bg text-status-parts-fg',
  'repair-qc': 'border-status-repair-qc-border bg-status-repair-qc-bg text-status-repair-qc-fg',
  handover: 'border-status-handover-border bg-status-handover-bg text-status-handover-fg',
}

const STATE_LABEL = { done: 'done', current: 'in progress', next: 'next' } as const

const HANDOFFS: ReadonlyArray<{
  phase: Phase
  label: string
  who: string
  time: string
  state: keyof typeof STATE_LABEL
}> = [
  {
    phase: 'intake',
    label: 'Booked online',
    who: 'Customer · Ayesha',
    time: '09:00',
    state: 'done',
  },
  {
    phase: 'inspection',
    label: 'Inspection done',
    who: 'Technician · Imran',
    time: '10:15',
    state: 'done',
  },
  {
    phase: 'estimate',
    label: 'Estimate approved',
    who: 'Customer · from her phone',
    time: '10:24',
    state: 'done',
  },
  { phase: 'parts', label: 'Parts ready', who: 'Parts · Usman', time: '10:27', state: 'done' },
  // The seeded BF-2026-001 is in repair with Imran, so the sample matches what Ayesha sees.
  {
    phase: 'repair-qc',
    label: 'In repair',
    who: 'Technician · Imran',
    time: 'Now',
    state: 'current',
  },
  { phase: 'repair-qc', label: 'Quality check', who: 'QC inspector', time: '', state: 'next' },
  {
    phase: 'handover',
    label: 'Ready for pick-up',
    who: 'The customer is notified',
    time: '',
    state: 'next',
  },
]

const LOGIN_FACTS: ReadonlyArray<{ icon: LucideIcon; title: string; body: string }> = [
  {
    icon: UsersRound,
    title: 'Role workspaces',
    body: 'Owner, advisor, technician, parts and QC each get their own queue.',
  },
  {
    icon: Smartphone,
    title: 'Online approvals',
    body: 'Customers approve estimates from their phone before work starts.',
  },
  {
    icon: History,
    title: 'Full history',
    body: 'Every status change records who did it and when.',
  },
]

function HandoffStory() {
  return (
    <div className="space-y-10 [@media(max-height:940px)]:space-y-6">
      <StoryIntro
        eyebrow="Built for independent garages"
        title={
          <>
            Every hand-off,
            <br /> on the <Handwritten>record</Handwritten>
            {/* The accent word's own end padding would leave a gap before the stop */}
            <span className="-ml-[0.18em]">.</span>
          </>
        }
        description="Bookings, estimates, parts and quality checks for independent garages, in one place."
      />
      <HandoffCard />
      {/* Only on tall screens, where it fits under the card */}
      <ul className="hidden max-w-2xl gap-5 xl:grid-cols-3 [@media(min-height:1100px)]:grid">
        {LOGIN_FACTS.map(({ icon: Icon, title, body }) => (
          <li key={title} className="space-y-2">
            <span className="flex size-9 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <span className="block text-sm font-semibold text-foreground">{title}</span>
            <span className="block text-sm text-muted-foreground">{body}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** A sample booking, phase by phase (illustrative data from the seeded demo shop). */
function HandoffCard() {
  return (
    <figure className="w-full max-w-md rounded-2xl border border-border bg-card p-5 shadow-lg [@media(max-height:560px)]:hidden">
      <figcaption className="flex items-start justify-between gap-4">
        <span className="min-w-0">
          <span className="block font-mono text-sm font-semibold text-brand-blue-ink">
            BF-2026-001
          </span>
          <span className="mt-0.5 block truncate text-sm text-muted-foreground">
            2022 Honda Civic · Lahore Auto Care
          </span>
        </span>
        <Badge variant="success">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-success-ink" />
          Live
        </Badge>
      </figcaption>

      <ol className="mt-5 [@media(max-height:940px)]:mt-4" aria-label="Sample booking timeline">
        {HANDOFFS.map((step, index) => (
          <li
            key={step.label}
            className="relative flex gap-3 pb-3.5 last:pb-0 [@media(max-height:880px)]:pb-2 [@media(max-height:940px)_and_(min-height:881px)]:pb-2.5"
          >
            {index < HANDOFFS.length - 1 && (
              <span
                aria-hidden="true"
                className={cn(
                  'absolute top-6 bottom-0 left-[11.5px] w-px',
                  step.state === 'done' ? 'bg-border-medium' : 'bg-border-faint',
                )}
              />
            )}
            <span
              aria-hidden="true"
              className={cn(
                'relative flex size-6 shrink-0 items-center justify-center rounded-full border',
                step.state === 'next'
                  ? 'border-dashed border-border-strong bg-card'
                  : PHASE_NODE[step.phase],
                step.state === 'current' && 'ring-4 ring-status-repair-qc-bg/70',
              )}
            >
              {step.state === 'done' && <Check className="size-3.5" strokeWidth={3} />}
              {step.state === 'current' && <span className="size-2 rounded-full bg-current" />}
            </span>
            <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3 pt-0.5">
              <span className="min-w-0">
                <span
                  className={cn(
                    'block text-sm',
                    step.state === 'next'
                      ? 'text-muted-foreground'
                      : 'font-semibold text-foreground',
                  )}
                >
                  {step.label}
                  <span className="sr-only"> ({STATE_LABEL[step.state]})</span>
                </span>
                <span className="block truncate text-xs text-helper [@media(max-height:880px)]:hidden">
                  {step.who}
                </span>
              </span>
              {step.time && (
                <span
                  className={cn(
                    'shrink-0 font-mono text-xs',
                    step.state === 'current'
                      ? 'font-semibold text-status-repair-qc-fg'
                      : 'text-helper',
                  )}
                >
                  {step.time}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </figure>
  )
}

/* ------------------------------------------------------------------------------------------ */
/* Registration: what an owner gets                                                             */
/* ------------------------------------------------------------------------------------------ */

const OWNER_FACTS: ReadonlyArray<{ icon: LucideIcon; title: string; body: string }> = [
  {
    icon: Smartphone,
    title: 'Online estimate approval',
    body: 'Customers approve or decline the estimate from their phone before work starts.',
  },
  {
    icon: Radio,
    title: 'Live status updates',
    body: 'Staff and customers see every status change as it happens.',
  },
  {
    icon: Store,
    title: 'Built for multi-shop owners',
    body: 'Switch between your shops, or see all of them on one summary.',
  },
  {
    icon: PackageCheck,
    title: 'Parts and QC built in',
    body: 'Parts requests, stock and purchase orders, and a quality check before every hand-over.',
  },
]

function OwnerStory() {
  return (
    <div className="space-y-10 [@media(max-height:940px)]:space-y-6">
      <StoryIntro
        eyebrow="For garage owners"
        title={
          <>
            Welcome to <Handwritten>BayFlow</Handwritten>
          </>
        }
        description="Owner, service advisor, technician, parts and QC: five roles on one shared workflow, from the online booking to the hand-over."
      />
      {/* Two by two; the explanations need the width of xl and a screen tall enough for them */}
      <ul className="grid max-w-2xl grid-cols-2 gap-3 [@media(max-height:560px)]:hidden">
        {OWNER_FACTS.map(({ icon: Icon, title, body }) => (
          <li
            key={title}
            className="flex gap-3 rounded-2xl border border-border bg-card p-4 shadow-xs xl:gap-3.5"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
              <Icon className="size-5" aria-hidden="true" />
            </span>
            <span className="min-w-0 space-y-1">
              <span className="block text-sm font-semibold text-foreground">{title}</span>
              <span className="hidden text-sm leading-snug text-muted-foreground xl:[@media(min-height:761px)]:block">
                {body}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
