'use client'

import {
  Banknote,
  Boxes,
  CheckCheck,
  Info,
  PackageCheck,
  PackageX,
  Plus,
  SearchX,
  Truck,
} from 'lucide-react'
import { useParams } from 'next/navigation'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { StatCard, type StatTone } from '@/components/layout/stat-card'
import { AdjustStockSheet } from '@/components/pos/inventory/adjust-stock-sheet'
import {
  adjustmentError,
  canManageStock,
  categoriesOf,
  countLabel,
  filterParts,
  inventorySummary,
  SEARCH_MAX_LENGTH,
  skuTakenBy,
  type InventorySummary,
  type StockFilter,
} from '@/components/pos/inventory/inventory-model'
import { InventorySkeleton } from '@/components/pos/inventory/inventory-skeleton'
import { PartSheet, type PartDraft } from '@/components/pos/inventory/part-sheet'
import { PartsList } from '@/components/pos/inventory/parts-list'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { formatPKR } from '@/lib/format'
import {
  adjustPartStock,
  getCurrentUser,
  getInventory,
  getPurchaseOrders,
  savePart,
  type MockPart,
} from '@/lib/mock-data'

/** A sheet's state; `session` changes on every opening so its form starts again. */
interface SheetState {
  open: boolean
  partId: string | null
  session: number
}

const CLOSED: SheetState = { open: false, partId: null, session: 0 }

const FILTER_CAPTION: Record<StockFilter, string> = {
  all: 'Parts',
  low: 'Parts running low',
  out: 'Parts out of stock',
}

/**
 * PP-03 Inventory (spec 10): the shop's parts with on hand, reserved and available stock, the
 * reorder level, unit cost and stock state (D45); search and stock filters; a part create / edit
 * sheet and, for the Parts Person, a stock adjustment sheet (D44, D82). The Owner edits the
 * catalogue only, with a notice saying so.
 */
