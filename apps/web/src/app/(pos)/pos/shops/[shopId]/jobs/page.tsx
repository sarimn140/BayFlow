'use client'

import { CheckCheck, ChevronDown, SearchX, Wrench } from 'lucide-react'
import { useParams } from 'next/navigation'
import { useState } from 'react'
import { flushSync } from 'react-dom'
import { toast } from 'sonner'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { JobCard, JobRow, jobActionSelector } from '@/components/pos/technician/job-card'
import {
  ACTION_GROUPS,
  countLabel,
  groupJobs,
  isOwnJob,
  JOB_GROUP_META,
  ownTechnicianMember,
  vehicleLabel,
  type JobGroup,
} from '@/components/pos/technician/job-model'
import { JobsSkeleton } from '@/components/pos/technician/job-skeletons'
import { GroupHeading, ReadOnlyBanner } from '@/components/pos/technician/job-ui'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import {
  getBookings,
  getCurrentUser,
  getTeamMembers,
  saveBooking,
  type MockBooking,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'
import { cn } from '@/lib/utils'

function headingId(group: JobGroup) {
  return `jobs-${group}`
}

/**
 * T-01 My jobs (spec 10): the technician's jobs grouped by what they need now — QC sent back,
 * to inspect, inspecting, repair — then the jobs waiting on others and the finished ones. The
 * Owner opens it as the read-only "Technician jobs" role view (D16).
 */
export default function TechnicianJobsPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'

  const ready = useMockStoreReady()
  const allBookings = useMockStore(() => getBookings(shopId))
  const user = useMockStore(getCurrentUser)
  const team = useMockStore(() => getTeamMembers(shopId))
  const [technicianFilter, setTechnicianFilter] = useState('all')
  const [doneOpen, setDoneOpen] = useState(false)
  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  // The seed data stands in for this browser's jobs until they load (no flash of stale cards).
  if (!ready) return <JobsSkeleton />

  const readOnly = sectionAccess(user.role, 'jobs') === 'read'
  const technicians = team.filter((member) => member.role === 'TECHNICIAN')
  const filtering = readOnly && technicianFilter !== 'all'
  // D21: a technician sees only the jobs assigned to them; the Owner's role view (D16) sees every
  // technician's, optionally narrowed to one.
  const self = readOnly ? undefined : ownTechnicianMember(team, user.email)
  const groups = groupJobs(
    readOnly
      ? filtering
        ? allBookings.filter((b) => b.assignedTechnicianId === technicianFilter)
        : allBookings
      : allBookings.filter((b) => isOwnJob(b, self)),
  )
  const needsYou = ACTION_GROUPS.reduce((count, group) => count + groups[group].length, 0)
  const total = needsYou + groups.waiting.length + groups.done.length

  const jobHref = (booking: MockBooking) => `${base}/jobs/${booking.id}`
  const showTechnician = (booking: MockBooking) =>
    readOnly ||
    (booking.assignedTechnicianName !== undefined && booking.assignedTechnicianName !== user.name)

  // The job moves to another group (or its button becomes a link), so the clicked control is
  // gone: save, let React render the move right away, then put focus on the job's new control.
  const saveAndFollow = (updated: MockBooking) => {
    flushSync(() => saveBooking(updated))
    document.querySelector<HTMLElement>(jobActionSelector(updated.id))?.focus()
  }

  const handleStartInspection = (booking: MockBooking) => {
    const updated: MockBooking = {
      ...booking,
      status: 'INSPECTING',
    }
    saveAndFollow(updated)
    toast.success('Inspection started', {
      description: `${booking.reference} · ${vehicleLabel(booking)}`,
    })
  }

  const handleStartRepair = (booking: MockBooking) => {
    const updated: MockBooking = {
      ...booking,
      status: 'IN_REPAIR',
    }
    saveAndFollow(updated)
    toast.success('Repair started', {
      description: `${booking.reference} · ${vehicleLabel(booking)}`,
    })
  }

  const summary = readOnly
    ? 'Every technician’s jobs, grouped by what happens next.'
    : needsYou > 0
      ? `${countLabel(needsYou, 'job needs', 'jobs need')} you now${
          groups.waiting.length > 0 ? `, ${groups.waiting.length} waiting on others` : ''
        }.`
      : 'Inspections, estimates and repairs assigned to you.'

  const filterName = technicians.find((t) => t.id === technicianFilter)?.name

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow={readOnly ? 'Role view' : 'Technician'}
        title={readOnly ? 'Technician jobs' : 'My jobs'}
        description={summary}
      />

      {readOnly ? (
        <div className="space-y-4">
          <ReadOnlyBanner href={`${base}/bookings`} scope="list" />
          {technicians.length > 1 ? (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
              <span id="technician-filter" className="text-sm font-medium text-foreground">
                Technician
              </span>
              <ToggleGroup
                type="single"
                variant="outline"
                size="lg"
                value={technicianFilter}
                onValueChange={(value) => setTechnicianFilter(value || 'all')}
                aria-labelledby="technician-filter"
                className="flex-wrap"
              >
                <ToggleGroupItem value="all">All technicians</ToggleGroupItem>
                {technicians.map((member) => (
                  <ToggleGroupItem key={member.id} value={member.id}>
                    {member.name}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </div>
          ) : null}
        </div>
      ) : null}

      {total === 0 ? (
        filtering ? (
          <EmptyState
            icon={SearchX}
            title={`No jobs for ${filterName ?? 'this technician'}`}
            description="Choose another technician, or show everyone’s jobs."
            action={
              <Button variant="outline" size="lg" onClick={() => setTechnicianFilter('all')}>
                Show all technicians
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={Wrench}
            title="No jobs assigned yet"
            description={
              readOnly
                ? 'Jobs appear here as soon as the service advisor assigns a technician.'
                : 'New assignments appear here as soon as the service advisor assigns you.'
            }
          />
        )
      ) : (
        <>
          {needsYou === 0 ? (
            <EmptyState
              tone="success"
              icon={CheckCheck}
              title={readOnly ? 'No jobs need a technician now' : 'You’re all caught up'}
              description={`Nothing needs ${readOnly ? 'a technician' : 'you'} right now. The jobs below are waiting on others or done.`}
            />
          ) : null}

          {ACTION_GROUPS.map((group) =>
            groups[group].length > 0 ? (
              <section key={group} aria-labelledby={headingId(group)} className="space-y-4">
                <GroupHeading
                  id={headingId(group)}
                  {...JOB_GROUP_META[group]}
                  count={groups[group].length}
                />
                <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,26rem),1fr))] gap-4">
                  {groups[group].map((booking) => (
                    <li key={booking.id}>
                      <JobCard
                        booking={booking}
                        href={jobHref(booking)}
                        showTechnician={showTechnician(booking)}
                        readOnly={readOnly}
                        onStartInspection={handleStartInspection}
                        onStartRepair={handleStartRepair}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null,
          )}

          {groups.waiting.length > 0 ? (
            <section aria-labelledby={headingId('waiting')} className="space-y-4">
              <GroupHeading
                id={headingId('waiting')}
                {...JOB_GROUP_META.waiting}
                count={groups.waiting.length}
              />
              <Card className="gap-0 py-0">
                <ul className="divide-y divide-border-faint">
                  {groups.waiting.map((booking) => (
                    <JobRow
                      key={booking.id}
                      booking={booking}
                      href={jobHref(booking)}
                      showTechnician={showTechnician(booking)}
                    />
                  ))}
                </ul>
              </Card>
            </section>
          ) : null}

          {groups.done.length > 0 ? (
            <Collapsible open={doneOpen} onOpenChange={setDoneOpen}>
              <section aria-labelledby={headingId('done')} className="space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <GroupHeading
                    id={headingId('done')}
                    {...JOB_GROUP_META.done}
                    count={groups.done.length}
                  />
                  <CollapsibleTrigger asChild>
                    <Button variant="outline" size="lg">
                      {doneOpen ? 'Hide' : 'Show'}
                      <span className="sr-only"> done jobs</span>
                      <ChevronDown
                        aria-hidden="true"
                        data-icon="inline-end"
                        className={cn(
                          'transition-transform duration-150',
                          doneOpen && 'rotate-180',
                        )}
                      />
                    </Button>
                  </CollapsibleTrigger>
                </div>
                <CollapsibleContent>
                  <Card className="gap-0 py-0">
                    <ul className="divide-y divide-border-faint">
                      {groups.done.map((booking) => (
                        <JobRow
                          key={booking.id}
                          booking={booking}
                          href={jobHref(booking)}
                          showTechnician={showTechnician(booking)}
                        />
                      ))}
                    </ul>
                  </Card>
                </CollapsibleContent>
              </section>
            </Collapsible>
          ) : null}
        </>
      )}
    </div>
  )
}
