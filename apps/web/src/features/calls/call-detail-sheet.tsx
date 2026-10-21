'use client'

/**
 * A call's AI summary, transcript and tasks (spec 05 §6.5, §9.6), in the right sheet the app uses
 * for record previews (DESIGN.md §6.10). Staff only (D21).
 */
import { useQuery } from '@tanstack/react-query'
import { Bot, ShieldCheck, User, Wrench } from 'lucide-react'

import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import { getCallDetail } from './api'
import { outcomeOf } from './format'
import type { CallDetailRead } from './types'

type Summary = NonNullable<CallDetailRead['summary']>
type Entry = Summary['transcript'][number]

export const SENTIMENT: Record<
  string,
  { label: string; variant: 'success' | 'neutral' | 'destructive' }
> = {
  POSITIVE: { label: 'Positive', variant: 'success' },
  NEUTRAL: { label: 'Neutral', variant: 'neutral' },
  NEGATIVE: { label: 'Negative', variant: 'destructive' },
}

const IDENTITY: Record<string, string> = {
  BOOKING_REFERENCE: 'Caller verified by booking reference',
  EMAIL: 'Caller verified by e-mail',
  PHONE: 'Caller verified by phone number',
  NAME: 'Caller verified by name',
}

export function CallDetailSheet({
  shopId,
  callId,
  onOpenChange,
}: {
  shopId: string
  callId: string | null
  onOpenChange: (open: boolean) => void
}) {
  const query = useQuery({
    queryKey: ['calls', 'detail', shopId, callId],
    queryFn: () => getCallDetail(shopId, callId!),
    enabled: Boolean(callId),
  })
  const call = query.data

  return (
    <Sheet open={Boolean(callId)} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>AI call summary</SheetTitle>
          <SheetDescription>
            {call ? (
              <>
                <span className="font-medium text-foreground">{call.caller.display_name}</span> ·{' '}
                <span className="font-mono">{call.booking_reference}</span> ·{' '}
                {formatDateTime(call.started_at)}
              </>
            ) : (
              'Loading the call…'
            )}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-6 px-6 pb-8">
          {query.isPending ? (
            <div className="space-y-3" aria-busy="true">
              <Skeleton className="h-24 rounded-2xl" />
              <Skeleton className="h-64 rounded-2xl" />
            </div>
          ) : !call ? (
            <Alert variant="destructive">
              <AlertDescription>This call couldn&apos;t be loaded.</AlertDescription>
            </Alert>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">{outcomeOf(call)}</p>
              {call.summary ? (
                <SummaryBlock summary={call.summary} identity={call.identity_method} />
              ) : (
                <Alert variant="info">
                  <AlertDescription>
                    {call.ai
                      ? 'The summary is not ready yet. It appears a few seconds after the call ends.'
                      : 'Only calls answered by the AI Front Desk have a summary.'}
                  </AlertDescription>
                </Alert>
              )}
              {call.tasks.length > 0 ? (
                <section className="space-y-2">
                  <h3 className="text-base font-semibold text-foreground">Tasks from this call</h3>
                  <ul className="space-y-2">
                    {call.tasks.map((task) => (
                      <li
                        key={task.id}
                        className="flex items-start justify-between gap-3 rounded-xl border border-border px-4 py-3"
                      >
                        <p className="text-sm font-medium text-foreground">{task.title}</p>
                        <Badge
                          variant={
                            task.status === 'DONE'
                              ? 'success'
                              : task.is_urgent
                                ? 'destructive'
                                : 'neutral'
                          }
                        >
                          {task.status === 'DONE' ? 'Done' : task.is_urgent ? 'Urgent' : 'Open'}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {call.summary?.transcript.length ? (
                <Transcript entries={call.summary.transcript} />
              ) : null}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function SummaryBlock({ summary, identity }: { summary: Summary; identity: string | null }) {
  const sentiment = SENTIMENT[summary.sentiment] ?? SENTIMENT.NEUTRAL!
  return (
    <section className="space-y-3 rounded-2xl bg-layer p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={sentiment.variant}>{sentiment.label}</Badge>
        {summary.is_urgent ? <Badge variant="destructive">Urgent</Badge> : null}
        {summary.is_fallback ? (
          <Badge variant="warning">Automatic summary unavailable</Badge>
        ) : null}
      </div>
      <h3 className="text-base font-semibold text-foreground">{summary.intent}</h3>
      <p className="text-sm leading-6 text-muted-foreground">{summary.details}</p>
      {identity ? (
        <p className="flex items-center gap-1.5 text-sm text-success-ink">
          <ShieldCheck aria-hidden="true" className="size-4" />
          {IDENTITY[identity] ?? 'Caller verified'}
        </p>
      ) : null}
    </section>
  )
}

function Transcript({ entries }: { entries: Entry[] }) {
  return (
    <section className="space-y-3">
      <h3 className="text-base font-semibold text-foreground">Transcript</h3>
      <ol className="space-y-2.5">
        {entries.map((entry, index) => {
          if (entry.role === 'tool_call' || entry.role === 'tool_result') {
            return (
              <li key={index} className="flex items-center gap-2 text-xs text-helper">
                <Wrench aria-hidden="true" className="size-3.5 shrink-0" />
                <span className="truncate">
                  {entry.role === 'tool_call' ? 'Looked up' : 'Got'}{' '}
                  <span className="font-mono">{entry.tool}</span>
                </span>
              </li>
            )
          }
          const customer = entry.role === 'customer'
          return (
            <li
              key={index}
              className={cn('flex gap-2', customer ? 'justify-start' : 'justify-end')}
            >
              {customer ? (
                <User aria-hidden="true" className="mt-1.5 size-4 shrink-0 text-helper" />
              ) : null}
              <p
                className={cn(
                  'max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-6',
                  customer
                    ? 'rounded-tl-md bg-secondary text-foreground'
                    : 'rounded-tr-md bg-brand-blue-subtle text-foreground',
                )}
              >
                <span className="sr-only">{customer ? 'Customer: ' : 'AI Front Desk: '}</span>
                {entry.text}
              </p>
              {!customer ? (
                <Bot aria-hidden="true" className="mt-1.5 size-4 shrink-0 text-brand-blue-ink" />
              ) : null}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