export default function InventoryManagementPage() {
  const params = useParams()
  const shopId = typeof params?.shopId === 'string' ? params.shopId : 'shop-lahore-auto-care'

  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const inventory = useMockStore(() => getInventory(shopId))
  const purchaseOrders = useMockStore(() => getPurchaseOrders(shopId))

  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<StockFilter>('all')
  const [partSheet, setPartSheet] = useState<SheetState>(CLOSED)
  const [adjustSheet, setAdjustSheet] = useState<SheetState>(CLOSED)
  const addButton = useRef<HTMLButtonElement>(null)
  /** What opened the current sheet: focus goes back there when the sheet closes. */
  const opener = useRef<HTMLElement | null>(null)

  // The seed data stands in for this browser's stock until it loads (no flash of old counts).
  if (!ready) return <InventorySkeleton />

  const base = `/pos/shops/${encodeURIComponent(shopId)}`
  const canAdjust = canManageStock(user.role)
  const summary = inventorySummary(inventory, purchaseOrders)
  const rows = filterParts(inventory, filter, query)
  const searching = query.trim() !== ''
  const editingPart =
    partSheet.partId === null ? null : (inventory.find((p) => p.id === partSheet.partId) ?? null)
  const adjustPart =
    adjustSheet.partId === null
      ? null
      : (inventory.find((p) => p.id === adjustSheet.partId) ?? null)

  const openCreate = () => {
    const focused = document.activeElement
    opener.current = focused instanceof HTMLElement && focused !== document.body ? focused : null
    setPartSheet((sheet) => ({ open: true, partId: null, session: sheet.session + 1 }))
  }
  const openEdit = (partId: string, menuButton: HTMLElement | null) => {
    opener.current = menuButton
    setPartSheet((sheet) => ({ open: true, partId, session: sheet.session + 1 }))
  }
  const openAdjust = (partId: string, menuButton: HTMLElement | null) => {
    opener.current = menuButton
    setAdjustSheet((sheet) => ({ open: true, partId, session: sheet.session + 1 }))
  }
  /**
   * The sheets are opened from menus and toasts, not a `SheetTrigger`, so Radix has nothing to
   * return focus to: put it back on the opener, or on "Add part" once the opener is gone.
   */
  const restoreFocus = (event: Event) => {
    event.preventDefault()
    if (document.querySelector('[data-slot="sheet-content"][data-state="open"]')) return
    const target = opener.current?.isConnected ? opener.current : addButton.current
    target?.focus()
  }
  const clearFilters = () => {
    setQuery('')
    setFilter('all')
  }

  /** Create or edit; returns the SKU field's error when another part already uses the SKU. */
  const saveDraft = (draft: PartDraft): string | null => {
    // A SKU is unique inside the shop (the API answers 409 CONFLICT, shown on the SKU field);
    // other shops may use the same SKU for their own parts.
    const shopParts = getInventory(shopId)
    const taken = skuTakenBy(shopParts, draft.sku, partSheet.partId ?? undefined)
    if (taken) return `${draft.sku} is already used by ${taken.name}.`

    if (partSheet.partId !== null) {
      const current = shopParts.find((p) => p.id === partSheet.partId)
      if (!current) return 'This part no longer exists. Close the sheet and try again.'
      // Catalogue fields only: stock changes go through Adjust stock (D44).
      savePart({
        ...current,
        sku: draft.sku,
        name: draft.name,
        category: draft.category,
        unit_price: draft.unitCost,
        reorder_level: draft.reorderLevel,
      })
      setPartSheet((sheet) => ({ ...sheet, open: false }))
      toast.success('Part updated', { description: `${draft.sku} · ${draft.name}` })
      return null
    }

    // D44: a new part starts at 0 on hand; the opening stock is an adjustment.
    const part: MockPart = {
      id: `prt-${Date.now()}`,
      shopId,
      sku: draft.sku,
      name: draft.name,
      category: draft.category,
      on_hand: 0,
      reserved: 0,
      reorder_level: draft.reorderLevel,
      unit_price: draft.unitCost,
    }
    savePart(part)
    setPartSheet((sheet) => ({ ...sheet, open: false }))
    if (canAdjust) {
      // Spec 09 §4.9: toasts with an action stay 6 s (hover or focus pauses them).
      toast.success('Part added', {
        description: `${part.sku} · ${part.name} starts at 0 on hand.`,
        action: { label: 'Set opening stock', onClick: () => openAdjust(part.id, null) },
        duration: 6000,
      })
    } else {
      toast.success('Part added', {
        description: `${part.sku} · ${part.name} starts at 0 on hand. Your Parts Person sets the opening stock.`,
      })
    }
    return null
  }

  /** Applies a stock adjustment; returns the 409 message when it would break the stock rules. */
  const applyAdjustment = (delta: number, reason: string): string | null => {
    const current = getInventory(shopId).find((p) => p.id === adjustSheet.partId)
    if (!current) return 'This part no longer exists. Close the sheet and try again.'
    const problem = adjustmentError(current, delta)
    if (problem) return problem
    const updated = adjustPartStock(current.id, delta)
    setAdjustSheet((sheet) => ({ ...sheet, open: false }))
    const why = reason.length > 60 ? `${reason.slice(0, 57).trimEnd()}…` : reason
    toast.success('Stock adjusted', {
      description: `${current.sku} · on hand ${current.on_hand} → ${
        updated?.on_hand ?? current.on_hand + delta
      } · ${why}`,
    })
    return null
  }

  const caption = `${FILTER_CAPTION[filter]}${searching ? ` matching “${query.trim()}”` : ''}`

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Parts"
        title="Inventory"
        description="Stock on hand, what’s reserved for jobs and what needs reordering."
        actions={
          // With no parts yet, the empty state's button is the one primary action.
          inventory.length > 0 ? (
            <Button ref={addButton} onClick={openCreate}>
              <Plus aria-hidden="true" data-icon="inline-start" />
              Add part
            </Button>
          ) : null
        }
      />

      {/* Spec 10 PP-03: the Owner's view (D44) — the catalogue, not the stock. */}
      {canAdjust ? null : (
        <Alert variant="info">
          <Info aria-hidden="true" />
          <AlertTitle>Catalogue only</AlertTitle>
          <AlertDescription>
            <p>Stock operations are done by Parts Persons; you can edit the parts catalogue.</p>
          </AlertDescription>
        </Alert>
      )}

      {inventory.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No parts yet"
          description="Add the parts you stock so jobs can reserve them and you can see what to reorder."
          action={
            <Button onClick={openCreate}>
              <Plus aria-hidden="true" data-icon="inline-start" />
              Add your first part
            </Button>
          }
        />
      ) : (
        <>
          <SummaryCards summary={summary} purchaseOrdersHref={`${base}/purchase-orders`} />

          <DataTableCard
            toolbar={
              <>
                <TableSearch
                  value={query}
                  onValueChange={(value) => setQuery(value.slice(0, SEARCH_MAX_LENGTH))}
                  label="Search parts"
                  placeholder="SKU, name or category"
                />
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  value={filter}
                  onValueChange={(value) =>
                    setFilter(value === 'low' || value === 'out' ? value : 'all')
                  }
                  aria-label="Stock filter"
                  className="flex-wrap"
                >
                  <FilterPill value="all" label="All" count={summary.partCount} />
                  <FilterPill value="low" label="Low stock" count={summary.lowCount} />
                  <FilterPill value="out" label="Out of stock" count={summary.outCount} />
                </ToggleGroup>
                <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
                  {rows.length === inventory.length ? (
                    <>
                      <span className="font-semibold text-foreground tabular-nums">
                        {rows.length}
                      </span>{' '}
                      {rows.length === 1 ? 'part' : 'parts'}
                    </>
                  ) : (
                    <>
                      Showing{' '}
                      <span className="font-semibold text-foreground tabular-nums">
                        {rows.length}
                      </span>{' '}
                      of {countLabel(inventory.length, 'part')}
                    </>
                  )}
                </p>
              </>
            }
          >
            {rows.length > 0 ? (
              <PartsList
                parts={rows}
                caption={caption}
                onAdjust={canAdjust ? openAdjust : undefined}
                onEdit={openEdit}
              />
            ) : searching ? (
              <EmptyState
                variant="inline"
                icon={SearchX}
                title={`No parts match “${query.trim()}”`}
                description={
                  filter === 'all'
                    ? 'Try another SKU, name or category.'
                    : `Nothing under ${filter === 'low' ? 'Low stock' : 'Out of stock'} matches. Try another search, or show every part.`
                }
                action={
                  // Resets the search and the stock filter (the search box has its own clear).
                  <Button variant="outline" onClick={clearFilters}>
                    Show all parts
                  </Button>
                }
              />
            ) : filter === 'low' ? (
              <EmptyState
                variant="inline"
                tone="success"
                icon={CheckCheck}
                title="Nothing is running low"
                description="Every part with stock left is above its reorder level."
              />
            ) : (
              <EmptyState
                variant="inline"
                tone="success"
                icon={CheckCheck}
                title="Nothing is out of stock"
                description="Every part has stock available to use."
              />
            )}
          </DataTableCard>
        </>
      )}

      <PartSheet
        open={partSheet.open && (partSheet.partId === null || editingPart !== null)}
        onOpenChange={(open) => setPartSheet((sheet) => ({ ...sheet, open }))}
        onCloseAutoFocus={restoreFocus}
        part={editingPart}
        formKey={`${partSheet.partId ?? 'new'}-${partSheet.session}`}
        categories={categoriesOf(inventory)}
        canManageStock={canAdjust}
        onSave={saveDraft}
      />
      <AdjustStockSheet
        open={canAdjust && adjustSheet.open && adjustPart !== null}
        onOpenChange={(open) => setAdjustSheet((sheet) => ({ ...sheet, open }))}
        onCloseAutoFocus={restoreFocus}
        part={adjustPart}
        formKey={`${adjustSheet.partId}-${adjustSheet.session}`}
        onApply={applyAdjustment}
      />
    </div>
  )
}

