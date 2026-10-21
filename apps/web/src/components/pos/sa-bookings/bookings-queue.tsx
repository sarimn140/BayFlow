'use client'

import {
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock,
  Inbox,
  Plus,
  SearchX,
  Wrench,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { useRef, useState } from 'react'

import { DataTableCard } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Button } from '@/components/ui/button'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { DEFAULT_SHOP_TZ, shopDateKey } from '@/lib/format'
import {
  getBookings,
  getShopById,
  getTeamMembers,
  type MockBooking,
  type MockTeamMember,
} from '@/lib/mock-data'
import { BOOKING_STATUS_META } from '@/lib/status'

import {
  MAX_QUERY_LENGTH,
  countBookings,
  estimateLabel,
  inPreset,
  matchesRefinements,
  nextStepFor,
  normaliseQuery,
  paginate,
  parseQueueParams,
  queueSearchString,
  selectBookings,
  servicesSummary,
  slotDateTime,
  slotLabel,
  updatedLabel,
  type QueueFilters,
  type QueuePreset,
} from './queue-model'
import { BookingsList, BookingsTable, type Assignee, type QueueRow } from './queue-rows'
import { QueueSkeleton } from './queue-skeleton'
import { QueueToolbar } from './queue-toolbar'

const VIEW_NAMES: Record<QueuePreset, string> = {
  needs_action: 'Bookings that need your action',
  in_progress: 'Bookings in progress',
  all: 'All bookings',
}

function assignee(
  members: ReadonlyMap<string, MockTeamMember>,
  id: string | undefined,
  name: string | undefined,
): Assignee | null {
  const member = id ? members.get(id) : undefined
  const shown = name || member?.name
  if (!shown) return null
  return { name: shown, inactive: member?.is_active === false }
}

interface SearchBox {
  /** What the advisor typed (shown in the field). */
  text: string
  /** The URL's `q` this state last caught up with. */
  seen: string
  /** `q` values written to the URL that the router has not reported back yet. */
  sent: string[]
}

/**
 * SA-01 · Bookings list (spec 10): the advisor's queue with the "Needs action" / "In progress" /
 * "All" presets and their counts, search, status and day filters, a table from tablet width and
 * stacked cards below it. Rows open SA-02; nothing changes status from here.
 *
 * The URL is the source of truth (spec 09 §4.7): `?filter=`, `?status=`, `?date=`, `?q=` and
 * `?page=` (see `parseQueueParams` for the links other screens use). Changes are written with
 * `history.replaceState`, which Next.js syncs with `useSearchParams` without a server round trip,
 * so links into the queue, the sidebar link and Back all show the view their URL names.
 */
