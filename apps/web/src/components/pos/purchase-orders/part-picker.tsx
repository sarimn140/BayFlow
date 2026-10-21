'use client'

import { ChevronsUpDown } from 'lucide-react'
import { useId, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import type { MockPart } from '@/lib/mock-data'

import { availableStock, formatCount, stockState } from './po-model'

/** The field look of `SelectTrigger` (42px+, 12px corners, stone edge, blue border + halo on focus). */
const TRIGGER =
  'flex min-h-14 w-full items-center gap-3 rounded-lg border border-input bg-card py-2 pr-3 pl-3.5 text-left text-sm text-foreground shadow-xs transition-[border-color,box-shadow] duration-150 ease-out outline-none focus-visible:border-brand-blue focus-visible:ring-4 focus-visible:ring-brand-blue/15 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60 aria-expanded:border-brand-blue aria-expanded:ring-4 aria-expanded:ring-brand-blue/15'

/** Low / Out chip (D45); nothing while the part is in stock. */
export function StockBadge({ part }: { part: MockPart }) {
  const state = stockState(part)
  if (state === 'ok') return null
  return state === 'out' ? (
    <Badge variant="destructive">Out of stock</Badge>
  ) : (
    <Badge variant="warning">Low</Badge>
  )
}

function PartLines({ part }: { part: MockPart }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate font-medium text-foreground">{part.name}</span>
      <span className="block truncate text-xs text-muted-foreground tabular-nums">
        <span className="font-mono">{part.sku}</span> · {formatCount(availableStock(part))}{' '}
        available
      </span>
    </span>
  )
}

/** cmdk filters on this text, so a search finds a part by its name or its SKU. */
function searchText(part: MockPart): string {
  return `${part.name} ${part.sku}`
}

/**
 * Searchable part picker for the new purchase order (spec 10 PP-04, spec 09 §3.12: `Popover` +
 * `Command`): each part with its SKU, what is available now and a Low / Out chip. The trigger is
 * named by the field label plus the chosen part.
 */
export function PartPicker({
  id,
  labelId,
  parts,
  value,
  onChange,
}: {
  id: string
  /** The visible label's id ("Part"). */
  labelId: string
  parts: ReadonlyArray<MockPart>
  /** The chosen part's SKU. */
  value: string
  onChange: (sku: string) => void
}) {
  const [open, setOpen] = useState(false)
  const valueId = useId()
  const popupId = useId()
  const selected = parts.find((part) => part.sku === value)

  return (
    <Popover open={open} onOpenChange={setOpen} modal>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-controls={open ? popupId : undefined}
          aria-labelledby={`${labelId} ${valueId}`}
          disabled={parts.length === 0}
          className={TRIGGER}
        >
          <span id={valueId} className="flex min-w-0 flex-1 items-center gap-3">
            {selected ? (
              <PartLines part={selected} />
            ) : (
              <span className="flex-1 text-helper">
                {parts.length === 0 ? 'No parts in inventory yet' : 'Choose a part'}
              </span>
            )}
          </span>
          {selected ? <StockBadge part={selected} /> : null}
          <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        id={popupId}
        align="start"
        className="w-(--radix-popover-trigger-width) gap-0 p-0"
      >
        <Command label="Search parts" defaultValue={selected ? searchText(selected) : undefined}>
          <CommandInput placeholder="Search by name or SKU" />
          {/* 20rem: a sixth part peeks out below the fifth, so the list reads as scrollable. */}
          <CommandList className="max-h-80">
            <CommandEmpty>No parts match that search.</CommandEmpty>
            <CommandGroup>
              {parts.map((part) => (
                <CommandItem
                  key={part.id}
                  value={searchText(part)}
                  data-checked={part.sku === value}
                  onSelect={() => {
                    onChange(part.sku)
                    setOpen(false)
                  }}
                  className="gap-3 py-2.5"
                >
                  <PartLines part={part} />
                  <StockBadge part={part} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