function FilterPill({ value, label, count }: { value: StockFilter; label: string; count: number }) {
  return (
    <ToggleGroupItem value={value}>
      {label} <span className="font-semibold tabular-nums">{count}</span>
    </ToggleGroupItem>
  )
}

/** The stock value summary (the overview's inventory card, in full): value, restock, on order. */
function SummaryCards({
  summary,
  purchaseOrdersHref,
}: {
  summary: InventorySummary
  purchaseOrdersHref: string
}) {
  const restock = summary.lowCount + summary.outCount
  const restockTone: StatTone =
    summary.outCount > 0 ? 'danger' : summary.lowCount > 0 ? 'warning' : 'success'
  const restockHint =
    restock === 0
      ? 'Every part is above its reorder level'
      : [
          summary.lowCount > 0 ? `${summary.lowCount} running low` : null,
          summary.outCount > 0 ? `${summary.outCount} out of stock` : null,
        ]
          .filter(Boolean)
          .join(' · ')

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
      <StatCard
        className="col-span-2 lg:col-span-1"
        label="Stock value"
        value={formatPKR(summary.stockValue)}
        icon={Banknote}
        tone="brand"
        hint={`${countLabel(summary.unitsOnHand, 'unit')} on hand across ${countLabel(
          summary.partCount,
          'part',
        )}`}
      />
      <StatCard
        label="Needs restock"
        value={restock}
        icon={restock === 0 ? PackageCheck : PackageX}
        tone={restockTone}
        hint={restockHint}
      />
      <StatCard
        label="On order"
        value={summary.openOrders}
        icon={Truck}
        hint={
          summary.openOrders === 0
            ? 'No purchase orders waiting'
            : `${summary.openOrders === 1 ? 'Purchase order' : 'Purchase orders'} not yet received`
        }
        href={purchaseOrdersHref}
      />
    </div>
  )
}
