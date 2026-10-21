'use client'

import { RotateCcw, SearchX } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/layout/page-header'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import {
  getBookingById,
  getCurrentUser,
  getShopById,
  getTeamMembers,
  saveBooking,
  type MockBooking,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

import { InspectionForm } from './inspection-form'
import { InspectionReadOnly } from './inspection-result'
import {
  FALLBACK_INSPECTOR_ID,
  formatQcIssue,
  inShop,
  isInQc,
  isRetest,
  memberIdFor,
  memberName,
  pickedByOther,
  shopTimeZone,
  vehicleName,
  type QcResult,
} from './qc-data'
import { QcInspectionSkeleton } from './qc-skeletons'
import { NotFoundState, PlateTag } from './qc-ui'

/** How long the result shows before the inspector is taken back to the queue. */
const BACK_TO_QUEUE_MS = 1500

/**
 * QI-02 Inspection (spec 10): the job's header, what to check it against, and — for a QC
 * inspector while the job is in QC and not picked by someone else — the D46 checklist with Pass
 * QC and Fail QC. Otherwise the page is read-only: the QC result, another inspector's job, the
 * Owner's view (D16), or a job that is not in QC.
 */
export function QcInspection({ shopId, bookingId }: { shopId: string; bookingId: string }) {
  const router = useRouter()
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const booking = useMockStore(() => getBookingById(bookingId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const [justActed, setJustActed] = useState<QcResult | null>(null)

  const queueHref = `/pos/shops/${encodeURIComponent(shopId)}/qc`

  // After a pass or a fail the result shows briefly, then the queue opens (as it always has).
  // Leaving the page first cancels the timer.
  useEffect(() => {
    if (justActed === null) return
    const timer = window.setTimeout(() => router.push(queueHref), BACK_TO_QUEUE_MS)
    return () => window.clearTimeout(timer)
  }, [justActed, queueHref, router])

  if (!ready || nowIso === null) return <QcInspectionSkeleton />
  if (!booking || !inShop(booking, shopId)) {
    return (
      <NotFoundState
        icon={SearchX}
        title="We couldn't find that job"
        description="Check the link, or open the job from the QC queue."
        href={queueHref}
        action="Back to QC queue"
      />
    )
  }

  const now = new Date(nowIso)
  const timeZone = shopTimeZone(shop?.timezone)
  const readOnly = sectionAccess(user.role, 'qc') !== 'manage'
  const myId = readOnly ? undefined : (memberIdFor(user, team) ?? FALLBACK_INSPECTOR_ID)
  const canAct =
    !readOnly && justActed === null && isInQc(booking.status) && !pickedByOther(booking, myId)
  const technician = booking.assignedTechnicianName

  /** The booking as stored now, or null (with a toast) when it can no longer be passed or failed. */
  const latestInQc = (): MockBooking | null => {
    const latest = getBookingById(booking.id)
    if (latest && isInQc(latest.status) && !pickedByOther(latest, myId)) return latest
    toast.error(
      latest && pickedByOther(latest, myId)
        ? `${memberName(latest.qcInspectorId, team) ?? 'Another inspector'} is inspecting ${booking.reference} now`
        : `${booking.reference} is no longer waiting for QC`,
    )
    return null
  }

  /** Writes the result; false (with a toast) when the browser could not store it. */
  const save = (next: MockBooking): boolean => {
    saveBooking(next)
    if (getBookingById(next.id)?.status === next.status) return true
    toast.error(`${next.reference} could not be saved. Try again.`)
    return false
  }

  const handlePass = (notes: string): boolean => {
    const latest = latestInQc()
    if (!latest) return false
    if (!save({ ...latest, status: 'READY_FOR_PICKUP', qcPassed: true, qcNotes: notes })) {
      return false
    }
    setJustActed('passed')
    toast.success(`QC passed: ${latest.reference} is ready for pick-up`, {
      description: 'The service advisor has been notified.',
    })
    return true
  }

  const handleFail = (title: string, description: string): boolean => {
    const latest = latestInQc()
    if (!latest) return false
    const failed: MockBooking = {
      ...latest,
      status: 'IN_REPAIR',
      qcPassed: false,
      qcNotes: formatQcIssue(title, description),
    }
    if (!save(failed)) return false
    setJustActed('failed')
    toast.success(`Returned to ${technician ?? 'the technician'} with an issue`, {
      description: `${latest.reference}: ${title}`,
    })
    return true
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: queueHref, label: 'QC queue' }}
        eyebrow="QC inspection"
        title={<span className="font-mono">{booking.reference}</span>}
        badges={
          <>
            <StatusBadge status={booking.status} audience="staff" size="md" />
            {isRetest(booking) ? (
              <Badge variant="warning" className="h-7 px-3 text-sm">
                <RotateCcw aria-hidden="true" />
                Re-test
              </Badge>
            ) : null}
          </>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="font-semibold text-foreground">{vehicleName(booking)}</span>
            <PlateTag plate={booking.licensePlate} size="md" />
            {technician ? <span>Repaired by {technician}</span> : null}
          </span>
        }
      />

      {canAct ? (
        <InspectionForm
          key={booking.id}
          booking={booking}
          onPass={handlePass}
          onFail={handleFail}
        />
      ) : (
        <InspectionReadOnly
          booking={booking}
          team={team}
          now={now}
          timeZone={timeZone}
          readOnly={readOnly}
          myId={myId}
          justActed={justActed}
          queueHref={queueHref}
        />
      )}
    </div>
  )
}
