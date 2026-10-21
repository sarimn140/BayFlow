'use client'

import {
  CalendarCheck,
  ChevronRight,
  Copy,
  KeyRound,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Store,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { Fragment, useId, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { EmptyState } from '@/components/layout/empty-state'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useNowMinute } from '@/hooks/use-now'
import { formatDateTime, formatRelative } from '@/lib/format'
import type { AuditCategory, AuditEvent } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

export const CATEGORY_LABEL: Record<AuditCategory, string> = {
  AUTH: 'Sign-in',
  USER: 'Account',
  SHOP: 'Shop',
  MEMBERSHIP: 'Team',
  BOOKING: 'Booking',
  ADMIN: 'Admin',
}

/** One icon per category, so a long log can be scanned without relying on colour. */
const CATEGORY_ICON: Record<AuditCategory, LucideIcon> = {
  AUTH: KeyRound,
  USER: UserCog,
  SHOP: Store,
  MEMBERSHIP: Users,
  BOOKING: CalendarCheck,
  ADMIN: ShieldCheck,
}

const ROLE_NAME: Record<string, string> = {
  PLATFORM_ADMIN: 'Platform admin',
  OWNER: 'Owner',
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
  CUSTOMER: 'Customer',
  SYSTEM: 'System',
  ANONYMOUS: 'Anonymous',
}

const TARGET_NAME: Record<NonNullable<AuditEvent['target']>['type'], string> = {
  USER: 'Account',
  SHOP: 'Shop',
  MEMBERSHIP: 'Team membership',
  BOOKING: 'Booking',
}

/** Security-relevant events get a red marker in lists. */
export const isAlert = (event: AuditEvent) =>
  event.action === 'auth.login_failed' ||
  event.action === 'auth.login_rate_limited' ||
  event.action === 'shop.suspended' ||
  event.action === 'user.deactivated'

/** Why a security event matters, shown at the top of its detail sheet. */
const ALERT_NOTE: Record<string, string> = {
  'auth.login_failed':
    'A sign-in failed. Several in a row from one address can mean someone is guessing a password.',
  'auth.login_rate_limited': 'Sign-ins from this address were paused after too many attempts.',
  'shop.suspended': 'A shop was suspended: hidden from customers and closed to its staff.',
  'user.deactivated': "An account was deactivated: the person can't sign in any more.",
}

/** Admin actions get the brand tint, security events red, everything else a neutral tile. */
function tileTone(event: AuditEvent): string {
  if (isAlert(event)) return 'bg-danger-subtle text-danger-ink'
  if (event.category === 'ADMIN') return 'bg-brand-blue-subtle text-brand-blue-ink'
  return 'bg-secondary text-muted-foreground'
}

export function CategoryBadge({ category }: { category: AuditCategory }) {
  const Icon = CATEGORY_ICON[category]
  return (
    <Badge variant={category === 'ADMIN' ? 'brand' : 'secondary'}>
      <Icon aria-hidden="true" data-icon="inline-start" />
      {CATEGORY_LABEL[category]}
    </Badge>
  )
}

function Dot({ className }: { className?: string }) {
  return (
    <span aria-hidden="true" className={cn('text-subtle-foreground', className)}>
      ·
    </span>
  )
}

/** The summary, with booking references (BF-2026-002) kept on one line. */
function Summary({ text }: { text: string }) {
  return text.split(/(BF-\d{4}-\d+)/).map((part, index) =>
    index % 2 === 1 ? (
      <span key={index} className="whitespace-nowrap">
        {part}
      </span>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  )
}

function EventRow({
  event,
  nowIso,
  showShop,
  onOpen,
}: {
  event: AuditEvent
  nowIso: string | null
  showShop: boolean
  onOpen: (opener: HTMLButtonElement) => void
}) {
  const alert = isAlert(event)
  const Icon = alert ? ShieldAlert : CATEGORY_ICON[event.category]
  const when = nowIso ? formatRelative(event.occurredAt, new Date(nowIso)) : ''
  return (
    <li>
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={(click) => onOpen(click.currentTarget)}
        // Rows line up with the padding of the card around them (20/24px in a Card, 20px elsewhere).
        className="group flex w-full items-start gap-3 px-[var(--card-spacing,1.25rem)] py-3 text-left transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
      >
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-xl',
            tileTone(event),
          )}
        >
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-start justify-between gap-3">
            <span className="min-w-0 pt-0.5 text-sm font-medium text-foreground">
              {alert ? <span className="sr-only">Security event: </span> : null}
              <Summary text={event.summary} />
            </span>
            {/* Wide lists: the time on the right. Narrow ones: first in the line below. */}
            <time
              dateTime={event.occurredAt}
              className="hidden shrink-0 pt-1 text-xs whitespace-nowrap text-helper tabular-nums @md/events:block"
            >
              {when}
            </time>
          </span>
          {/* Narrow lists keep one line here; the action and IP stay in the detail sheet. */}
          <span className="mt-1 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-helper">
            <time
              dateTime={event.occurredAt}
              className="whitespace-nowrap tabular-nums @md/events:hidden"
            >
              {when}
            </time>
            <Dot className="@md/events:hidden" />
            <span>{CATEGORY_LABEL[event.category]}</span>
            <Dot className="hidden @md/events:inline" />
            <span className="hidden font-mono break-all @md/events:inline">{event.action}</span>
            {showShop && event.shop ? (
              <>
                <Dot />
                <span>{event.shop.name}</span>
              </>
            ) : null}
            {event.ip ? (
              <>
                <Dot className="hidden @md/events:inline" />
                <span className="hidden font-mono @md/events:inline">{event.ip}</span>
              </>
            ) : null}
          </span>
        </span>
        <ChevronRight
          className="mt-2.5 size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </button>
    </li>
  )
}

