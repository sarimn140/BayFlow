'use client'

import { SearchX, Search, X } from 'lucide-react'
import { useState } from 'react'

import { ShopCard } from '@/components/booking/shop-card'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { useNowMinute } from '@/hooks/use-now'
import { getShopSuspensions } from '@/lib/mock-admin'
import { getServices, getShops } from '@/lib/mock-data'

const ALL = 'all'

/**
 * W1 · Shop (spec 10 P-03): the bookable shops, searchable by name, area or street and filtered
 * by city. A shop must be listed, not suspended (D96) and have an active service (D64).
 */
export function ShopDirectory() {
  const ready = useMockStoreReady()
  const shops = useMockStore(getShops)
  const services = useMockStore(() => getServices())
  const suspensions = useMockStore(getShopSuspensions)
  const nowIso = useNowMinute()

  const [query, setQuery] = useState('')
  const [city, setCity] = useState(ALL)

  const bookable = shops
    .filter((shop) => shop.is_listed && !suspensions[shop.id])
    .map((shop) => ({
      shop,
      services: services.filter((s) => s.shopId === shop.id && s.is_active),
    }))
    .filter((entry) => entry.services.length > 0)

  const cities = [...new Set(bookable.map((entry) => entry.shop.city))].sort()
  const needle = query.trim().toLowerCase()
  const results = bookable.filter(({ shop }) => {
    if (city !== ALL && shop.city !== city) return false
    if (!needle) return true
    return [shop.name, shop.city, shop.address].some((field) =>
      field.toLowerCase().includes(needle),
    )
  })

  const reset = () => {
    setQuery('')
    setCity(ALL)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <InputGroup className="h-12 rounded-full border-border bg-card px-2 shadow-sm lg:max-w-md">
          <InputGroupAddon>
            <Search aria-hidden />
          </InputGroupAddon>
          <InputGroupInput
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by workshop, area or street"
            aria-label="Search workshops"
            className="text-base [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton
                size="icon-xs"
                className="rounded-full"
                aria-label="Clear search"
                onClick={() => setQuery('')}
              >
                <X />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>

        <ToggleGroup
          type="single"
          value={city}
          onValueChange={(value) => setCity(value || ALL)}
          aria-label="Filter by city"
          className="flex flex-wrap gap-2"
        >
          {[ALL, ...cities].map((value) => (
            <ToggleGroupItem
              key={value}
              value={value}
              className="h-9 rounded-full! border border-border bg-card px-4 text-sm font-medium text-muted-foreground shadow-none hover:border-brand-blue/40 hover:text-foreground data-[state=on]:border-brand-blue data-[state=on]:bg-brand-blue data-[state=on]:text-white"
            >
              {value === ALL ? 'All cities' : value}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <p className="text-sm text-muted-foreground" aria-live="polite">
        {ready ? (
          <>
            <span className="font-semibold text-foreground">{results.length}</span>{' '}
            {results.length === 1 ? 'workshop' : 'workshops'}
            {city !== ALL && ` in ${city}`} taking online bookings
          </>
        ) : (
          'Loading workshops…'
        )}
      </p>

      {!ready ? (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <div key={key} className="overflow-hidden rounded-3xl border border-border bg-card">
              <Skeleton className="aspect-[16/10] rounded-none" />
              <div className="space-y-3 p-5">
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-8 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : results.length === 0 ? (
        <Empty className="rounded-3xl border border-dashed border-border bg-card py-14">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <SearchX />
            </EmptyMedia>
            <EmptyTitle>No workshops match</EmptyTitle>
            <EmptyDescription>
              Try another area or street, or show workshops in every city.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant="outline" className="rounded-full" onClick={reset}>
              Clear filters
            </Button>
          </EmptyContent>
        </Empty>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {results.map(({ shop, services: shopServices }, index) => (
            <ShopCard
              key={shop.id}
              shop={shop}
              services={shopServices}
              nowIso={nowIso}
              priority={index < 3}
            />
          ))}
        </div>
      )}
    </div>
  )
}
