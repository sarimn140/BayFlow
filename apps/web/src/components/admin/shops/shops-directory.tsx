'use client'

import { ChevronRight, SearchX, Store } from 'lucide-react'
import Link from 'next/link'
import { useMemo, useState } from 'react'

import { AdminPageHeader, ShopStatusBadges, usePaged } from '@/components/admin/admin-ui'
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore } from '@/hooks/use-mock-store'
import { formatDate } from '@/lib/format'
import { getAdminShops, type AdminShop } from '@/lib/mock-admin'

import {
  cityOptions,
  filterShops,
  hasActiveFilters,
  statusCounts,
  type ListedFilter,
  type StatusFilter,
} from './shops-data'

const STATUS_PILLS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'ACTIVE', label: 'Active' },
  { value: 'SUSPENDED', label: 'Suspended' },
]

function shopHref(tenant: AdminShop) {
  return `/admin/shops/${encodeURIComponent(tenant.shop.id)}`
}

function count(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`
}

/** A shop on a phone or a narrow window: name and status, owner, then the figures. */
function ShopRow({ tenant }: { tenant: AdminShop }) {
  return (
    <li>
      <Link
        href={shopHref(tenant)}
        className="group flex items-center gap-3 px-5 py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
      >
        <span className="min-w-0 flex-1 space-y-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="min-w-0 truncate text-sm font-semibold text-brand-blue-ink">
              {tenant.shop.name}
            </span>
            <ShopStatusBadges tenant={tenant} />
          </span>
          {tenant.owners.length > 0 ? (
            tenant.owners.map((owner) => (
              <span key={owner.email} className="block min-w-0">
                <span className="block truncate text-sm text-foreground">{owner.name}</span>
                <span className="block truncate text-xs text-helper">{owner.email}</span>
              </span>
            ))
          ) : (
            <span className="block text-sm font-medium text-danger-ink">No active owner</span>
          )}
          <span className="block text-xs text-helper">
            {tenant.shop.city} · {count(tenant.activeMembers, 'member')} ·{' '}
            {count(tenant.bookingsTotal, 'booking')} · joined {formatDate(tenant.createdAt)}
          </span>
        </span>
        <ChevronRight
          className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </Link>
    </li>
  )
}

/**
 * A-02 Shops (spec 19 §5; E-62 once wired): every tenant, suspended ones included, with a search,
 * status pills, city and listing filters, and a table (stacked rows on narrow screens) whose shop
 * names open A-03.
 */
export function ShopsDirectory() {
  const tenants = useMockStore(getAdminShops)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [city, setCity] = useState('ALL')
  const [listed, setListed] = useState<ListedFilter>('ALL')

  const cities = useMemo(() => cityOptions(tenants), [tenants])
  const filtered = useMemo(
    () => filterShops(tenants, { q, status, city, listed }),
    [tenants, q, status, city, listed],
  )
  const counts = useMemo(
    () => statusCounts(tenants, { q, status, city, listed }),
    [tenants, q, status, city, listed],
  )
  const { rows, pager, reset } = usePaged(filtered)
  const filtering = hasActiveFilters({ q, status, city, listed })

  const clearFilters = () => {
    setQ('')
    setStatus('ALL')
    setCity('ALL')
    setListed('ALL')
    reset()
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Shops"
        description="Every tenant on BayFlow. Open a shop to see its team and bookings, or to suspend it."
      />

      <DataTableCard
        className="@container/shops"
        toolbar={
          <>
            <TableSearch
              value={q}
              onValueChange={(value) => {
                setQ(value)
                reset()
              }}
              label="Search shops"
              placeholder="Name, city or owner e-mail"
            />
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={status}
              onValueChange={(value) => {
                setStatus((value || 'ALL') as StatusFilter)
                reset()
              }}
              aria-label="Filter by status"
            >
              {STATUS_PILLS.map((pill) => (
                <ToggleGroupItem key={pill.value} value={pill.value}>
                  {pill.label}
                  <span className="text-helper tabular-nums group-data-[state=on]/toggle:text-brand-blue-ink">
                    {counts[pill.value]}
                  </span>
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Select
                value={city}
                onValueChange={(value) => {
                  setCity(value)
                  reset()
                }}
              >
                <SelectTrigger size="sm" aria-label="City" className="w-full sm:w-auto sm:min-w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All cities</SelectItem>
                  {cities.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={listed}
                onValueChange={(value) => {
                  setListed(value as ListedFilter)
                  reset()
                }}
              >
                <SelectTrigger
                  size="sm"
                  aria-label="Directory listing"
                  className="w-full sm:w-auto sm:min-w-36"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">Any listing</SelectItem>
                  <SelectItem value="LISTED">Listed</SelectItem>
                  <SelectItem value="UNLISTED">Unlisted</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* The count sits at the row's end; on phones it leads and the reset follows. */}
            <div className="flex min-h-10 items-center justify-between gap-3 sm:ml-auto sm:flex-row-reverse sm:justify-start">
              <p className="text-sm whitespace-nowrap text-muted-foreground" aria-live="polite">
                <span className="font-semibold text-foreground tabular-nums">
                  {filtered.length}
                </span>{' '}
                {filtered.length === 1 ? 'shop' : 'shops'}
              </p>
              {filtering && filtered.length > 0 ? (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
            </div>
          </>
        }
      >
        {tenants.length === 0 ? (
          <EmptyState
            variant="inline"
            tone="neutral"
            icon={Store}
            title="No shops yet"
            description="Shops appear here as soon as an owner creates one."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            variant="inline"
            icon={SearchX}
            title="No shops match"
            description="Try another name, city or owner e-mail, or clear the filters."
            action={
              <Button variant="outline" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <>
            <ul className="divide-y divide-border-faint @4xl/shops:hidden" aria-label="Shops">
              {rows.map((tenant) => (
                <ShopRow key={tenant.shop.id} tenant={tenant} />
              ))}
            </ul>
            <div className="hidden @4xl/shops:block">
              <Table>
                <TableCaption className="sr-only">Shops on BayFlow, newest first</TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Shop</TableHead>
                    <TableHead scope="col">Owner</TableHead>
                    <TableHead scope="col">Status</TableHead>
                    <TableHead scope="col" className="text-right">
                      Members
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Bookings
                    </TableHead>
                    <TableHead scope="col">Joined</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((tenant) => (
                    <TableRow key={tenant.shop.id}>
                      <TableCell>
                        <Link
                          href={shopHref(tenant)}
                          className="rounded-sm font-semibold text-brand-blue-ink outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                        >
                          {tenant.shop.name}
                        </Link>
                        <p className="text-xs text-helper">{tenant.shop.city}</p>
                      </TableCell>
                      <TableCell>
                        {tenant.owners.length > 0 ? (
                          <div className="space-y-1">
                            {tenant.owners.map((owner) => (
                              <div key={owner.email} className="max-w-60">
                                <p className="truncate font-medium text-foreground">{owner.name}</p>
                                <p className="truncate text-xs text-helper">{owner.email}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className="font-medium text-danger-ink">No active owner</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1.5">
                          <ShopStatusBadges tenant={tenant} />
                        </div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {tenant.activeMembers}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {tenant.bookingsTotal}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(tenant.createdAt)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {pager}
          </>
        )}
      </DataTableCard>
    </div>
  )
}