/**
 * Audit events, newest first; a row opens the detail sheet. Put it straight into a flush card
 * (`<Card className="gap-0 py-0">` after a `border-b` header) or a `DataTableCard`: the rows run
 * edge to edge and inset their content by the card's own padding (`--card-spacing`, 20px when
 * there is none). Inside an already padded box, pass `className="[--card-spacing:0px]"`.
 */
export function AuditEventList({
  events,
  empty = 'No events yet.',
  showShop = true,
  className,
}: {
  events: ReadonlyArray<AuditEvent>
  empty?: string
  showShop?: boolean
  /** Classes for the list (or its empty state), e.g. to change the row inset. */
  className?: string
}) {
  // The sheet keeps the last event while it slides out, and focus goes back to the row that
  // opened it (the sheet has no trigger of its own).
  const [selected, setSelected] = useState<AuditEvent | null>(null)
  const [open, setOpen] = useState(false)
  const opener = useRef<HTMLButtonElement | null>(null)
  const nowIso = useNowMinute()

  if (events.length === 0) {
    return (
      <EmptyState
        variant="inline"
        tone="neutral"
        icon={ScrollText}
        title={empty}
        className={cn('p-6 sm:p-8', className)}
      />
    )
  }

  return (
    <>
      <ul className={cn('@container/events divide-y divide-border-faint', className)}>
        {events.map((event) => (
          <EventRow
            key={event.id}
            event={event}
            nowIso={nowIso}
            showShop={showShop}
            onOpen={(button) => {
              opener.current = button
              setSelected(event)
              setOpen(true)
            }}
          />
        ))}
      </ul>
      <EventSheet
        event={selected}
        open={open}
        onOpenChange={setOpen}
        onCloseAutoFocus={(focusEvent) => {
          focusEvent.preventDefault()
          opener.current?.focus()
        }}
      />
    </>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-4 py-3 text-sm first:pt-0 last:pb-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-foreground">{children}</dd>
    </div>
  )
}

function None() {
  return <span className="text-muted-foreground">—</span>
}

function targetHref(event: AuditEvent): string | null {
  if (!event.target) return null
  switch (event.target.type) {
    case 'USER':
      return `/admin/users/${event.target.id}`
    case 'SHOP':
      return `/admin/shops/${event.target.id}`
    case 'BOOKING':
      return `/admin/bookings/${event.target.id}`
    case 'MEMBERSHIP':
      return event.shop ? `/admin/shops/${event.shop.id}` : null
  }
}

function copyDetails(json: string) {
  if (!navigator.clipboard) {
    toast.error("Couldn't copy. Select the text instead.")
    return
  }
  navigator.clipboard.writeText(json).then(
    () => toast.success('Details copied'),
    () => toast.error("Couldn't copy. Select the text instead."),
  )
}

