'use client'

/**
 * AI calls & tasks (spec 05 §6.5, §9.6; spec 10 B-04): for the Service Advisor and the Owner.
 * Open tasks first (urgent on top, then newest), each with its AI call summary and transcript and a
 * "Mark as done" with an optional note; a Done tab; and the shop's call log. New tasks arrive live
 * (`task.created`) with a toast.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  CalendarClock,
  CheckCheck,
  CircleAlert,
  ClipboardList,
  ListChecks,
  PhoneCall,
  PhoneMissed,
  Siren,
  type LucideIcon,
} from 'lucide-react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { StatCard } from '@/components/layout/stat-card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useMockStore } from '@/hooks/use-mock-store'
import { formatDateTime, formatRelative } from '@/lib/format'
import { getShopById } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { listShopCalls, listTasks, markTaskDone } from './api'
import { CallDetailSheet, SENTIMENT } from './call-detail-sheet'
import { CALLING_ENABLED } from './config'
import { outcomeOf } from './format'
import type { CallRead, TaskRead } from './types'
import { useLiveShopId } from './use-live-booking'

const KIND: Record<string, { label: string; icon: LucideIcon }> = {
  CALLBACK: { label: 'Call back', icon: PhoneCall },
  RESCHEDULE_REQUEST: { label: 'Reschedule', icon: CalendarClock },
  ESCALATION: { label: 'Escalation', icon: Siren },
  FOLLOW_UP: { label: 'Follow-up', icon: ClipboardList },
}

export function AiCallsPage() {
  const params = useParams<{ shopId: string }>()
  const mockShopId = params.shopId
  const shop = useMockStore(() => getShopById(mockShopId))
  const live = useLiveShopId(shop?.slug)
  const router = useRouter()
  const search = useSearchParams()
  const openCall = search.get('call')
  const [tab, setTab] = useState('open')

  const shopId = live.data?.state === 'ready' ? live.data.shopId : null
  const open = useQuery({
    queryKey: ['calls', 'tasks', shopId, 'OPEN'],
    queryFn: () => listTasks(shopId!, 'OPEN'),
    enabled: Boolean(shopId),
    refetchInterval: 30_000,
  })
  const done = useQuery({
    queryKey: ['calls', 'tasks', shopId, 'DONE'],
    queryFn: () => listTasks(shopId!, 'DONE'),
    enabled: Boolean(shopId) && tab === 'done',
  })
  const log = useQuery({
    queryKey: ['calls', 'shop-log', shopId],
    queryFn: () => listShopCalls(shopId!),
    enabled: Boolean(shopId),
    refetchInterval: 30_000,
  })

  const setOpenCall = (callId: string | null) => {
    const next = new URLSearchParams(search.toString())
    if (callId) next.set('call', callId)
    else next.delete('call')
    const query = next.toString()
    router.replace(query ? `?${query}` : '?', { scroll: false })
  }

  const header = (
    <PageHeader
      eyebrow="AI Front Desk"
      title="AI calls & tasks"
      description="Calls the AI Front Desk answered when no advisor could pick up, and the follow-ups it left for your team."
    />
  )

  if (!CALLING_ENABLED) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState
          icon={Bot}
          tone="neutral"
          title="In-app calling is not set up"
          description="Add the LiveKit settings to turn on calls and the AI Front Desk."
        />
      </div>
    )
  }

  if (live.data?.state === 'signed-out' || live.data?.state === 'unavailable') {
    return (
      <div className="space-y-6">
        {header}
        <Alert variant="info">
          <CircleAlert aria-hidden="true" />
          <AlertTitle>
            {live.data.state === 'signed-out'
              ? 'Sign in again to see AI calls'
              : 'Not available for this shop'}
          </AlertTitle>
          <AlertDescription>
            {live.data.state === 'signed-out'
              ? 'AI calls and tasks come from the live system. Log out and sign in with your account password.'
              : 'AI calls and tasks are shown to the shop’s Service Advisors and Owner.'}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const openTasks = open.data?.items ?? []
  const urgent = openTasks.filter((task) => task.is_urgent).length
  const calls = log.data?.items ?? []
  const aiAnswered = calls.filter((call) => call.ai && call.ai.status !== 'NONE').length
  const missed = calls.filter((call) => call.status === 'MISSED').length

  return (
    <div className="space-y-6">
      {header}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Open tasks"
          value={open.isPending ? '—' : openTasks.length}
          icon={ListChecks}
          tone="brand"
          hint="Follow-ups waiting for an advisor"
        />
        <StatCard
          label="Urgent"
          value={open.isPending ? '—' : urgent}
          icon={Siren}
          tone={urgent > 0 ? 'danger' : 'default'}
          hint="Safety concerns and requests for a person"
        />
        <StatCard
          label="Answered by AI"
          value={log.isPending ? '—' : aiAnswered}
          icon={Bot}
          tone="success"
          hint="In the latest 50 calls"
        />
        <StatCard
          label="Missed calls"
          value={log.isPending ? '—' : missed}
          icon={PhoneMissed}
          tone={missed > 0 ? 'warning' : 'default'}
          hint="Nobody picked up in time"
        />
      </div>

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList aria-label="Show">
          <TabsTrigger value="open">
            Open
            {openTasks.length ? (
              <Badge variant="secondary" className="ml-1.5 tabular-nums">
                {openTasks.length}
              </Badge>
            ) : null}
          </TabsTrigger>
          <TabsTrigger value="done">Done</TabsTrigger>
          <TabsTrigger value="log">Call log</TabsTrigger>
        </TabsList>

        <TabsContent value="open">
          <TaskList
            shopId={shopId}
            loading={open.isPending || live.isPending}
            tasks={openTasks}
            onOpenCall={setOpenCall}
            empty={
              <EmptyState
                tone="success"
                icon={CheckCheck}
                title="No open tasks"
                description="When the AI Front Desk answers a call, its follow-up lands here."
              />
            }
          />
        </TabsContent>
        <TabsContent value="done">
          <TaskList
            shopId={shopId}
            loading={done.isPending}
            tasks={done.data?.items ?? []}
            onOpenCall={setOpenCall}
            empty={
              <EmptyState
                tone="neutral"
                icon={ListChecks}
                title="Nothing marked as done yet"
                description="Tasks you close move here with who closed them and when."
              />
            }
          />
        </TabsContent>
        <TabsContent value="log">
          <CallLog loading={log.isPending} calls={calls} onOpenCall={setOpenCall} />
        </TabsContent>
      </Tabs>

      {shopId ? (
        <CallDetailSheet
          shopId={shopId}
          callId={openCall}
          onOpenChange={(isOpen) => {
            if (!isOpen) setOpenCall(null)
          }}
        />
      ) : null}
    </div>
  )
}

function ListSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true">
      {[0, 1, 2].map((i) => (
        <Skeleton key={i} className="h-24 rounded-2xl" />
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}

function TaskList({
  shopId,
  loading,
  tasks,
  empty,
  onOpenCall,
}: {
  shopId: string | null
  loading: boolean
  tasks: TaskRead[]
  empty: React.ReactNode
  onOpenCall: (callId: string) => void
}) {
  const [closing, setClosing] = useState<TaskRead | null>(null)
  if (loading) return <ListSkeleton />
  if (tasks.length === 0) return <>{empty}</>
  return (
    <>
      <ul className="space-y-3">
        {tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            onOpenCall={onOpenCall}
            onMarkDone={() => setClosing(task)}
          />
        ))}
      </ul>
      {shopId ? (
        <MarkDoneDialog shopId={shopId} task={closing} onClose={() => setClosing(null)} />
      ) : null}
    </>
  )
}

function TaskRow({
  task,
  onOpenCall,
  onMarkDone,
}: {
  task: TaskRead
  onOpenCall: (callId: string) => void
  onMarkDone: () => void
}) {
  const kind = KIND[task.kind] ?? KIND.FOLLOW_UP!
  const Icon = kind.icon
  const done = task.status === 'DONE'
  const sentiment = task.summary ? SENTIMENT[task.summary.sentiment] : undefined

  return (
    <li>
      <Card className={cn('gap-0 py-0', task.is_urgent && !done && 'border-danger-ink/30')}>
        <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:p-6">
          <span
            aria-hidden="true"
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-xl',
              task.is_urgent && !done
                ? 'bg-danger-subtle text-danger-ink'
                : done
                  ? 'bg-success-subtle text-success-ink'
                  : 'bg-brand-blue-subtle text-brand-blue-ink',
            )}
          >
            <Icon className="size-5" />
          </span>

          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="neutral">{kind.label}</Badge>
              {task.is_urgent && !done ? <Badge variant="destructive">Urgent</Badge> : null}
              {sentiment ? <Badge variant={sentiment.variant}>{sentiment.label}</Badge> : null}
            </div>
            <h3 className="text-base font-semibold text-foreground">{task.title}</h3>
            <p className="text-sm text-muted-foreground">
              {task.customer ? (
                <span className="font-medium text-foreground">{task.customer.display_name}</span>
              ) : null}
              {task.booking_reference ? (
                <>
                  {' · '}
                  <span className="font-mono">{task.booking_reference}</span>
                </>
              ) : null}
              {' · '}
              <time dateTime={task.created_at} title={formatDateTime(task.created_at)}>
                {formatRelative(task.created_at)}
              </time>
            </p>
            {task.summary ? (
              <p className="text-sm text-helper">AI summary: {task.summary.intent}</p>
            ) : null}
            {task.description && !task.summary ? (
              <p className="text-sm text-muted-foreground">{task.description}</p>
            ) : null}
            {done ? (
              <p className="text-sm text-success-ink">
                Done{task.done_by ? ` by ${task.done_by.display_name}` : ''}
                {task.done_at ? ` · ${formatDateTime(task.done_at)}` : ''}
                {task.done_note ? ` — “${task.done_note}”` : ''}
              </p>
            ) : null}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2 sm:flex-col sm:items-stretch">
            {task.call_id ? (
              <Button variant="ghost" onClick={() => onOpenCall(task.call_id!)}>
                <Bot aria-hidden="true" />
                View summary
              </Button>
            ) : null}
            {!done ? (
              <Button variant="outline" onClick={onMarkDone}>
                <CheckCheck aria-hidden="true" />
                Mark as done
              </Button>
            ) : null}
          </div>
        </div>
      </Card>
    </li>
  )
}

function MarkDoneDialog({
  shopId,
  task,
  onClose,
}: {
  shopId: string
  task: TaskRead | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const mutation = useMutation({
    mutationFn: () => markTaskDone(shopId, task!.id, note.trim() || undefined),
    onSuccess: () => {
      toast.success('Task marked as done')
      void queryClient.invalidateQueries({ queryKey: ['calls', 'tasks'] })
      setNote('')
      onClose()
    },
    onError: () => toast.error('The task could not be updated. Please try again.'),
  })

  return (
    <Dialog
      open={Boolean(task)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Mark this task as done?</DialogTitle>
          <DialogDescription>{task?.title}</DialogDescription>
        </DialogHeader>
        <Field>
          <FieldLabel htmlFor="task-note">Note (optional)</FieldLabel>
          <Textarea
            id="task-note"
            maxLength={500}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="For example: called back, customer will approve the estimate today."
          />
        </Field>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? <Spinner /> : <CheckCheck aria-hidden="true" />}
            Mark as done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function CallLog({
  loading,
  calls,
  onOpenCall,
}: {
  loading: boolean
  calls: CallRead[]
  onOpenCall: (callId: string) => void
}) {
  if (loading) return <ListSkeleton />
  if (calls.length === 0) {
    return (
      <EmptyState
        tone="neutral"
        icon={PhoneCall}
        title="No calls yet"
        description="In-app calls between customers and your advisors appear here."
      />
    )
  }
  return (
    <Card className="gap-0 py-0">
      <ul className="divide-y divide-border-faint">
        {calls.map((call) => (
          <li key={call.id} className="flex items-center gap-3 px-5 py-3.5 sm:px-6">
            <span
              aria-hidden="true"
              className={cn(
                'flex size-9 shrink-0 items-center justify-center rounded-xl',
                call.status === 'MISSED' && !call.ai
                  ? 'bg-danger-subtle text-danger-ink'
                  : 'bg-brand-blue-subtle text-brand-blue-ink',
              )}
            >
              {call.ai ? (
                <Bot className="size-4" />
              ) : call.status === 'MISSED' ? (
                <PhoneMissed className="size-4" />
              ) : (
                <PhoneCall className="size-4" />
              )}
            </span>
            <div className="min-w-0 flex-1 space-y-0.5">
              <p className="truncate text-sm font-medium text-foreground">
                {call.direction === 'CUSTOMER_TO_SHOP'
                  ? `${call.caller.display_name} called`
                  : `${call.caller.display_name} called ${call.callee_label}`}
                {' · '}
                <span className="font-mono">{call.booking_reference}</span>
              </p>
              <p className="truncate text-xs text-helper">
                <time dateTime={call.started_at}>{formatDateTime(call.started_at)}</time> ·{' '}
                {outcomeOf(call)}
              </p>
            </div>
            {call.ai ? (
              <Button variant="ghost" size="sm" onClick={() => onOpenCall(call.id)}>
                Summary
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  )
}
