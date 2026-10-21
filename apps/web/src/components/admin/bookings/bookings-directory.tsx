'use client'

import { SearchX } from 'lucide-react'
import { useId, useMemo, useState } from 'react'

import { AdminPageHeader, usePaged } from '@/components/admin/admin-ui'
import { BookingsList, BookingsTable } from '@/components/admin/bookings/booking-list'
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Button } from '@/components/ui/button'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { useMockStore } from '@/hooks/use-mock-store'
import { getBookings, getShops } from '@/lib/mock-data'
import { slotSortKey } from '@/lib/slot'
import { STATUS_PHASES, STATUS_PHASE_LABELS, statusPhase, type StatusPhase } from '@/lib/status'

/** The toolbar search gives up a little width so the filters and the count share its row. */
const SEARCH_CLASS = 'sm:w-auto sm:max-w-72 sm:min-w-52 sm:flex-1'

/** A-06 Bookings across every shop (spec 19 §5; E-72 once wired). Read-only. */
export function BookingsDirectory() {
  const bookings = useMockStore(getBookings)
  const shops = useMockStore(getShops)
  const [q, setQ] = useState('')
  const [shopId, setShopId] = useState('ALL')
  const [phase, setPhase] = useState<'ALL' | StatusPhase>('ALL')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const id = useId()

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (
      bookings
        .filter((b) => shopId === 'ALL' || b.shopId === shopId)
        .filter((b) => phase === 'ALL' || statusPhase(b.status) === phase)
        // Slot dates are shop-local YYYY-MM-DD strings, so they compare as text (E-72 date_from/date_to).
        .filter((b) => (!from || b.scheduledDate >= from) && (!to || b.scheduledDate <= to))
        .filter(
          (b) =>
            !needle ||
            [b.reference, b.licensePlate, b.customerName, b.customerEmail]
              .join(' ')
              .toLowerCase()
              .includes(needle),
        )
        .sort((a, b) => slotSortKey(b).localeCompare(slotSortKey(a)))
    )
  }, [bookings, q, shopId, phase, from, to])

  const { rows, pager, reset } = usePaged(filtered)

  // E-72 refuses a range that ends before it starts (422 query.date_to); say so here too.
  const rangeInvalid = Boolean(from && to && from > to)
  const filtersActive = q.trim() !== '' || shopId !== 'ALL' || phase !== 'ALL' || !!from || !!to
  const clearFilters = () => {
    setQ('')
    setShopId('ALL')
    setPhase('ALL')
    setFrom('')
    setTo('')
    reset()
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Bookings"
        description="Every booking in every shop, read-only. Shops act on their own bookings."
      />

      <DataTableCard
        className="@container/bookings"
        toolbar={
          <>
            <TableSearch
              value={q}
              onValueChange={(value) => {
                setQ(value)
                reset()
              }}
              label="Search bookings"
              placeholder="Reference, plate or customer"
              className={SEARCH_CLASS}
            />
            <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:items-center">
              <NativeSelect
                size="sm"
                aria-label="Shop"
                value={shopId}
                onChange={(event) => {
                  setShopId(event.target.value)
                  reset()
                }}
                className="w-full sm:w-auto"
              >
                <NativeSelectOption value="ALL">All shops</NativeSelectOption>
                {shops.map((s) => (
                  <NativeSelectOption key={s.id} value={s.id}>
                    {s.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <NativeSelect
                size="sm"
                aria-label="Phase"
                value={phase}
                onChange={(event) => {
                  setPhase(event.target.value as typeof phase)
                  reset()
                }}
                className="w-full sm:w-auto"
              >
                <NativeSelectOption value="ALL">All phases</NativeSelectOption>
                {STATUS_PHASES.map((p) => (
                  <NativeSelectOption key={p} value={p}>
                    {STATUS_PHASE_LABELS[p]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-3 sm:flex sm:items-center">
              <InputGroup className="rounded-md sm:w-46">
                <InputGroupAddon>
                  <label htmlFor={`${id}-from`} className="cursor-default">
                    <span className="sr-only">Slot date </span>From
                  </label>
                </InputGroupAddon>
                <InputGroupInput
                  id={`${id}-from`}
                  type="date"
                  value={from}
                  max={to || undefined}
                  aria-invalid={rangeInvalid || undefined}
                  aria-describedby={rangeInvalid ? `${id}-range-error` : undefined}
                  onChange={(event) => {
                    setFrom(event.target.value)
                    reset()
                  }}
                />
              </InputGroup>
              <InputGroup className="rounded-md sm:w-44">
                <InputGroupAddon>
                  <label htmlFor={`${id}-to`} className="cursor-default">
                    <span className="sr-only">Slot date </span>To
                  </label>
                </InputGroupAddon>
                <InputGroupInput
                  id={`${id}-to`}
                  type="date"
                  value={to}
                  min={from || undefined}
                  aria-invalid={rangeInvalid || undefined}
                  aria-describedby={rangeInvalid ? `${id}-range-error` : undefined}
                  onChange={(event) => {
                    setTo(event.target.value)
                    reset()
                  }}
                />
              </InputGroup>
            </div>
            <div className="flex items-center justify-between gap-3 sm:ml-auto">
              {filtersActive ? (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
              <p className="text-sm text-muted-foreground" aria-live="polite">
                <span className="font-semibold text-foreground tabular-nums">
                  {filtered.length}
                </span>{' '}
                {filtered.length === 1 ? 'booking' : 'bookings'}
              </p>
            </div>
            {rangeInvalid ? (
              <p
                id={`${id}-range-error`}
                role="alert"
                className="text-sm text-destructive sm:basis-full"
              >
                The &ldquo;From&rdquo; date is after the &ldquo;To&rdquo; date. Pick a range that
                starts first.
              </p>
            ) : null}
          </>
        }
      >
        {rows.length === 0 ? (
          <EmptyState
            variant="inline"
            icon={SearchX}
            title="No bookings match these filters"
            description="Try another reference, plate or customer, or widen the dates."
            action={
              <Button variant="outline" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <>
            <div className="@min-[58rem]/bookings:hidden">
              <BookingsList bookings={rows} />
            </div>
            <div className="hidden @min-[58rem]/bookings:block">
              <BookingsTable bookings={rows} />
            </div>
            {pager}
          </>
        )}
      </DataTableCard>
    </div>
  )
}