/** The detail sheet of one event: who, where, what, from which device, and the raw metadata. */
function EventSheet({
  event,
  open,
  onOpenChange,
  onCloseAutoFocus,
}: {
  event: AuditEvent | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onCloseAutoFocus?: (event: Event) => void
}) {
  const href = event ? targetHref(event) : null
  const json = event ? JSON.stringify(event.metadata, null, 2) : ''
  // The sheet is read-only, so it opens on its title (WAI-ARIA dialog pattern), not on "Copy".
  const title = useRef<HTMLHeadingElement>(null)
  const detailsId = useId()
  return (
    <Sheet open={open && event !== null} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="gap-0"
        onOpenAutoFocus={(focusEvent) => {
          focusEvent.preventDefault()
          title.current?.focus()
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        {event ? (
          <>
            <SheetHeader className="border-b border-border-faint">
              <div className="flex flex-wrap items-center gap-2">
                <CategoryBadge category={event.category} />
                {isAlert(event) ? (
                  <Badge variant="destructive">
                    <ShieldAlert aria-hidden="true" data-icon="inline-start" />
                    Security
                  </Badge>
                ) : null}
              </div>
              <SheetTitle ref={title} tabIndex={-1} className="mt-1 outline-none">
                {event.summary}
              </SheetTitle>
              <SheetDescription>
                <time dateTime={event.occurredAt}>{formatDateTime(event.occurredAt)}</time>{' '}
                (Asia/Karachi)
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-6 p-6">
              {isAlert(event) && ALERT_NOTE[event.action] ? (
                <Alert variant="destructive" role="note">
                  <ShieldAlert aria-hidden="true" />
                  <AlertTitle>Security event</AlertTitle>
                  <AlertDescription>{ALERT_NOTE[event.action]}</AlertDescription>
                </Alert>
              ) : null}

              <dl className="divide-y divide-border-faint">
                <Fact label="Action">
                  <span className="font-mono text-xs">{event.action}</span>
                </Fact>
                <Fact label="Actor">
                  {event.actor ? (
                    <>
                      <span className="font-medium">{event.actor.name}</span>
                      <span className="block text-muted-foreground">
                        {[event.actor.email, ROLE_NAME[event.actor.role] ?? event.actor.role]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </>
                  ) : (
                    <span className="text-muted-foreground">Anonymous</span>
                  )}
                </Fact>
                <Fact label="Shop">{event.shop?.name ?? <None />}</Fact>
                <Fact label="Target">
                  {event.target ? (
                    <>
                      {href ? (
                        <Link
                          href={href}
                          onClick={() => onOpenChange(false)}
                          className="rounded-sm font-medium text-brand-blue-ink outline-none hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                        >
                          {event.target.label}
                        </Link>
                      ) : (
                        <span className="font-medium">{event.target.label}</span>
                      )}
                      <span className="block text-muted-foreground">
                        {TARGET_NAME[event.target.type]}
                      </span>
                    </>
                  ) : (
                    <None />
                  )}
                </Fact>
                <Fact label="IP address">
                  {event.ip ? <span className="font-mono text-xs">{event.ip}</span> : <None />}
                </Fact>
                <Fact label="Device">{event.userAgent ?? <None />}</Fact>
                <Fact label="Request ID">
                  {event.requestId ? (
                    <span className="font-mono text-xs">{event.requestId}</span>
                  ) : (
                    <None />
                  )}
                </Fact>
                <Fact label="Event ID">
                  <span className="font-mono text-xs">{event.id}</span>
                </Fact>
              </dl>

              <section aria-labelledby={detailsId} className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <h3 id={detailsId} className="text-base font-semibold text-foreground">
                    Details
                  </h3>
                  <Button variant="ghost" size="xs" onClick={() => copyDetails(json)}>
                    <Copy aria-hidden="true" />
                    Copy JSON
                  </Button>
                </div>
                <pre
                  tabIndex={0}
                  aria-label="Event details as JSON"
                  className="max-h-80 overflow-auto rounded-xl border border-border-faint bg-muted p-4 font-mono text-xs leading-relaxed text-foreground outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
                >
                  {json}
                </pre>
              </section>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

/** One event's detail sheet, opened from outside a list (`event` null closes it). */
export function AuditEventSheet({
  event,
  onClose,
}: {
  event: AuditEvent | null
  onClose: () => void
}) {
  return (
    <EventSheet event={event} open={event !== null} onOpenChange={(next) => !next && onClose()} />
  )
}