export function BookingsQueue({ shopId, walkInHref }: { shopId: string; walkInHref: string }) {
  const ready = useMockStoreReady()
  const nowIso = useNowMinute()
  const bookings = useMockStore(() => getBookings(shopId))
  const shop = useMockStore(() => getShopById(shopId))
  const team = useMockStore(() => getTeamMembers(shopId))
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const topRef = useRef<HTMLDivElement>(null)

  const fromUrl = parseQueueParams(searchParams)
  // The router reports our own URL writes a moment later (in a transition), possibly after more
  // typing, so they are recognised by value; any other change of `q` (a link, Back) wins.
  const [search, setSearch] = useState<SearchBox>({
    text: fromUrl.query,
    seen: fromUrl.query,
    sent: [],
  })
  if (fromUrl.query !== search.seen) {
    const index = search.sent.indexOf(fromUrl.query)
    setSearch(
      index >= 0
        ? { text: search.text, seen: fromUrl.query, sent: search.sent.slice(index + 1) }
        : { text: fromUrl.query, seen: fromUrl.query, sent: [] },
    )
  }
  const filters: QueueFilters = { ...fromUrl, query: search.text }

  if (!ready || !nowIso) return <QueueSkeleton />

  const timeZone = shop?.timezone || DEFAULT_SHOP_TZ
  const todayKey = shopDateKey(nowIso, timeZone)
  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  const write = (next: QueueFilters) => {
    const query = queueSearchString(next)
    window.history.replaceState(null, '', query ? `${pathname}?${query}` : pathname)
  }
  /** Any filter change starts again on page 1. */
  const update = (patch: Partial<QueueFilters>) => {
    const next: QueueFilters = { ...filters, page: 1, ...patch }
    if (patch.query !== undefined) {
      const written = normaliseQuery(next.query)
      setSearch((current) => {
        const last = current.sent.at(-1) ?? current.seen
        return {
          ...current,
          text: next.query,
          sent: written === last ? current.sent : [...current.sent, written],
        }
      })
    }
    write(next)
  }
  const clearRefinements = () => update({ status: null, date: 'any', query: '' })
  const goToPage = (page: number) => {
    write({ ...filters, page })
    topRef.current?.scrollIntoView({ block: 'start' })
  }

  const counts = countBookings(bookings)
  const matching = selectBookings(bookings, filters, todayKey)
  const slice = paginate(matching, filters.page)

  const members = new Map(team.map((member) => [member.id, member]))
  const rows: QueueRow[] = slice.rows.map((booking: MockBooking) => {
    const services = servicesSummary(booking.services)
    return {
      booking,
      href: `${base}/bookings/${encodeURIComponent(booking.id)}`,
      slot: slotLabel(booking, todayKey),
      slotDateTime: slotDateTime(booking),
      updated: updatedLabel(booking.updatedAt, nowIso),
      estimate: estimateLabel(booking),
      firstService: services.first,
      moreServices: services.more,
      technician: assignee(members, booking.assignedTechnicianId, booking.assignedTechnicianName),
      partsPerson: assignee(members, booking.assignedPartsPersonId, undefined),
      nextStep: nextStepFor(booking.status),
    }
  })

  const viewName = filters.status
    ? `${BOOKING_STATUS_META[filters.status].staffLabel} bookings`
    : VIEW_NAMES[filters.preset]

  const footer =
    matching.length > 0 ? (
      <>
        <p className="flex items-center gap-1.5 text-xs text-helper">
          <Clock className="size-3.5 shrink-0" aria-hidden="true" />
          Times are shop local time ({timeZone}).
        </p>
        {slice.pageCount > 1 ? (
          <nav aria-label="Pages" className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground tabular-nums">
              {slice.from}–{slice.to} of {matching.length}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              className="max-sm:size-10"
              aria-label="Previous page"
              disabled={slice.page === 1}
              onClick={() => goToPage(slice.page - 1)}
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              className="max-sm:size-10"
              aria-label="Next page"
              disabled={slice.page === slice.pageCount}
              onClick={() => goToPage(slice.page + 1)}
            >
              <ChevronRight aria-hidden="true" />
            </Button>
          </nav>
        ) : null}
      </>
    ) : null

  return (
    <div ref={topRef} className="scroll-mt-24">
      <DataTableCard
        className="@container"
        toolbar={
          <QueueToolbar
            filters={filters}
            counts={counts}
            matching={matching.length}
            // A preset replaces a status filter; the search and the day stay.
            onPreset={(preset) => update({ preset, status: null })}
            onQuery={(query) => update({ query: query.slice(0, MAX_QUERY_LENGTH) })}
            // A status is looked for among all bookings.
            onStatus={(status) => update(status ? { preset: 'all', status } : { status: null })}
            onDate={(date) => update({ date })}
          />
        }
        footer={footer}
      >
        {matching.length === 0 ? (
          <QueueEmpty
            filters={filters}
            bookings={bookings}
            todayKey={todayKey}
            walkInHref={walkInHref}
            onShowAll={() => update({ preset: 'all' })}
            onClear={clearRefinements}
          />
        ) : (
          // Stacked cards until the card is wide enough for the table's core columns (672px):
          // phones, and tablets with the sidebar open (spec 09 §6).
          <>
            <BookingsList rows={rows} label={viewName} className="@min-[42rem]:hidden" />
            <div className="hidden @min-[42rem]:block">
              <BookingsTable rows={rows} caption={viewName} />
            </div>
          </>
        )}
      </DataTableCard>
    </div>
  )
}

/** Spec 10 SA-01 empty states: no match, no bookings yet, nothing on the floor, all caught up. */
function QueueEmpty({
  filters,
  bookings,
  todayKey,
  walkInHref,
  onShowAll,
  onClear,
}: {
  filters: QueueFilters
  bookings: ReadonlyArray<MockBooking>
  todayKey: string
  walkInHref: string
  onShowAll: () => void
  onClear: () => void
}) {
  const refined = filters.status !== null || filters.date !== 'any' || filters.query.trim() !== ''

  if (refined) {
    // A search can match bookings that sit in another view ("BF-2026-001 is in progress").
    const elsewhere =
      filters.preset === 'all'
        ? 0
        : bookings.filter(
            (booking) =>
              !inPreset(booking.status, filters.preset) &&
              matchesRefinements(booking, filters, todayKey),
          ).length
    const query = filters.query.trim()
    return (
      <EmptyState
        variant="inline"
        icon={SearchX}
        title={query ? `No bookings match “${query}”` : 'No bookings match these filters'}
        description={
          elsewhere > 0
            ? `${elsewhere} ${elsewhere === 1 ? 'booking matches' : 'bookings match'} in ${
                elsewhere === 1 ? 'another view' : 'other views'
              }.`
            : 'Try another reference, plate, status or day.'
        }
        action={
          elsewhere > 0 ? (
            <Button variant="outline" onClick={onShowAll}>
              Show all matches
            </Button>
          ) : (
            <Button variant="outline" onClick={onClear}>
              Clear filters
            </Button>
          )
        }
      />
    )
  }

  // A shop without a single booking gets the first-use state, whichever view is open.
  if (bookings.length === 0) {
    return (
      <EmptyState
        variant="inline"
        icon={Inbox}
        title="No bookings yet"
        description="Online bookings and walk-ins appear here as soon as they are made."
        action={
          <Button asChild variant="outline">
            <Link href={walkInHref}>
              <Plus aria-hidden="true" />
              New walk-in booking
            </Link>
          </Button>
        }
      />
    )
  }

  if (filters.preset === 'in_progress') {
    return (
      <EmptyState
        variant="inline"
        tone="neutral"
        icon={Wrench}
        title="Nothing on the floor"
        description="No cars are with technicians, parts or QC right now."
      />
    )
  }

  // "Needs action" is empty: the advisor's queue is done (spec 10 SA-01 copy).
  return (
    <EmptyState
      variant="inline"
      tone="success"
      icon={CheckCheck}
      title="All caught up"
      description="Nothing needs your action right now."
    />
  )
}
