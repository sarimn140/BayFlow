'use client'

import { SearchX } from 'lucide-react'
import { useMemo, useState } from 'react'

import { AdminPageHeader, usePaged } from '@/components/admin/admin-ui'
import { UsersList, UsersTable } from '@/components/admin/users/user-list'
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { getAdminUsers, type AdminUserKind } from '@/lib/mock-admin'

type KindFilter = 'ALL' | AdminUserKind
type StatusFilter = 'ALL' | 'ACTIVE' | 'INACTIVE'

const KIND_FILTERS: ReadonlyArray<{ value: KindFilter; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'CUSTOMER', label: 'Customers' },
  { value: 'STAFF', label: 'Shop staff' },
  { value: 'PLATFORM_ADMIN', label: 'Platform admins' },
]

/** The toolbar search gives up a little width so the filters and the count share its row. */
const SEARCH_CLASS = 'sm:w-auto sm:max-w-72 sm:min-w-52 sm:flex-1'

/** A-04 Users (spec 19 §5; E-66 once wired). */
export function UsersDirectory() {
  const users = useMockStore(getAdminUsers)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<KindFilter>('ALL')
  const [status, setStatus] = useState<StatusFilter>('ALL')

  // Search and status first; the kind pills count within that, so each shows what it would list.
  const matching = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return users
      .filter((u) => status === 'ALL' || (status === 'ACTIVE' ? u.isActive : !u.isActive))
      .filter(
        (u) => !needle || [u.name, u.email, u.phone ?? ''].join(' ').toLowerCase().includes(needle),
      )
  }, [users, q, status])

  const filtered = useMemo(
    () => matching.filter((u) => kind === 'ALL' || u.kind === kind),
    [matching, kind],
  )

  const counts = useMemo(() => {
    const byKind: Record<KindFilter, number> = {
      ALL: matching.length,
      CUSTOMER: 0,
      STAFF: 0,
      PLATFORM_ADMIN: 0,
    }
    for (const u of matching) byKind[u.kind] += 1
    return byKind
  }, [matching])

  const { rows, pager, reset } = usePaged(filtered)
  const nowIso = useNowMinute()

  const filtersActive = q.trim() !== '' || kind !== 'ALL' || status !== 'ALL'
  const clearFilters = () => {
    setQ('')
    setKind('ALL')
    setStatus('ALL')
    reset()
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Users"
        description="Every account: customers, shop staff and platform admins."
      />

      <DataTableCard
        className="@container/users"
        toolbar={
          <>
            <TableSearch
              value={q}
              onValueChange={(value) => {
                setQ(value)
                reset()
              }}
              label="Search users"
              placeholder="Name, e-mail or phone"
              className={SEARCH_CLASS}
            />
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={kind}
              onValueChange={(value) => {
                setKind((value || 'ALL') as KindFilter)
                reset()
              }}
              aria-label="Filter by kind"
              className="flex-wrap"
            >
              {KIND_FILTERS.map((option) => (
                <ToggleGroupItem key={option.value} value={option.value}>
                  {option.label}
                  <span className="font-normal tabular-nums">{counts[option.value]}</span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <NativeSelect
              size="sm"
              aria-label="Status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as StatusFilter)
                reset()
              }}
              className="w-full sm:w-auto"
            >
              <NativeSelectOption value="ALL">All statuses</NativeSelectOption>
              <NativeSelectOption value="ACTIVE">Active</NativeSelectOption>
              <NativeSelectOption value="INACTIVE">Deactivated</NativeSelectOption>
            </NativeSelect>
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
                {filtered.length === 1 ? 'account' : 'accounts'}
              </p>
            </div>
          </>
        }
      >
        {rows.length === 0 ? (
          <EmptyState
            variant="inline"
            icon={SearchX}
            title="No accounts match these filters"
            description="Try another name, e-mail or phone number, or clear the filters."
            action={
              <Button variant="outline" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <>
            <div className="@4xl/users:hidden">
              <UsersList users={rows} nowIso={nowIso} />
            </div>
            <div className="hidden @4xl/users:block">
              <UsersTable users={rows} nowIso={nowIso} />
            </div>
            {pager}
          </>
        )}
      </DataTableCard>
    </div>
  )
}
