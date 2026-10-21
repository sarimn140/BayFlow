'use client'

import { Ellipsis, Pencil, SlidersHorizontal } from 'lucide-react'
import { useRef } from 'react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatPKR } from '@/lib/format'
import type { MockPart } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { availableOf, stockState } from './inventory-model'
import { STOCK_INK, StockBadge } from './stock-badge'

/** `menuButton` is the row's menu button: focus goes back to it when the sheet closes. */
export interface PartActionHandlers {
  /** Stock operations (D44): Parts Persons only; without it the menu has no "Adjust stock". */
  onAdjust?: (partId: string, menuButton: HTMLElement | null) => void
  onEdit: (partId: string, menuButton: HTMLElement | null) => void
}

/** Numeric columns: right-aligned tabular figures, a little tighter than the default 16px. */
const NUMBER = 'px-2.5 text-right tabular-nums xl:px-3'

/** Secondary columns (spec 09 §6 "tables hide secondary columns" on tablets): from `xl` only. */
const SECONDARY = 'hidden xl:table-cell'

/**
 * The parts, as a stacked list below `lg` (spec 10 PP-03 "Mobile: cards: name, SKU, a large
 * Available, stock badge, and a menu") and as the table from `lg` up. The header stays in view
 * while the rows scroll, and the row menu stays pinned to the right edge when the table is wider
 * than its card (the scroll is on the table container, so it never widens the page).
 */
