'use client'

import { Download, History, SearchX } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { useAdminActor } from '@/components/admin/admin-shell'
import { AdminPageHeader, usePaged } from '@/components/admin/admin-ui'
import { AuditEventList, CATEGORY_LABEL } from '@/components/admin/audit-events'
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { useMockStore } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import {
  AUDIT_EXPORT_LIMIT,
  auditCsv,
  getAuditEvents,
  recordAuditExport,
  type AuditCategory,
} from '@/lib/mock-admin'
import { getShops } from '@/lib/mock-data'

const PERIODS = {
  '24h': { label: 'Last 24 hours', ms: 24 * 36e5 },
  '7d': { label: 'Last 7 days', ms: 7 * 24 * 36e5 },
  '30d': { label: 'Last 30 days', ms: 30 * 24 * 36e5 },
  all: { label: 'All time', ms: Number.POSITIVE_INFINITY },
} as const

type Period = keyof typeof PERIODS

const DEFAULT_PERIOD: Period = '30d'

/** The toolbar search gives up a little width so the filters and the count share its row. */
const SEARCH_CLASS = 'sm:w-auto sm:max-w-72 sm:min-w-52 sm:flex-1'

/** A-08 Audit log (spec 19 §5; E-74 and E-75 once wired). */
export function AuditLog() {
  const { user } = useAdminActor()
  const events = useMockStore(getAuditEvents)
  const shops = useMockStore(getShops)
  const [q, setQ] = useState('')
  const [category, setCategory] = useState<'ALL' | AuditCategory>('ALL')
  const [shopId, setShopId] = useState('ALL')
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD)

  const nowIso = useNowMinute()
  const filtered = useMemo(() => {
    const now = nowIso ? Date.parse(nowIso) : Number.POSITIVE_INFINITY
    const needle = q.trim().toLowerCase()
    return events
      .filter((e) => category === 'ALL' || e.category === category)
      .filter((e) => shopId === 'ALL' || e.shop?.id === shopId)
      .filter((e) => now - Date.parse(e.occurredAt) <= PERIODS[period].ms)
      .filter(
        (e) =>
          !needle ||
          [
            e.summary,
            e.action,
            e.actor?.name ?? '',
            e.actor?.email ?? '',
            e.target?.label ?? '',
            e.ip ?? '',
          ]
            .join(' ')
            .toLowerCase()
            .includes(needle),
      )
  }, [events, q, category, shopId, period, nowIso])

  const { rows, pager, reset } = usePaged(filtered, 25)

  const exportCsv = () => {
    const csv = auditCsv(filtered)
    // A byte-order mark first, so spreadsheet apps read the file as UTF-8.
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `bayflow-audit-${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(url)
    const rowsExported = Math.min(filtered.length, AUDIT_EXPORT_LIMIT)
    recordAuditExport({ q: q || null, category, shop_id: shopId, period }, rowsExported, {
      name: user.name,
      email: user.email,
    })
    toast.success(`Exported ${rowsExported} ${rowsExported === 1 ? 'event' : 'events'}`)
  }

  const change =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value)
      reset()
    }

  const filtersActive =
    q.trim() !== '' || category !== 'ALL' || shopId !== 'ALL' || period !== DEFAULT_PERIOD
  const clearFilters = () => {
    setQ('')
    setCategory('ALL')
    setShopId('ALL')
    setPeriod(DEFAULT_PERIOD)
    reset()
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Audit log"
        description="Who did what, where and when, across every shop. Entries can't be edited or deleted."
        actions={
          <Button onClick={exportCsv} disabled={filtered.length === 0}>
            <Download data-icon="inline-start" aria-hidden="true" />
            Export CSV
          </Button>
        }
      />

      <DataTableCard
        toolbar={
          <>
            <TableSearch
              value={q}
              onValueChange={change(setQ)}
              label="Search the audit log"
              placeholder="Person, reference, action or IP"
              className={SEARCH_CLASS}
            />
            <div className="grid grid-cols-2 gap-3 sm:flex sm:flex-wrap sm:items-center">
              <NativeSelect
                size="sm"
                aria-label="Category"
                value={category}
                onChange={(event) => change(setCategory)(event.target.value as typeof category)}
                className="w-full sm:w-auto"
              >
                <NativeSelectOption value="ALL">All categories</NativeSelectOption>
                {(Object.keys(CATEGORY_LABEL) as AuditCategory[]).map((c) => (
                  <NativeSelectOption key={c} value={c}>
                    {CATEGORY_LABEL[c]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <NativeSelect
                size="sm"
                aria-label="Shop"
                value={shopId}
                onChange={(event) => change(setShopId)(event.target.value)}
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
                aria-label="Period"
                value={period}
                onChange={(event) => change(setPeriod)(event.target.value as Period)}
                className="col-span-2 w-full sm:w-auto"
              >
                {(Object.keys(PERIODS) as Period[]).map((p) => (
                  <NativeSelectOption key={p} value={p}>
                    {PERIODS[p].label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
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
                {filtered.length === 1 ? 'event' : 'events'}
              </p>
            </div>
          </>
        }
      >
        {filtered.length === 0 ? (
          filtersActive ? (
            <EmptyState
              variant="inline"
              icon={SearchX}
              title="No events match these filters"
              description="Try another search, category or shop, or a longer period."
              action={
                <Button variant="outline" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              variant="inline"
              tone="neutral"
              icon={History}
              title="Nothing recorded in the last 30 days"
              description="Older entries are kept. Choose a longer period to see them."
              action={
                <Button variant="outline" onClick={() => change(setPeriod)('all')}>
                  Show all time
                </Button>
              }
            />
          )
        ) : (
          <>
            <AuditEventList events={rows} />
            {pager}
          </>
        )}
      </DataTableCard>
    </div>
  )
}
