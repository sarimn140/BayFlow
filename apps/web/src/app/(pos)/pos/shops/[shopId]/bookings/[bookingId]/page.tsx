'use client'

import { useParams } from 'next/navigation'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { BookingCallsCard } from '@/features/calls/booking-calls-card'
import { CallButton } from '@/features/calls/call-button'
import {
  AssignMemberDialog,
  ConfirmActionDialog,
  NoteDialog,
  ReasonDialog,
  MEMBER_NOT_ELIGIBLE,
  type ActionError,
  type MemberOption,
} from '@/components/pos/sa-booking/action-dialogs'
import {
  buildActivity,
  historySince,
  lastEnteredAt,
  statusSteps,
} from '@/components/pos/sa-booking/activity'
import {
  ActivityCard,
  QualityCheckCard,
  RequestCard,
} from '@/components/pos/sa-booking/booking-sections'
import { CopyReferenceButton } from '@/components/pos/sa-booking/copy-reference-button'
import { EDIT_ESTIMATE_BUTTON_ID, EstimateCard } from '@/components/pos/sa-booking/estimate-card'
import { EstimateEditorSheet } from '@/components/pos/sa-booking/estimate-editor'
import { estimateTotals, sameItems } from '@/components/pos/sa-booking/estimate-math'
import { dateTimeText, describeNextStep, slotText } from '@/components/pos/sa-booking/next-step'
import {
  MobileActionBar,
  NextStepCard,
  type Fact,
} from '@/components/pos/sa-booking/next-step-card'
import { BookingDetailSkeleton, BookingNotFound } from '@/components/pos/sa-booking/page-states'
import { BookingDetailsCard, type Assignee } from '@/components/pos/sa-booking/people-cards'
import {
  planActionBar,
  saAllowedActions,
  type SaActionSlug,
} from '@/components/pos/sa-booking/sa-actions'
import {
  getSaRecord,
  lastReadyNotice,
  recordCancellation,
  recordEstimateEdit,
  recordEstimateRevised,
  recordEstimateSent,
  recordReadyNotice,
  recordReturnedToTechnician,
  type SaActor,
} from '@/components/pos/sa-booking/sa-records'
import { StatusBadge } from '@/components/status-badge'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { DEFAULT_SHOP_TZ, formatPKR } from '@/lib/format'
import {
  getBookingById,
  getBookings,
  getCurrentUser,
  getInventory,
  getServices,
  getShopById,
  getTeamMembers,
  saveBooking,
  type MockBooking,
  type MockEstimateItem,
  type MockTeamMember,
} from '@/lib/mock-data'
import { BOOKING_STATUS_META, statusPhase, type BookingStatus } from '@/lib/status'

/** The actions that open a dialog; `confirm` and `notify-ready` run at once, edits open a sheet. */
type DialogSlug = Exclude<SaActionSlug, 'confirm' | 'notify-ready' | 'edit-estimate'>

const MOVED_ON = 'This booking has moved on — we’ve refreshed it.'
const CONCURRENT_UPDATE: ActionError = {
  code: 'CONCURRENT_UPDATE',
  message:
    'Someone else just updated this booking. We’ve loaded the latest version — please check and try again.',
}

/** The booking belongs to the shop in the URL (E-35 is shop-scoped: another shop's is a 404). */
const inShop = (booking: MockBooking, shopId: string) =>
  booking.shopId === shopId || booking.shopSlug === shopId