export function PartsList({
  parts,
  caption,
  ...handlers
}: {
  parts: ReadonlyArray<MockPart>
  /** Names the table for screen readers, e.g. "Parts running low". */
  caption: string
} & PartActionHandlers) {
  return (
    <>
      <ul aria-label={caption} className="divide-y divide-border-faint lg:hidden">
        {parts.map((part) => (
          <PartCard key={part.id} part={part} {...handlers} />
        ))}
      </ul>

      <div className="hidden lg:block [&_[data-slot=table-container]]:max-h-[70svh]">
        <Table>
          <TableCaption className="sr-only">{caption}</TableCaption>
          {/* Opaque header cells (the header band's tint mixed into white): rows scroll under. */}
          <TableHeader className="sticky top-0 z-10 bg-card [&_th]:bg-[color-mix(in_srgb,var(--color-layer)_60%,var(--color-card))] [&_th]:shadow-[inset_0_-1px_0_var(--color-border-faint)] [&_th:last-child]:shadow-[inset_1px_0_0_var(--color-border-faint),inset_0_-1px_0_var(--color-border-faint)] [&_tr]:border-b-0">
            <TableRow>
              <TableHead scope="col" className="pr-3">
                SKU
              </TableHead>
              <TableHead scope="col" className="px-3">
                Part
              </TableHead>
              <TableHead scope="col" className={NUMBER}>
                On hand
              </TableHead>
              <TableHead scope="col" className={NUMBER}>
                Reserved
              </TableHead>
              <TableHead scope="col" className={NUMBER}>
                Available
              </TableHead>
              <TableHead scope="col" className={cn(NUMBER, SECONDARY)}>
                Reorder level
              </TableHead>
              <TableHead scope="col" className={cn(NUMBER, SECONDARY)}>
                Unit cost
              </TableHead>
              <TableHead scope="col" className="px-3">
                Stock
              </TableHead>
              <TableHead scope="col" className="sticky right-0 w-0 pl-2 last:pr-3">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {parts.map((part) => {
              const state = stockState(part)
              return (
                <TableRow key={part.id} className="group/row">
                  <TableCell className="pr-3 font-mono font-semibold">{part.sku}</TableCell>
                  <TableCell className="min-w-36 px-3 py-3 whitespace-normal xl:min-w-40">
                    <p className="font-medium text-foreground">{part.name}</p>
                    {part.category ? <p className="text-xs text-helper">{part.category}</p> : null}
                  </TableCell>
                  <TableCell className={NUMBER}>{part.on_hand}</TableCell>
                  <TableCell className={cn(NUMBER, 'text-muted-foreground')}>
                    {part.reserved}
                  </TableCell>
                  <TableCell className={cn(NUMBER, 'font-semibold', STOCK_INK[state])}>
                    {Math.max(availableOf(part), 0)}
                  </TableCell>
                  <TableCell className={cn(NUMBER, SECONDARY, 'text-muted-foreground')}>
                    {part.reorder_level}
                  </TableCell>
                  <TableCell className={cn(NUMBER, SECONDARY)}>
                    {formatPKR(part.unit_price)}
                  </TableCell>
                  <TableCell className="px-3">
                    <StockBadge state={state} />
                  </TableCell>
                  {/* Pinned: opaque, with the row's hover and open-menu tint mixed into white. */}
                  <TableCell className="sticky right-0 w-0 bg-card pl-2 shadow-[inset_1px_0_0_var(--color-border-faint)] group-hover/row:bg-[color-mix(in_srgb,var(--color-brand-blue-subtle)_40%,var(--color-card))] group-has-aria-expanded/row:bg-[color-mix(in_srgb,var(--color-brand-blue-subtle)_40%,var(--color-card))] last:pr-3">
                    <PartActions part={part} {...handlers} />
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </>
  )
}

function PartCard({ part, ...handlers }: { part: MockPart } & PartActionHandlers) {
  const state = stockState(part)
  return (
    <li className="space-y-3 px-5 py-4 sm:px-6">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-base leading-snug font-semibold text-foreground">{part.name}</p>
          {/* One text run: the SKU, then the category. */}
          <p className="font-mono text-xs break-all text-helper">
            {part.category ? `${part.sku} · ${part.category}` : `SKU ${part.sku}`}
          </p>
          <StockBadge state={state} />
        </div>
        <PartActions part={part} {...handlers} />
      </div>

      <dl className="grid grid-cols-3 gap-3 rounded-xl bg-layer px-4 py-3">
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">Available</dt>
          <dd
            className={cn(
              'text-2xl leading-8 font-extrabold tracking-tight tabular-nums',
              STOCK_INK[state],
            )}
          >
            {Math.max(availableOf(part), 0)}
          </dd>
        </div>
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">On hand</dt>
          <dd className="text-base leading-8 font-semibold text-foreground tabular-nums">
            {part.on_hand}
          </dd>
        </div>
        <div className="space-y-0.5">
          <dt className="text-xs text-muted-foreground">Reserved</dt>
          <dd className="text-base leading-8 font-semibold text-foreground tabular-nums">
            {part.reserved}
          </dd>
        </div>
      </dl>

      <p className="text-sm text-muted-foreground">
        Reorder at{' '}
        <span className="font-medium text-foreground tabular-nums">{part.reorder_level}</span> ·{' '}
        <span className="font-medium text-foreground tabular-nums">
          {formatPKR(part.unit_price)}
        </span>{' '}
        per unit
      </p>
    </li>
  )
}

/** The row menu (spec 10 PP-03): Adjust stock (`stock.manage`) and Edit part (`parts.manage`). */
function PartActions({ part, onAdjust, onEdit }: { part: MockPart } & PartActionHandlers) {
  const menuButton = useRef<HTMLButtonElement>(null)
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          ref={menuButton}
          variant="ghost"
          size="icon"
          className="-my-1 shrink-0 text-muted-foreground"
        >
          <Ellipsis aria-hidden="true" />
          <span className="sr-only">Actions for {part.name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        {onAdjust ? (
          <DropdownMenuItem onSelect={() => onAdjust(part.id, menuButton.current)}>
            <SlidersHorizontal aria-hidden="true" />
            Adjust stock
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={() => onEdit(part.id, menuButton.current)}>
          <Pencil aria-hidden="true" />
          Edit part
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
