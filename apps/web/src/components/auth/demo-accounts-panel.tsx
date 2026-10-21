'use client'

import { Check, Copy, Info, Lightbulb } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader } from '@/components/ui/card'
import {
  DEMO_ACCOUNTS,
  DEMO_AHMED_NOTE,
  DEMO_PASSWORD,
  type DemoAccount,
} from '@/content/demo-accounts'
import { cn } from '@/lib/utils'

/** Each role wears the hue of the booking phase it works on (spec 09 §3.3). */
const ROLE_TONE: Record<string, string> = {
  Owner: 'bg-brand-blue text-brand-blue-foreground',
  'Service Advisor': 'bg-status-estimate-bg text-status-estimate-fg',
  Technician: 'bg-status-inspection-bg text-status-inspection-fg',
  'QC Inspector': 'bg-status-repair-qc-bg text-status-repair-qc-fg',
  'Parts Person': 'bg-status-parts-bg text-status-parts-fg',
  Customer: 'bg-status-handover-bg text-status-handover-fg',
  'Platform Admin': 'bg-foreground text-background',
}

/** D71: shared demo data drifts as testers replay the worked example. */
const DEMO_DRIFT_TIP =
  'Friday 10:00 full or parts used up by earlier testers? Pick another slot; Usman (Parts) can adjust stock.'

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export interface DemoAccountsPanelProps {
  /** Fills the login form with the account's e-mail and the shared password (D52: no auto-login). */
  onPick: (account: DemoAccount) => void
  /** The e-mail currently in the form, to mark the matching account. */
  selectedEmail?: string
}

/**
 * Demo credentials (spec 09 §4.12, D52): every account's name, role and e-mail in plain text, the
 * shared password, and the judge notes. Picking an account only fills the form; the user still
 * presses Log in.
 */
export function DemoAccountsPanel({ onPick, selectedEmail }: DemoAccountsPanelProps) {
  const [copied, setCopied] = useState(false)

  const copyPassword = async () => {
    try {
      await navigator.clipboard.writeText(DEMO_PASSWORD)
      setCopied(true)
      toast.success('Demo password copied')
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(`Copy failed. The password is ${DEMO_PASSWORD}`)
    }
  }

  return (
    <Card aria-labelledby="demo-accounts-title" role="region" className="gap-0 py-0">
      <CardHeader className="gap-1.5 border-b pt-(--card-spacing)">
        <h2 id="demo-accounts-title" className="text-lg leading-7 font-semibold text-foreground">
          Demo accounts
        </h2>
        <CardDescription className="text-pretty">
          Pick an account to fill in the form, then press Log in.
        </CardDescription>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="text-sm text-muted-foreground">Password for every account</span>
          <Button
            type="button"
            variant="outline"
            onClick={copyPassword}
            aria-label={`Copy the demo password ${DEMO_PASSWORD}`}
            className="font-mono"
          >
            {DEMO_PASSWORD}
            {copied ? (
              <Check data-icon="inline-end" className="text-success-ink" aria-hidden="true" />
            ) : (
              <Copy data-icon="inline-end" className="text-helper" aria-hidden="true" />
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="px-2 py-2 sm:px-3 sm:py-3">
        {/* One row per account: name and role, then the e-mail (beside them when there is room) */}
        <ul className="@container grid gap-1">
          {DEMO_ACCOUNTS.map((account) => {
            const selected = account.email === selectedEmail
            return (
              <li key={account.email}>
                <button
                  type="button"
                  onClick={() => onPick(account)}
                  aria-pressed={selected}
                  className={cn(
                    'flex min-h-12 w-full items-center gap-3 rounded-xl border px-3 py-2 text-left transition-colors duration-150 outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid',
                    selected
                      ? 'border-brand-blue bg-brand-blue-subtle'
                      : 'border-transparent hover:bg-brand-blue-subtle/40',
                  )}
                >
                  {/* The role's hue; a check once the account is in the form */}
                  <Avatar aria-hidden="true" className="size-8 after:hidden">
                    <AvatarFallback
                      className={cn(
                        'text-xs font-semibold',
                        selected
                          ? 'bg-brand-blue text-brand-blue-foreground'
                          : (ROLE_TONE[account.role] ?? ''),
                      )}
                    >
                      {selected ? (
                        <Check className="size-4" strokeWidth={3} />
                      ) : (
                        initials(account.name)
                      )}
                    </AvatarFallback>
                  </Avatar>
                  <span className="flex min-w-0 flex-1 flex-col @sm:grid @sm:grid-cols-[minmax(0,1fr)_auto] @sm:items-center @sm:gap-x-4">
                    <span className="text-sm leading-5 font-semibold text-foreground">
                      <span className="sr-only">Use </span>
                      {account.name}
                      <span className="font-normal text-muted-foreground"> · {account.role}</span>
                    </span>
                    <span className="text-xs leading-5 break-all text-muted-foreground @sm:col-start-2 @sm:row-start-1 @sm:text-right @sm:break-normal">
                      {account.email}
                    </span>
                    {account.note && (
                      <span className="text-xs leading-5 text-helper first-letter:uppercase @sm:col-span-2">
                        {account.note}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </CardContent>

      <CardFooter className="flex-col items-stretch gap-2.5 border-t bg-muted py-4 text-sm text-muted-foreground">
        <p className="flex gap-2.5">
          <Info className="mt-0.5 size-4 shrink-0 text-info-ink" aria-hidden="true" />
          <span>{DEMO_AHMED_NOTE}</span>
        </p>
        <p className="flex gap-2.5">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-warning-ink" aria-hidden="true" />
          <span>{DEMO_DRIFT_TIP}</span>
        </p>
      </CardFooter>
    </Card>
  )
}
