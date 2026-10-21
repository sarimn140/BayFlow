import { CalendarX2, ChevronRight, Lock, Store } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { ROLE_LABEL } from '@/components/admin/admin-ui'
import { AuditEventList } from '@/components/admin/audit-events'
import { slotLabel, vehicleLabel } from '@/components/admin/bookings/slot'
import { EmptyState } from '@/components/layout/empty-state'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { formatDate, formatDateTime } from '@/lib/format'
import type { AdminMembership, AdminShop, AdminUser, AuditEvent } from '@/lib/mock-admin'
import type { MockBooking } from '@/lib/mock-data'

const ROW_LINK =
  'group flex items-center gap-3 px-(--card-spacing) py-3.5 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

function CardHeading({ children }: { children: ReactNode }) {
  return <h2 className="text-lg leading-7 font-semibold text-foreground">{children}</h2>
}

function RowChevron() {
  return (
    <ChevronRight
      className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
      aria-hidden="true"
    />
  )
}

/**
 * One account lever (spec 19 §5 A-05): what it is, where it stands, the button that opens its
 * confirmation, and, when the lever is blocked (self, last admin, inactive account), why.
 */
export function AccessItem({
  title,
  state,
  description,
  control,
  blockedReason,
  reasonId,
}: {
  title: string
  state: ReactNode
  description: string
  control: ReactNode
  blockedReason?: string | null
  reasonId: string
}) {
  return (
    <section className="space-y-3 py-5 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {state}
      </div>
      {control}
      {blockedReason ? (
        <p id={reasonId} className="flex items-start gap-2 text-sm text-muted-foreground">
          <Lock className="mt-0.5 size-4 shrink-0 text-helper" aria-hidden="true" />
          {blockedReason}
        </p>
      ) : null}
    </section>
  )
}

/** The account levers: platform admin access and sign-in. Every change is audited (D95). */
export function AccessCard({ children }: { children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>Access</CardHeading>
        <CardDescription>Every change is recorded in the audit log.</CardDescription>
      </CardHeader>
      <CardContent className="gap-0 divide-y divide-border-faint">{children}</CardContent>
    </Card>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right font-medium break-words text-foreground">{children}</dd>
    </div>
  )
}

/** Contact details and account facts. */
export function ProfileCard({ person }: { person: AdminUser }) {
  return (
    <Card>
      <CardHeader>
        <CardHeading>Profile</CardHeading>
      </CardHeader>
      <CardContent>
        <dl className="divide-y divide-border-faint text-sm">
          <Fact label="E-mail">
            <span className="break-all">{person.email}</span>
          </Fact>
          <Fact label="Phone">
            {person.phone ?? <span className="font-normal text-muted-foreground">Not given</span>}
          </Fact>
          <Fact label="Last sign-in">
            {person.lastLoginAt ? (
              <time dateTime={person.lastLoginAt}>{formatDateTime(person.lastLoginAt)}</time>
            ) : (
              <span className="font-normal text-muted-foreground">Never</span>
            )}
          </Fact>
          <Fact label="Joined">
            <time dateTime={person.createdAt}>{formatDate(person.createdAt)}</time>
          </Fact>
          <Fact label="Account ID">
            <span className="font-mono text-xs">{person.id}</span>
          </Fact>
        </dl>
      </CardContent>
    </Card>
  )
}

/** The shops this person belongs to and their role in each; a row opens the shop (A-03). */
export function MembershipsCard({
  memberships,
  tenants,
}: {
  memberships: ReadonlyArray<AdminMembership>
  tenants: ReadonlyArray<AdminShop>
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Shop memberships</CardHeading>
        <CardDescription>
          {memberships.length === 0
            ? 'Shops and roles'
            : `${memberships.length} ${memberships.length === 1 ? 'shop' : 'shops'}`}
        </CardDescription>
      </CardHeader>
      {memberships.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={Store}
          title="Not a member of any shop"
          description="Shop owners add their staff from the POS."
          className="p-6 sm:p-8"
        />
      ) : (
        <ul className="divide-y divide-border-faint">
          {memberships.map((m) => {
            const suspended = Boolean(tenants.find((t) => t.shop.id === m.shopId)?.suspension)
            return (
              <li key={m.shopId}>
                <Link href={`/admin/shops/${m.shopId}`} className={ROW_LINK}>
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink">
                    <Store className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-foreground">
                      {m.shopName}
                    </span>
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      <Badge variant="brand">{ROLE_LABEL[m.role]}</Badge>
                      {m.isActive ? null : <Badge variant="neutral">Inactive</Badge>}
                      {suspended ? <Badge variant="destructive">Shop suspended</Badge> : null}
                    </span>
                  </span>
                  <RowChevron />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

/** Bookings made with this person's e-mail, newest first; a row opens the booking (A-07). */
export function CustomerBookingsCard({
  bookings,
  limit = 6,
}: {
  bookings: ReadonlyArray<MockBooking>
  limit?: number
}) {
  const shown = bookings.slice(0, limit)
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Bookings as a customer</CardHeading>
        <CardDescription>
          {bookings.length} in total
          {bookings.length > shown.length ? ` · the latest ${shown.length}` : ''}
        </CardDescription>
      </CardHeader>
      {bookings.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={CalendarX2}
          title="No bookings as a customer"
          description="Bookings made with this e-mail address appear here."
          className="p-6 sm:p-8"
        />
      ) : (
        <ul className="divide-y divide-border-faint">
          {shown.map((b) => (
            <li key={b.id}>
              <Link href={`/admin/bookings/${b.id}`} className={ROW_LINK}>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-mono text-sm font-semibold text-brand-blue-ink">
                      {b.reference}
                    </span>
                    <StatusBadge status={b.status} audience="staff" />
                  </div>
                  <p className="truncate text-sm text-foreground">
                    {b.shopName} · {vehicleLabel(b)}
                  </p>
                  <p className="text-xs text-helper">{slotLabel(b)}</p>
                </div>
                <RowChevron />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/** What this person did, and what was done to their account (the latest `limit` events). */
export function AuditTrailCard({
  events,
  limit = 25,
}: {
  events: ReadonlyArray<AuditEvent>
  limit?: number
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Audit trail</CardHeading>
        <CardDescription>
          What this person did, and what was done to their account
          {events.length > limit ? ` · the latest ${limit} of ${events.length}` : ''}
        </CardDescription>
      </CardHeader>
      <AuditEventList events={events.slice(0, limit)} empty="Nothing recorded yet." />
    </Card>
  )
}
