'use client'

import { CalendarDays, ListFilter, X, type LucideIcon } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'

import { TableSearch } from '@/components/layout/data-table-card'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  BOOKING_STATUS_META,
  STATUS_PHASES,
  STATUS_PHASE_LABELS,
  isBookingStatus,
  statusesInPhase,
  type BookingStatus,
} from '@/lib/status'
import { cn } from '@/lib/utils'

import {
  DATE_RANGES,
  DATE_RANGE_LABELS,
  PRESET_LABELS,
  QUEUE_PRESETS,
  type DateRange,
  type QueueCounts,
  type QueueFilters,
  type QueuePreset,
} from './queue-model'

const ANY_STATUS = 'any'

/** A filter in use takes the toggle's "on" look: blue tint, blue ink (DESIGN.md "Toolbar"). */
const ACTIVE_PILL =
  'data-[active=true]:border-brand-blue/25 data-[active=true]:bg-brand-blue-subtle data-[active=true]:text-brand-blue-ink'

/**
 * A filter menu as a pill. Once a value is picked it reads "Status: Estimate review" and grows a
 * ✕ that removes the filter in one click.
 */
function FilterPill({
  icon: Icon,
  label,
  active,
  removeLabel,
  onRemove,
  children,
}: {
  icon: LucideIcon
  label: ReactNode
  active: boolean
  removeLabel: string
  onRemove: () => void
  /** The `DropdownMenuContent`. */
  children: ReactNode
}) {
  return (
    <div className="flex min-w-0 max-sm:grow">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            data-active={active}
            className={cn('min-w-0 flex-1', ACTIVE_PILL, active && 'rounded-r-none pr-3')}
          >
            <Icon aria-hidden="true" />
            <span className="truncate">{label}</span>
          </Button>
        </DropdownMenuTrigger>
        {children}
      </DropdownMenu>
      {active ? (
        <Button
          variant="outline"
          size="sm"
          data-active
          aria-label={removeLabel}
          onClick={onRemove}
          className={cn('rounded-l-none border-l-0 px-2.5', ACTIVE_PILL)}
        >
          <X aria-hidden="true" />
        </Button>
      ) : null}
    </div>
  )
}

export interface QueueToolbarProps {
  filters: QueueFilters
  counts: QueueCounts
  /** How many bookings the current view and filters show. */
  matching: number
  onPreset: (preset: QueuePreset) => void
  onQuery: (query: string) => void
  onStatus: (status: BookingStatus | null) => void
  onDate: (date: DateRange) => void
}

/**
 * The queue's filter bar (spec 09 §4.7, spec 10 SA-01): the three presets with their counts,
 * search, a status filter grouped by phase with counts, the slot day and the result count. Each
 * filter in use removes itself (its ✕); "Clear filters" sits in the no-match state.
 */
export function QueueToolbar({
  filters,
  counts,
  matching,
  onPreset,
  onQuery,
  onStatus,
  onDate,
}: QueueToolbarProps) {
  return (
    <>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        spacing={1.5}
        value={filters.preset}
        // Picking the pressed pill again sends '': keep the view, drop a status filter.
        onValueChange={(value) =>
          onPreset(QUEUE_PRESETS.find((preset) => preset === value) ?? filters.preset)
        }
        aria-label="Queue"
        // Three pills just fit a 390px phone; bigger counts wrap instead of overflowing the card.
        className="flex-wrap"
      >
        {QUEUE_PRESETS.map((preset) => (
          <ToggleGroupItem key={preset} value={preset} className="max-sm:gap-1 max-sm:px-2.5">
            {/* The space keeps the name "Needs action 2" for screen readers; flex hides it. */}
            {PRESET_LABELS[preset]}{' '}
            <span
              className={cn(
                'min-w-5 rounded-full px-1.5 text-xs leading-5 font-semibold tabular-nums max-sm:min-w-4 max-sm:px-1',
                preset === 'needs_action' && counts.presets[preset] > 0
                  ? 'bg-attention text-cta'
                  : 'bg-secondary text-muted-foreground group-data-[state=on]/toggle:bg-card group-data-[state=on]/toggle:text-brand-blue-ink',
              )}
            >
              {counts.presets[preset]}
            </span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <TableSearch
        value={filters.query}
        onValueChange={onQuery}
        label="Search bookings by reference, plate or customer"
        placeholder="Reference, plate or customer"
        className="sm:w-60"
      />

      <div className="flex flex-wrap gap-2">
        <FilterPill
          icon={ListFilter}
          active={filters.status !== null}
          label={
            filters.status ? `Status: ${BOOKING_STATUS_META[filters.status].staffLabel}` : 'Status'
          }
          removeLabel="Remove status filter"
          onRemove={() => onStatus(null)}
        >
          <DropdownMenuContent className="w-64">
            <DropdownMenuRadioGroup
              value={filters.status ?? ANY_STATUS}
              onValueChange={(value) => onStatus(isBookingStatus(value) ? value : null)}
            >
              <DropdownMenuRadioItem value={ANY_STATUS}>
                Any status
                <DropdownMenuShortcut className="tabular-nums">
                  {counts.presets.all}
                </DropdownMenuShortcut>
              </DropdownMenuRadioItem>
              {STATUS_PHASES.map((phase) => (
                <Fragment key={phase}>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>{STATUS_PHASE_LABELS[phase]}</DropdownMenuLabel>
                  {statusesInPhase(phase).map((status) => (
                    <DropdownMenuRadioItem key={status} value={status}>
                      {BOOKING_STATUS_META[status].staffLabel}
                      <DropdownMenuShortcut className="tabular-nums">
                        {counts.statuses[status]}
                      </DropdownMenuShortcut>
                    </DropdownMenuRadioItem>
                  ))}
                </Fragment>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </FilterPill>

        <FilterPill
          icon={CalendarDays}
          active={filters.date !== 'any'}
          label={
            <>
              <span className="sr-only">Scheduled:</span> {DATE_RANGE_LABELS[filters.date]}
            </>
          }
          removeLabel="Remove day filter"
          onRemove={() => onDate('any')}
        >
          <DropdownMenuContent className="w-48">
            <DropdownMenuLabel>Scheduled</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={filters.date}
              onValueChange={(value) => {
                const date = DATE_RANGES.find((range) => range === value)
                if (date) onDate(date)
              }}
            >
              {DATE_RANGES.map((range) => (
                <DropdownMenuRadioItem key={range} value={range}>
                  {DATE_RANGE_LABELS[range]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </FilterPill>
      </div>

      <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
        <span className="font-semibold text-foreground tabular-nums">{matching}</span>{' '}
        {matching === 1 ? 'booking' : 'bookings'}
      </p>
    </>
  )
}
