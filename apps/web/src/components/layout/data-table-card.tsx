'use client'

import { Search, X } from 'lucide-react'
import type { ComponentProps, ReactNode } from 'react'

import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { cn } from '@/lib/utils'

export interface DataTableCardProps {
  /** Card title (an `<h2>`); leave out when the page header already names the list. */
  title?: ReactNode
  description?: ReactNode
  /** Buttons on the right of the title row. */
  actions?: ReactNode
  /** The toolbar row under the title: `TableSearch`, filter pills, a result count. */
  toolbar?: ReactNode
  /** The pager row ("1–20 of 312" and the arrows). */
  footer?: ReactNode
  /** The `<Table>` (flush to the card edges), or the stacked mobile list, or an `EmptyState`. */
  children: ReactNode
  className?: string
}

/**
 * Data table card (DESIGN.md "Data tables"): a white rounded card that clips the table to its
 * corners, with an optional title row, toolbar and pager footer.
 */
export function DataTableCard({
  title,
  description,
  actions,
  toolbar,
  footer,
  children,
  className,
}: DataTableCardProps) {
  const hasHeader = Boolean(title || description || actions)
  return (
    <section
      className={cn(
        'overflow-clip rounded-2xl border border-border bg-card text-sm shadow-xs',
        className,
      )}
    >
      {hasHeader ? (
        <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 pb-4">
          <div className="min-w-0 space-y-0.5">
            {title ? (
              <h2 className="text-lg leading-7 font-semibold text-foreground">{title}</h2>
            ) : null}
            {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {toolbar ? (
        <div
          data-slot="table-toolbar"
          className={cn(
            'flex flex-col gap-3 border-b border-border-faint px-5 py-3 max-sm:*:data-[slot=button]:self-start sm:flex-row sm:flex-wrap sm:items-center',
            // One control height for the whole row, at the 40px touch-target minimum: the search,
            // filter pills, selects and small buttons line up whatever size the page asked for.
            '[&_:is(button,a)[data-size=default]]:h-10 [&_:is(button,a)[data-size=sm]]:h-10 [&_[data-slot=input-group]]:h-10 [&_[data-slot=native-select]]:h-10 [&_[data-slot=select-trigger]]:h-10 [&_[data-slot=toggle-group-item]]:h-10',
            hasHeader && 'border-t',
          )}
        >
          {toolbar}
        </div>
      ) : null}
      {children}
      {footer ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-faint px-5 py-3 text-sm text-muted-foreground">
          {footer}
        </div>
      ) : null}
    </section>
  )
}

/** Spec 09 §2.10: a search box (`q`) takes at most 100 characters. */
export const SEARCH_MAX_LENGTH = 100

export interface TableSearchProps extends Omit<
  ComponentProps<'input'>,
  'value' | 'onChange' | 'type' | 'className'
> {
  value: string
  onValueChange: (value: string) => void
  /** Accessible name, e.g. "Search bookings". */
  label: string
  placeholder?: string
  /** Defaults to 100 (spec 09 §2.10). */
  maxLength?: number
  /** On the pill (width, flex), not the input. Other props go to the `<input>`. */
  className?: string
}

/** The toolbar's search field: a 40px pill with a search icon and a clear button. */
export function TableSearch({
  value,
  onValueChange,
  label,
  placeholder,
  maxLength = SEARCH_MAX_LENGTH,
  className,
  ...inputProps
}: TableSearchProps) {
  return (
    <InputGroup className={cn('h-10 rounded-full sm:w-72', className)}>
      <InputGroupAddon>
        <Search aria-hidden="true" />
      </InputGroupAddon>
      <InputGroupInput
        {...inputProps}
        type="search"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-label={label}
        // The clear button below replaces the browser's own, which would show a second ✕.
        className="[&::-webkit-search-cancel-button]:hidden"
      />
      {value ? (
        <InputGroupAddon align="inline-end">
          {/* 32px, with a 40px hit area. */}
          <InputGroupButton
            size="icon-sm"
            aria-label="Clear search"
            onClick={() => onValueChange('')}
            className="relative after:absolute after:-inset-1"
          >
            <X />
          </InputGroupButton>
        </InputGroupAddon>
      ) : null}
    </InputGroup>
  )
}