/** SA-02 · Booking detail for the Service Advisor and the Owner (spec 10 SA-02, D16). */
export default function ServiceAdvisorBookingDetailPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'
  const bookingId = typeof params?.bookingId === 'string' ? params.bookingId : ''

  const ready = useMockStoreReady()
  const stored = useMockStore(() => getBookingById(bookingId))
  const record = useMockStore(() => getSaRecord(getBookingById(bookingId)?.id ?? bookingId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const shopBookings = useMockStore(() => getBookings(shopId))
  const services = useMockStore(() => getServices(shopId))
  const inventory = useMockStore(() => getInventory(shopId))
  const shop = useMockStore(() => getShopById(shopId))
  const user = useMockStore(getCurrentUser)

  /** The open dialog and the booking's `updatedAt` when it opened (`expected_version`, D30). */
  const [dialog, setDialog] = useState<{ slug: DialogSlug; version: string } | null>(null)
  const [editor, setEditor] = useState<{ open: boolean; version: string }>({
    open: false,
    version: '',
  })
  const headingRef = useRef<HTMLHeadingElement>(null)
  /** Where focus goes once a dialog has closed after an action (spec 09 §4.6 rule 4). */
  const afterDialog = useRef<'step' | 'editor' | null>(null)
  const editorBackToStep = useRef(false)

  const base = `/pos/shops/${encodeURIComponent(shopId)}`
  const booking = stored && inShop(stored, shopId) ? stored : undefined

  if (!ready) return <BookingDetailSkeleton />
  if (!booking) return <BookingNotFound backHref={`${base}/bookings`} />

  const timeZone = shop?.timezone ?? DEFAULT_SHOP_TZ
  const actor: SaActor = {
    name: user.name,
    role: user.role === 'OWNER' ? 'OWNER' : 'SERVICE_ADVISOR',
  }
  const memberById = (id?: string): MockTeamMember | undefined =>
    id ? team.find((member) => member.id === id) : undefined
  const technicianMember = memberById(booking.assignedTechnicianId)
  const partsMember = memberById(booking.assignedPartsPersonId)
  const qcMember = memberById(booking.qcInspectorId)
  const technician = booking.assignedTechnicianName ?? technicianMember?.name
  const partsPerson =
    partsMember?.name ?? (booking.assignedPartsPersonId ? 'Unknown member' : undefined)
  const qcInspector = qcMember?.name ?? (booking.qcInspectorId ? 'Unknown member' : undefined)

  const allowed = saAllowedActions(booking.status)
  const readyNotice = lastReadyNotice(record)
  const plan = planActionBar(allowed, { readyNotified: Boolean(readyNotice) })
  const cancellation = booking.status === 'CANCELLED' ? record.cancellation : undefined
  const step = describeNextStep(booking, {
    technician,
    partsPerson,
    qcInspector,
    estimateVersion: record.estimateVersion,
    saDraftOpen: record.saDraftOpen,
    readyNotified: Boolean(readyNotice),
    cancellation,
    timeZone,
  })
  const activity = buildActivity(booking, record, { technician, partsPerson })
  const steps = statusSteps(booking, record)
  const when = (status: BookingStatus) => {
    const at = lastEnteredAt(steps, status)
    return at ? dateTimeText(at, timeZone, ' at ') : undefined
  }
  const estimateTimes = {
    submitted: when('ESTIMATE_REVIEW'),
    sent: when('AWAITING_CUSTOMER'),
    approved: when('ESTIMATE_APPROVED'),
    declined: when('ESTIMATE_REJECTED'),
  }

  const facts: Fact[] = [{ label: 'Slot', value: slotText(booking) }]
  if (booking.estimateItems.length > 0) {
    facts.push({ label: 'Estimate', value: formatPKR(booking.estimateTotal) })
  }
  if (booking.paidAmount > 0) facts.push({ label: 'Paid', value: formatPKR(booking.paidAmount) })
  if (readyNotice) {
    facts.push({ label: 'Customer notified', value: dateTimeText(readyNotice.at, timeZone) })
  }
  if (booking.status === 'COMPLETED') {
    facts.push({ label: 'Completed', value: dateTimeText(booking.updatedAt, timeZone) })
  }

  const assignees: Assignee[] = [
    { role: 'Technician', name: technician, inactive: technicianMember?.is_active === false },
    { role: 'Parts person', name: partsPerson, inactive: partsMember?.is_active === false },
    { role: 'QC inspector', name: qcInspector, inactive: qcMember?.is_active === false },
  ]

  // Assign pickers: the shop's active members of the role, with their open jobs (E-25).
  const technicians: MemberOption[] = team
    .filter((member) => member.role === 'TECHNICIAN' && member.is_active)
    .map((member) => ({
      id: member.id,
      name: member.name,
      openJobs: shopBookings.filter(
        (b) => b.assignedTechnicianId === member.id && !BOOKING_STATUS_META[b.status].terminal,
      ).length,
    }))
  const partsPeople: MemberOption[] = team
    .filter((member) => member.role === 'PARTS_PERSON' && member.is_active)
    .map((member) => ({
      id: member.id,
      name: member.name,
      openJobs: shopBookings.filter(
        (b) => b.assignedPartsPersonId === member.id && statusPhase(b.status) === 'PARTS',
      ).length,
    }))

  const reference = booking.reference
  const customer = booking.customerName
  const vehicle = `${booking.vehicleMake} ${booking.vehicleModel}`
  const version = record.estimateVersion

  /* -------------------------------------------------------------------- actions ---------- */

  const focusNextStep = () => requestAnimationFrame(() => headingRef.current?.focus())

  const onDialogCloseAutoFocus = (event: Event) => {
    const next = afterDialog.current
    afterDialog.current = null
    if (!next) return
    event.preventDefault()
    if (next === 'editor') setEditor((current) => ({ ...current, open: true }))
    else headingRef.current?.focus()
  }

  // Back to "Edit estimate" (Safari never focused it on click), or to the next step after a
  // revision opened the editor.
  const onEditorCloseAutoFocus = (event: Event) => {
    event.preventDefault()
    const editButton = editorBackToStep.current
      ? null
      : document.getElementById(EDIT_ESTIMATE_BUTTON_ID)
    editorBackToStep.current = false
    ;(editButton ?? headingRef.current)?.focus()
  }

  /**
   * Runs `slug` on the latest stored booking, as the API would (spec 08): a booking that has moved
   * on refreshes and closes the dialog (`INVALID_TRANSITION`); one changed since the dialog opened
   * keeps the dialog and its input (`CONCURRENT_UPDATE`). `apply` returns the success toast.
   */
  const run = (
    slug: SaActionSlug,
    apply: (latest: MockBooking) => string,
    expectedVersion?: string,
  ): ActionError | null => {
    const latest = getBookingById(booking.id)
    if (!latest || !saAllowedActions(latest.status).includes(slug)) {
      afterDialog.current = 'step'
      setDialog(null)
      setEditor((current) => ({ ...current, open: false }))
      toast.error(MOVED_ON)
      return null
    }
    if (expectedVersion !== undefined && latest.updatedAt !== expectedVersion) {
      setDialog((current) => current && { ...current, version: latest.updatedAt })
      return CONCURRENT_UPDATE
    }
    toast.success(apply(latest))
    afterDialog.current = 'step'
    setDialog(null)
    return null
  }

  const onAction = (slug: SaActionSlug) => {
    switch (slug) {
      case 'confirm':
        run('confirm', (latest) => {
          saveBooking({ ...latest, status: 'CONFIRMED' })
          return `${latest.reference} confirmed`
        })
        afterDialog.current = null
        focusNextStep()
        return
      case 'notify-ready':
        run('notify-ready', (latest) => {
          recordReadyNotice(latest.id, actor)
          return `Pick-up notice sent to ${latest.customerName}`
        })
        afterDialog.current = null
        focusNextStep()
        return
      case 'edit-estimate':
        setEditor({ open: true, version: booking.updatedAt })
        return
      default:
        setDialog({ slug, version: booking.updatedAt })
    }
  }

  const expected = dialog?.version

  const assign = (role: 'TECHNICIAN' | 'PARTS_PERSON', memberId: string): ActionError | null => {
    const member = getTeamMembers(shopId).find(
      (candidate) => candidate.id === memberId && candidate.role === role && candidate.is_active,
    )
    if (!member) return MEMBER_NOT_ELIGIBLE
    return role === 'TECHNICIAN'
      ? run(
          'assign-technician',
          (latest) => {
            saveBooking({
              ...latest,
              status: 'ASSIGNED',
              assignedTechnicianId: member.id,
              assignedTechnicianName: member.name,
            })
            return `${member.name} assigned to ${latest.reference}`
          },
          expected,
        )
      : run(
          'assign-parts-person',
          (latest) => {
            saveBooking({ ...latest, status: 'PARTS_PENDING', assignedPartsPersonId: member.id })
            return `${member.name} assigned to ${latest.reference}`
          },
          expected,
        )
  }

  const sendEstimate = (): ActionError | null => {
    const latest = getBookingById(booking.id)
    if (latest?.status === 'ESTIMATE_REVIEW' && latest.estimateItems.length === 0) {
      return { code: 'ESTIMATE_EMPTY', message: 'Add at least one part or labour line first.' }
    }
    return run(
      'send-estimate',
      (current) => {
        const sent = getSaRecord(current.id).estimateVersion
        recordEstimateSent(current.id)
        saveBooking({ ...current, status: 'AWAITING_CUSTOMER' })
        return `Estimate v${sent} sent to ${current.customerName}`
      },
      expected,
    )
  }

  const endBooking = (kind: 'decline' | 'cancel', reason: string): ActionError | null =>
    run(
      kind,
      (latest) => {
        recordCancellation(latest.id, actor, {
          kind,
          reason,
          fromStatus: latest.status,
          previousUpdatedAt: latest.updatedAt,
        })
        saveBooking({ ...latest, status: 'CANCELLED' })
        return `${latest.reference} ${kind === 'decline' ? 'declined' : 'cancelled'}`
      },
      expected,
    )

  const reviseEstimate = (): ActionError | null => {
    let revisedAt = ''
    const error = run(
      'revise-estimate',
      (latest) => {
        const history = historySince(latest, getSaRecord(latest.id).loops ?? [])
        const draft = recordEstimateRevised(latest.id, actor, history).estimateVersion
        const next: MockBooking = { ...latest, status: 'ESTIMATE_REVIEW' }
        saveBooking(next)
        revisedAt = next.updatedAt
        return `Draft v${draft} created`
      },
      expected,
    )
    if (!error && revisedAt) {
      // Spec 09 §4.6: "Then opens the editor" — once the dialog has closed.
      afterDialog.current = 'editor'
      editorBackToStep.current = true
      setEditor({ open: false, version: revisedAt })
    }
    return error
  }

  const returnToTechnician = (note: string): ActionError | null =>
    run(
      'return-to-technician',
      (latest) => {
        const history = historySince(latest, getSaRecord(latest.id).loops ?? [])
        recordReturnedToTechnician(latest.id, actor, note, history)
        saveBooking({ ...latest, status: 'INSPECTING' })
        return `Returned to ${latest.assignedTechnicianName ?? 'the technician'}`
      },
      expected,
    )

  const complete = (): ActionError | null =>
    run(
      'complete',
      (latest) => {
        saveBooking({ ...latest, status: 'COMPLETED', paidAmount: latest.estimateTotal })
        return `${latest.reference} completed`
      },
      expected,
    )

  const saveEstimate = (items: MockEstimateItem[]): ActionError | null => {
    const latest = getBookingById(booking.id)
    if (!latest || !saAllowedActions(latest.status).includes('edit-estimate')) {
      setEditor((current) => ({ ...current, open: false }))
      toast.error('This estimate can’t be edited any more.')
      return null
    }
    if (latest.updatedAt !== editor.version) {
      setEditor((current) => ({ ...current, version: latest.updatedAt }))
      return CONCURRENT_UPDATE
    }
    setEditor((current) => ({ ...current, open: false }))
    if (sameItems(items, latest.estimateItems)) {
      toast('No changes to save')
      return null
    }
    const saved = recordEstimateEdit(latest.id, actor).estimateVersion
    saveBooking({ ...latest, estimateItems: items, estimateTotal: estimateTotals(items).total })
    toast.success(`Estimate saved (v${saved})`)
    return null
  }

  const closeDialog = (open: boolean) => {
    if (!open) setDialog(null)
  }
  const openSlug = dialog?.slug

  /* -------------------------------------------------------------------- page ------------- */

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: `${base}/bookings`, label: 'Bookings' }}
        title={<span className="font-mono tracking-tight">{reference}</span>}
        badges={
          <>
            <CopyReferenceButton reference={reference} />
            <StatusBadge status={booking.status} audience="staff" size="md" />
          </>
        }
        description={
          <>
            {customer} · {booking.vehicleYear} {vehicle} ·{' '}
            <span className="font-mono whitespace-nowrap">{booking.licensePlate}</span>
          </>
        }
        actions={
          // In-app call to the booking's customer (spec 05 §9.2), SA and Owner only (D21).
          <CallButton
            target={{ audience: 'staff', reference, shopSlug: booking.shopSlug }}
            counterpart={customer}
            label="Call customer"
          />
        }
      />

      <DetailLayout
        aside={
          <>
            <NextStepCard
              status={booking.status}
              step={step}
              plan={plan}
              onAction={onAction}
              facts={facts}
              headingRef={headingRef}
              note={
                cancellation ? (
                  <blockquote className="rounded-xl bg-layer px-4 py-3 text-sm text-foreground">
                    “{cancellation.reason}”
                  </blockquote>
                ) : undefined
              }
            />
            <BookingDetailsCard booking={booking} assignees={assignees} />
          </>
        }
      >
        <RequestCard booking={booking} services={services} timeZone={timeZone} />
        <EstimateCard
          booking={booking}
          version={version}
          technician={technician}
          saDraftOpen={record.saDraftOpen}
          times={estimateTimes}
          onEdit={allowed.includes('edit-estimate') ? () => onAction('edit-estimate') : undefined}
        />
        {booking.qcPassed !== undefined || booking.qcNotes ? (
          <QualityCheckCard
            passed={booking.qcPassed}
            notes={booking.qcNotes}
            inspector={qcInspector}
          />
        ) : null}
        <ActivityCard entries={activity} timeZone={timeZone} />
        <BookingCallsCard
          target={{ audience: 'staff', reference, shopSlug: booking.shopSlug }}
          summaryHrefBase={base}
        />
      </DetailLayout>

      <MobileActionBar plan={plan} onAction={onAction} />

      <AssignMemberDialog
        open={openSlug === 'assign-technician'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Assign a technician to ${reference}`}
        description={
          <>
            Choose who inspects {customer}&apos;s {vehicle} (
            <span className="font-mono whitespace-nowrap">{booking.licensePlate}</span>). The job
            appears in their queue straight away.
          </>
        }
        groupLabel="Technicians"
        members={technicians}
        defaultMemberId="usr-imran"
        emptyMessage="This shop has no active technicians. The Owner can add one in Team."
        onConfirm={(memberId) => assign('TECHNICIAN', memberId)}
      />
      <AssignMemberDialog
        open={openSlug === 'assign-parts-person'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Assign a parts person to ${reference}`}
        description="They check stock for the approved parts, order anything missing and reserve the rest for this job."
        groupLabel="Parts people"
        members={partsPeople}
        defaultMemberId="usr-usman"
        emptyMessage="This shop has no active parts people. The Owner can add one in Team."
        onConfirm={(memberId) => assign('PARTS_PERSON', memberId)}
      />
      <ConfirmActionDialog
        open={openSlug === 'send-estimate'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Send estimate v${version} for ${reference}?`}
        description={`${customer} is notified and can approve or decline it from their bookings.`}
        confirmLabel="Send to customer"
        onConfirm={sendEstimate}
      >
        <dl className="space-y-1.5 rounded-xl bg-layer p-4 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">Customer</dt>
            <dd className="min-w-0 text-right text-foreground">
              {customer}
              <span className="block text-xs break-all text-helper">{booking.customerEmail}</span>
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">Lines</dt>
            <dd className="text-foreground tabular-nums">{booking.estimateItems.length}</dd>
          </div>
          <div className="mt-3 flex items-baseline justify-between gap-4 border-t border-border pt-3">
            <dt className="font-semibold text-foreground">Grand total</dt>
            <dd className="text-lg font-bold text-foreground tabular-nums">
              {formatPKR(booking.estimateTotal)}
            </dd>
          </div>
        </dl>
      </ConfirmActionDialog>
      <ConfirmActionDialog
        open={openSlug === 'revise-estimate'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Revise the estimate for ${reference}?`}
        description={`A new draft (v${version + 1}) is made from the declined estimate, and the editor opens so you can change it before you send it again.`}
        confirmLabel="Revise estimate"
        onConfirm={reviseEstimate}
      />
      <NoteDialog
        open={openSlug === 'return-to-technician'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Return ${reference} to ${technician ?? 'the technician'}?`}
        description={`${technician ?? 'The technician'} gets a new draft (v${version + 1}) made from the declined estimate, re-inspects the car and submits it again.`}
        noteLabel={`Note for ${technician ?? 'the technician'} (optional)`}
        placeholder="e.g. The customer wants to skip the AC service"
        confirmLabel={`Return to ${technician ?? 'technician'}`}
        onConfirm={returnToTechnician}
      />
      <ConfirmActionDialog
        open={openSlug === 'complete'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Complete ${reference}?`}
        description={`Confirm that ${customer} has collected the ${vehicle}. The booking closes and ${formatPKR(booking.estimateTotal)} is recorded as paid.`}
        confirmLabel="Complete booking"
        onConfirm={complete}
      />
      <ReasonDialog
        open={openSlug === 'decline'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Decline booking ${reference}?`}
        description={`${customer} is told the booking was declined, with your reason, and the slot is freed.`}
        reasonLabel="Reason for the customer"
        placeholder="e.g. We can't take the car in that day. Please book another slot."
        confirmLabel="Decline booking"
        keepLabel="Keep booking"
        onConfirm={(reason) => endBooking('decline', reason)}
      />
      <ReasonDialog
        open={openSlug === 'cancel'}
        onOpenChange={closeDialog}
        onCloseAutoFocus={onDialogCloseAutoFocus}
        title={`Cancel booking ${reference}?`}
        description={`${customer} is told the booking was cancelled, with your reason. Reserved parts go back to stock and the slot is freed.`}
        reasonLabel="Reason for the customer"
        placeholder="e.g. The customer called to cancel."
        confirmLabel="Cancel booking"
        keepLabel="Keep booking"
        onConfirm={(reason) => endBooking('cancel', reason)}
      />

      <EstimateEditorSheet
        open={editor.open}
        onOpenChange={(open) => setEditor((current) => ({ ...current, open }))}
        onCloseAutoFocus={onEditorCloseAutoFocus}
        booking={booking}
        version={version}
        saDraftOpen={record.saDraftOpen}
        technician={technician}
        inventory={inventory}
        onSave={saveEstimate}
      />
    </div>
  )
}
