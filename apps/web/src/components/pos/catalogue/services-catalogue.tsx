'use client'

import { Clock, ExternalLink, Info, Plus, SearchX, Tags, TriangleAlert } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'

import { ServiceIcon } from '@/components/booking/service-icon'
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'
import { ShopNotFound } from '@/components/pos/settings/shop-not-found'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
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
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { formatPKR } from '@/lib/format'
import {
  getServices,
  getShopById,
  saveService,
  type MockService,
  type MockShop,
} from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import {
  activeNameClash,
  bookability,
  filterServices,
  formatDuration,
  serviceFromDraft,
  sortServices,
  type ServiceDraft,
  type ServiceFilter,
} from './catalogue-data'
import { ServiceSheet } from './service-sheet'

/** Keeps a 36px control's look while giving it a 44px tall touch target. */
const TALL_TARGET = 'relative after:absolute after:inset-x-0 after:-inset-y-1'

/**
 * O-03 Services catalogue (spec 10): every service of the shop, active or not, with its duration
 * and base price; add and edit in a right sheet; the Active switch hides a service from the public
 * page and the booking wizard (D34). Explains when customers can't book the shop (D64).
 */
export function ServicesCatalogue({ shopId }: { shopId: string }) {
  const ready = useMockStoreReady()
  const shop = useMockStore(() => getShopById(shopId))
  const services = useMockStore(() => getServices(shop?.id ?? shopId))

  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ServiceFilter>('all')
  const [sheet, setSheet] = useState<{ open: boolean; service: MockService | null; key: number }>({
    open: false,
    service: null,
    key: 0,
  })

  if (!ready) return <CatalogueSkeleton />
  if (!shop) return <ShopNotFound />

  const sorted = sortServices(services)
  const rows = filterServices(sorted, query, filter)
  const activeCount = services.filter((s) => s.is_active).length
  const state = bookability(shop, services)
  const publicHref = `/shops/${encodeURIComponent(shop.slug)}`

  const openSheet = (service: MockService | null) =>
    setSheet((current) => ({ open: true, service, key: current.key + 1 }))

  const clearFilters = () => {
    setQuery('')
    setFilter('all')
  }

  const handleSubmit = (draft: ServiceDraft) => {
    const editing = sheet.service
    const saved = serviceFromDraft(draft, {
      id: editing ? editing.id : `srv-${Date.now()}`,
      shopId: shop.id,
    })
    saveService(saved)
    setSheet((current) => ({ ...current, open: false }))
    if (editing) {
      toast.success(`${saved.name} saved`)
    } else {
      // Show the new row, whatever the filters were.
      clearFilters()
      toast.success(`${saved.name} added to your services`)
    }
  }

  const toggleActive = (service: MockService) => {
    const nextActive = !service.is_active
    if (nextActive) {
      const clash = activeNameClash(service.name, services, service.id)
      if (clash) {
        toast.error(
          `Another active service is already called “${clash.name}”. Rename one of them first.`,
        )
        return
      }
    }
    saveService({ ...service, is_active: nextActive })
    const othersActive = services.some((s) => s.id !== service.id && s.is_active)
    if (nextActive) toast.success(`${service.name} is active`)
    else if (!othersActive)
      toast.warning(
        `${service.name} is off. Customers can't book ${shop.name} until a service is active.`,
      )
    else toast.success(`${service.name} is off and hidden from new bookings`)
  }

  return (
    <div className="@container/catalogue space-y-6">
      <PageHeader
        eyebrow={shop.name}
        title="Services"
        description="What customers can book online, with how long each job takes and its starting price."
        actions={
          // While the list is empty, the empty state carries the one "Add service" action.
          services.length > 0 ? (
            <Button onClick={() => openSheet(null)}>
              <Plus data-icon="inline-start" aria-hidden="true" />
              Add service
            </Button>
          ) : null
        }
      />

      <BookabilityNotice state={state} shop={shop} />

      {services.length === 0 ? (
        <EmptyState
          icon={Tags}
          title="No services yet"
          description={`Customers can't book ${shop.name} until you add at least one service.`}
          action={
            <Button onClick={() => openSheet(null)}>
              <Plus data-icon="inline-start" aria-hidden="true" />
              Add service
            </Button>
          }
        />
      ) : (
        <DataTableCard
          toolbar={
            <>
              <TableSearch
                value={query}
                onValueChange={setQuery}
                label="Search services"
                placeholder="Name or description"
              />
              <ToggleGroup
                type="single"
                variant="outline"
                size="sm"
                value={filter}
                onValueChange={(value) => setFilter((value as ServiceFilter) || 'all')}
                aria-label="Show services"
              >
                <ToggleGroupItem value="all">
                  All <span className="tabular-nums">{services.length}</span>
                </ToggleGroupItem>
                <ToggleGroupItem value="active">
                  Active <span className="tabular-nums">{activeCount}</span>
                </ToggleGroupItem>
                <ToggleGroupItem value="inactive">
                  Inactive <span className="tabular-nums">{services.length - activeCount}</span>
                </ToggleGroupItem>
              </ToggleGroup>
              <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
                <span className="font-semibold text-foreground tabular-nums">{rows.length}</span>{' '}
                {rows.length === 1 ? 'service' : 'services'}
              </p>
            </>
          }
          footer={
            <>
              <p className="flex min-w-0 flex-1 basis-80 items-start gap-2">
                <Info className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
                <span>
                  Active services appear on your public page and in online booking. Turning one off
                  hides it from new bookings; bookings already made keep it.
                </span>
              </p>
              {shop.is_listed ? (
                <Link
                  href={publicHref}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-sm py-1 font-medium text-brand-blue-ink underline-offset-4 outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  View public page
                  <ExternalLink className="size-4" aria-hidden="true" />
                  <span className="sr-only"> (opens in a new tab)</span>
                </Link>
              ) : null}
            </>
          }
        >
          {rows.length === 0 ? (
            <EmptyState
              variant="inline"
              icon={SearchX}
              title="No services match"
              description={
                query.trim()
                  ? `Nothing matches “${query.trim()}”. Try another name, or clear the filters.`
                  : filter === 'inactive'
                    ? 'Every service is active.'
                    : 'Every service is turned off.'
              }
              action={
                <Button variant="outline" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <>
              <ul
                className="divide-y divide-border-faint @3xl/catalogue:hidden"
                aria-label={`Services of ${shop.name}`}
              >
                {rows.map((service) => (
                  <ServiceItem
                    key={service.id}
                    service={service}
                    onToggle={() => toggleActive(service)}
                    onEdit={() => openSheet(service)}
                  />
                ))}
              </ul>
              <div className="hidden @3xl/catalogue:block">
                <ServicesTable
                  shopName={shop.name}
                  rows={rows}
                  onToggle={toggleActive}
                  onEdit={openSheet}
                />
              </div>
            </>
          )}
        </DataTableCard>
      )}

      <ServiceSheet
        open={sheet.open}
        onOpenChange={(open) => setSheet((current) => ({ ...current, open }))}
        service={sheet.service}
        services={services}
        formKey={sheet.key}
        onSubmit={handleSubmit}
      />
    </div>
  )
}

/** D64: why customers can't book the shop right now, if they can't. */
function BookabilityNotice({
  state,
  shop,
}: {
  state: ReturnType<typeof bookability>
  shop: MockShop
}) {
  const settingsHref = `/pos/shops/${encodeURIComponent(shop.id)}/settings`
  if (state === 'no-active') {
    return (
      <Alert variant="warning" role="note">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Customers can&apos;t book {shop.name} online</AlertTitle>
        <AlertDescription>
          <p>
            Online booking needs at least one active service. Turn a service on below, or add a new
            one.
            {shop.is_listed ? null : (
              <>
                {' '}
                The shop also needs to be <Link href={settingsHref}>listed in settings</Link>.
              </>
            )}
          </p>
        </AlertDescription>
      </Alert>
    )
  }
  if (state === 'unlisted') {
    return (
      <Alert variant="info" role="note">
        <Info aria-hidden="true" />
        <AlertTitle>{shop.name} isn&apos;t listed in the shop directory</AlertTitle>
        <AlertDescription>
          <p>
            Customers can&apos;t find or book it online, so your active services stay hidden until
            you <Link href={settingsHref}>list the shop in settings</Link>.
          </p>
        </AlertDescription>
      </Alert>
    )
  }
  return null
}

function ServiceTile({ service }: { service: MockService }) {
  return (
    <span
      className={cn(
        'flex size-10 shrink-0 items-center justify-center rounded-xl',
        service.is_active
          ? 'bg-brand-blue-subtle text-brand-blue-ink'
          : 'bg-secondary text-muted-foreground',
      )}
    >
      <ServiceIcon name={service.name} className="size-5" />
    </span>
  )
}

function Price({ service }: { service: MockService }) {
  return service.base_price === null ? (
    <span className="text-muted-foreground">Price after inspection</span>
  ) : (
    <span className="font-medium text-foreground tabular-nums">
      {formatPKR(service.base_price)}
    </span>
  )
}

function ActiveSwitch({ service, onToggle }: { service: MockService; onToggle: () => void }) {
  return (
    <Switch
      checked={service.is_active}
      onCheckedChange={onToggle}
      aria-label={`Active: ${service.name}`}
    />
  )
}

function EditButton({ service, onEdit }: { service: MockService; onEdit: () => void }) {
  return (
    <Button variant="outline" size="sm" className={TALL_TARGET} onClick={onEdit}>
      Edit<span className="sr-only"> {service.name}</span>
    </Button>
  )
}

function InactiveBadge() {
  return <Badge variant="neutral">Inactive</Badge>
}

/** Phones and narrow panes: one stacked row per service (DESIGN.md §6.3). */
function ServiceItem({
  service,
  onToggle,
  onEdit,
}: {
  service: MockService
  onToggle: () => void
  onEdit: () => void
}) {
  return (
    <li className="flex gap-3 px-5 py-4">
      <ServiceTile service={service} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1 pt-0.5">
            <p
              className={cn(
                'font-semibold break-words',
                service.is_active ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              {service.name}
            </p>
            {service.is_active ? null : <InactiveBadge />}
          </div>
          <div className="pt-1">
            <ActiveSwitch service={service} onToggle={onToggle} />
          </div>
        </div>
        {service.description ? (
          <p className="mt-1 line-clamp-2 text-sm break-words text-muted-foreground">
            {service.description}
          </p>
        ) : null}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1.5 tabular-nums">
              <Clock className="size-4 text-helper" aria-hidden="true" />
              {formatDuration(service.estimated_duration_minutes)}
            </span>
            <Price service={service} />
          </p>
          <EditButton service={service} onEdit={onEdit} />
        </div>
      </div>
    </li>
  )
}

function ServicesTable({
  shopName,
  rows,
  onToggle,
  onEdit,
}: {
  shopName: string
  rows: ReadonlyArray<MockService>
  onToggle: (service: MockService) => void
  onEdit: (service: MockService) => void
}) {
  return (
    <Table>
      <TableCaption className="sr-only">Services of {shopName}</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">Service</TableHead>
          <TableHead scope="col">Duration</TableHead>
          <TableHead scope="col" className="text-right">
            Base price
          </TableHead>
          <TableHead scope="col">Active</TableHead>
          <TableHead scope="col" className="w-0">
            <span className="sr-only">Edit</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((service) => (
          <TableRow key={service.id}>
            <TableCell className="py-3 whitespace-normal">
              <div className="flex min-w-[18rem] items-start gap-3">
                <ServiceTile service={service} />
                <div className="min-w-0 space-y-0.5">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span
                      className={cn(
                        'font-semibold break-words',
                        service.is_active ? 'text-foreground' : 'text-muted-foreground',
                      )}
                    >
                      {service.name}
                    </span>
                    {service.is_active ? null : <InactiveBadge />}
                  </p>
                  {service.description ? (
                    <p className="line-clamp-2 max-w-2xl text-sm break-words text-muted-foreground">
                      {service.description}
                    </p>
                  ) : null}
                </div>
              </div>
            </TableCell>
            <TableCell className="text-muted-foreground tabular-nums">
              {formatDuration(service.estimated_duration_minutes)}
            </TableCell>
            <TableCell className="text-right">
              <Price service={service} />
            </TableCell>
            <TableCell>
              <ActiveSwitch service={service} onToggle={() => onToggle(service)} />
            </TableCell>
            <TableCell>
              <EditButton service={service} onEdit={() => onEdit(service)} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Loading state shaped like the page (DESIGN.md §6.9): header, toolbar and rows. */
function CatalogueSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-4 w-32 rounded-full" />
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-5 w-full max-w-xl" />
      </div>
      <div className="overflow-clip rounded-2xl border border-border bg-card shadow-xs">
        <div className="flex flex-wrap items-center gap-3 border-b border-border-faint px-5 py-3">
          <Skeleton className="h-10 w-full rounded-full sm:w-72" />
          <Skeleton className="h-10 w-56 rounded-full" />
        </div>
        <div className="divide-y divide-border-faint">
          {[0, 1, 2, 3, 4].map((row) => (
            <div key={row} className="flex items-center gap-3 px-5 py-4">
              <Skeleton className="size-10 shrink-0 rounded-xl" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-3.5 w-2/3" />
              </div>
              <Skeleton className="hidden h-6 w-11 rounded-full sm:block" />
            </div>
          ))}
        </div>
      </div>
      <span className="sr-only">Loading services…</span>
    </div>
  )
}
