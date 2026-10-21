'use client'

import { CheckCheck, ChevronDown, ClipboardList, Eye, History, Store } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import {
  getBookingById,
  getBookings,
  getCurrentUser,
  getShopById,
  getTeamMembers,
  saveBooking,
  type MockBooking,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'
import { cn } from '@/lib/utils'

import {
  FALLBACK_INSPECTOR_ID,
  inProgressJobs,
  memberIdFor,
  memberName,
  pickedByOther,
  recentlyInspected,
  shopTimeZone,
  waitingJobs,
} from './qc-data'
import { QcQueueSkeleton } from './qc-skeletons'
import { CardHeading, NotFoundState } from './qc-ui'
import { InProgressRow, InspectedRow, WaitingRow } from './queue-rows'

const continueId = (bookingId: string) => `qc-continue-${bookingId}`

function CountBadge({ count, noun }: { count: number; noun: string }) {
  return (
    <Badge variant="secondary" className="tabular-nums">
      {count}
      <span className="sr-only"> {count === 1 ? noun : `${noun}s`}</span>
    </Badge>
  )
}

/**
 * QI-01 QC queue (spec 10), shared by the shop's QC inspectors: cars waiting for their final
 * check (oldest first, "Pick job" locks one to you), inspections in progress (yours first) and
 * the jobs that recently passed or failed QC. The Owner sees the same queue read-only (D16).
 */
export function QcQueue({ shopId }: { shopId: string }) {
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const bookings = useMockStore(() => getBookings(shopId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const [recentOpen, setRecentOpen] = useState(false)

  if (!ready || nowIso === null) return <QcQueueSkeleton />
  if (!shop) {
    return (
      <NotFoundState
        icon={Store}
        title="We couldn't find that shop"
        description="Check the link, or open one of your shops from the workshop hub."
        href="/pos"
        action="Go to my shops"
      />
    )
  }

  const base = `/pos/shops/${encodeURIComponent(shopId)}`
  const inspectHref = (booking: MockBooking) => `${base}/qc/${encodeURIComponent(booking.id)}`
  const now = new Date(nowIso)
  const timeZone = shopTimeZone(shop.timezone)
  const readOnly = sectionAccess(user.role, 'qc') !== 'manage'
  const myId = readOnly ? undefined : (memberIdFor(user, team) ?? FALLBACK_INSPECTOR_ID)

  const waiting = waitingJobs(bookings)
  const inProgress = inProgressJobs(bookings, myId)
  const recent = recentlyInspected(bookings)
  const continuable = readOnly ? [] : inProgress.filter((b) => !pickedByOther(b, myId))
  // One primary per view (R7): finish your own inspection first, else pick the oldest car.
  const primaryId = readOnly ? null : (continuable[0]?.id ?? waiting[0]?.id ?? null)

  // The picked row moves to "In progress": keep keyboard focus on it.
  const focusContinue = (bookingId: string) =>
    requestAnimationFrame(() => document.getElementById(continueId(bookingId))?.focus())

  const handlePick = (booking: MockBooking) => {
    // First to pick locks it (SM-06): re-read, so a pick from another tab is never overwritten.
    const latest = getBookingById(booking.id)
    if (latest?.status === 'QC_IN_PROGRESS' && latest.qcInspectorId === myId) {
      focusContinue(latest.id) // you already picked it (in another tab)
      return
    }
    if (!latest || latest.status !== 'QC_PENDING') {
      const picker = memberName(latest?.qcInspectorId, team)
      toast.error(
        latest?.status === 'QC_IN_PROGRESS'
          ? `${picker ?? 'Another inspector'} picked this job first`
          : `${booking.reference} is no longer waiting for QC`,
      )
      return
    }
    saveBooking({
      ...latest,
      status: 'QC_IN_PROGRESS',
      qcInspectorId: myId ?? FALLBACK_INSPECTOR_ID,
    })
    if (getBookingById(latest.id)?.status !== 'QC_IN_PROGRESS') {
      toast.error(`${latest.reference} could not be saved. Try again.`)
      return
    }
    toast.success(`You're inspecting ${latest.reference}`)
    focusContinue(latest.id)
  }

  return (
    <div className="@container/qc space-y-6">
      <PageHeader
        eyebrow="Quality control"
        title="QC queue"
        description={
          readOnly
            ? 'Repaired cars waiting for their final check before hand-over, and the inspections under way.'
            : 'Repaired cars waiting for their final check before hand-over. Pick a job to lock it to you, then work through the checklist.'
        }
      />

      {readOnly ? (
        <Alert variant="info" role="note">
          <Eye aria-hidden="true" />
          <AlertTitle>Read-only view</AlertTitle>
          <AlertDescription>
            QC inspectors pick, pass and fail jobs. You can follow the queue and open any job.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid items-start gap-6 @4xl/qc:grid-cols-2">
        <Card className="@container/queue gap-0 py-0">
          <CardHeader className="border-b pt-(--card-spacing)">
            <CardHeading id="qc-waiting">
              Waiting for inspection
              <CountBadge count={waiting.length} noun="car" />
            </CardHeading>
            <CardDescription>
              Oldest first. The first inspector to pick a job locks it.
            </CardDescription>
          </CardHeader>
          {waiting.length === 0 ? (
            <EmptyState
              variant="inline"
              tone="success"
              icon={CheckCheck}
              title="No cars waiting for a quality check"
              description={
                readOnly
                  ? 'Cars show up here when a technician sends them to QC.'
                  : "You'll be notified when a technician sends one."
              }
              className="p-6 sm:p-8"
            />
          ) : (
            <ul className="divide-y divide-border-faint" aria-labelledby="qc-waiting">
              {waiting.map((booking) => (
                <WaitingRow
                  key={booking.id}
                  booking={booking}
                  href={inspectHref(booking)}
                  now={now}
                  primary={booking.id === primaryId}
                  readOnly={readOnly}
                  onPick={handlePick}
                />
              ))}
            </ul>
          )}
        </Card>

        <Card className="@container/queue gap-0 py-0">
          <CardHeader className="border-b pt-(--card-spacing)">
            <CardHeading id="qc-in-progress">
              In progress
              <CountBadge count={inProgress.length} noun="inspection" />
            </CardHeading>
            <CardDescription>
              {readOnly
                ? 'Jobs a QC inspector has picked and is checking now.'
                : 'Your inspections first. Only the inspector who picked a job can pass or fail it.'}
            </CardDescription>
          </CardHeader>
          {inProgress.length === 0 ? (
            <EmptyState
              variant="inline"
              tone="neutral"
              icon={ClipboardList}
              title="No inspections in progress"
              description="A picked job stays here until it passes or fails QC."
              className="p-6 sm:p-8"
            />
          ) : (
            <ul className="divide-y divide-border-faint" aria-labelledby="qc-in-progress">
              {inProgress.map((booking) => {
                const mine = myId !== undefined && booking.qcInspectorId === myId
                return (
                  <InProgressRow
                    key={booking.id}
                    booking={booking}
                    href={inspectHref(booking)}
                    now={now}
                    timeZone={timeZone}
                    canContinue={!readOnly && !pickedByOther(booking, myId)}
                    mine={mine}
                    inspectorName={memberName(booking.qcInspectorId, team)}
                    primary={booking.id === primaryId}
                    readOnly={readOnly}
                    continueId={continueId(booking.id)}
                  />
                )
              })}
            </ul>
          )}
        </Card>
      </div>

      <Collapsible open={recentOpen} onOpenChange={setRecentOpen} asChild>
        <Card className="gap-0 py-0">
          <CardHeader className={cn('py-(--card-spacing)', recentOpen && 'border-b')}>
            <CardHeading id="qc-recent">
              Recently inspected
              <CountBadge count={recent.length} noun="job" />
            </CardHeading>
            <CardDescription>
              The latest jobs that passed or failed QC, newest first.
            </CardDescription>
            <CardAction>
              <CollapsibleTrigger asChild>
                <Button variant="ghost">
                  {recentOpen ? 'Hide' : 'Show'}
                  <span className="sr-only"> recently inspected jobs</span>
                  <ChevronDown
                    aria-hidden="true"
                    className={cn('transition-transform duration-150', recentOpen && 'rotate-180')}
                  />
                </Button>
              </CollapsibleTrigger>
            </CardAction>
          </CardHeader>
          <CollapsibleContent>
            {recent.length === 0 ? (
              <EmptyState
                variant="inline"
                tone="neutral"
                icon={History}
                title="No inspections yet"
                description="Jobs that pass or fail QC are listed here."
                className="p-6 sm:p-8"
              />
            ) : (
              <ul className="divide-y divide-border-faint" aria-labelledby="qc-recent">
                {recent.map((booking) => (
                  <InspectedRow
                    key={booking.id}
                    booking={booking}
                    href={inspectHref(booking)}
                    now={now}
                    inspectorName={memberName(booking.qcInspectorId, team)}
                  />
                ))}
              </ul>
            )}
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </div>
  )
}
