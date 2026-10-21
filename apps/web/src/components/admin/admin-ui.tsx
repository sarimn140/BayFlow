'use client'

import { ChevronLeft, ChevronRight, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { PageHeader } from '@/components/layout/page-header'
import { StatCard } from '@/components/layout/stat-card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { AdminShop, AdminUser, AdminUserKind, StaffRole } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

/** Page title row of the console (spec 19 §5): the shared `PageHeader`. */
export function AdminPageHeader({
  title,
  description,
  back,
  actions,
  badges,
}: {
  title: string
  description?: ReactNode
  back?: { href: string; label: string }
  actions?: ReactNode
  badges?: ReactNode
}) {
  return (
    <PageHeader
      title={title}
      description={description}
      back={back}
      actions={actions}
      badges={badges}
    />
  )
}

/** A white card with a title row (DESIGN.md "Cards"). */
export function Tile({
  title,
  description,
  actions,
  children,
  className,
  flush = false,
}: {
  title?: string
  description?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
  /** No inner padding (tables and lists run edge to edge). */
  flush?: boolean
}) {
  return (
    <section
      className={cn(
        'overflow-clip rounded-2xl border border-border bg-card text-sm shadow-xs',
        className,
      )}
    >
      {title && (
        <div className="flex items-start justify-between gap-3 px-5 pt-5 pb-4">
          <div className="min-w-0">
            <h2 className="text-lg leading-7 font-semibold text-foreground">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={flush ? undefined : cn('px-5 pb-5', !title && 'pt-5')}>{children}</div>
    </section>
  )
}

/** KPI card of the console: the shared `StatCard` ("attention" maps to its warning tone). */
export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = 'default',
}: {
  label: string
  value: number | string
  hint?: string
  icon: LucideIcon
  tone?: 'default' | 'attention' | 'danger'
}) {
  return (
    <StatCard
      label={label}
      value={value}
      hint={hint}
      icon={icon}
      tone={tone === 'attention' ? 'warning' : tone === 'danger' ? 'danger' : 'brand'}
    />
  )
}

/** Client-side paging over an already filtered list (E-6x lists page server-side once wired). */
export function usePaged<T>(items: ReadonlyArray<T>, pageSize = 20) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / pageSize))
  const current = Math.min(page, pages - 1)
  return {
    rows: items.slice(current * pageSize, (current + 1) * pageSize),
    pager: (
      <Pager
        page={current}
        pages={pages}
        total={items.length}
        pageSize={pageSize}
        onPage={setPage}
      />
    ),
    reset: () => setPage(0),
  }
}

function Pager({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number
  pages: number
  total: number
  pageSize: number
  onPage: (page: number) => void
}) {
  if (total === 0) return null
  const from = page * pageSize + 1
  const to = Math.min(total, (page + 1) * pageSize)
  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-between gap-3 border-t border-border-faint px-5 py-3 text-sm text-muted-foreground"
    >
      <span className="tabular-nums">
        {from}–{to} of {total}
      </span>
      <span className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Previous page"
          disabled={page === 0}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft aria-hidden="true" />
        </Button>
        <span className="px-2 tabular-nums">
          {page + 1} / {pages}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label="Next page"
          disabled={page >= pages - 1}
          onClick={() => onPage(page + 1)}
        >
          <ChevronRight aria-hidden="true" />
        </Button>
      </span>
    </nav>
  )
}

export function ShopStatusBadges({ tenant }: { tenant: AdminShop }) {
  return (
    <>
      {tenant.suspension ? (
        <Badge variant="destructive">Suspended</Badge>
      ) : (
        <Badge variant="success">Active</Badge>
      )}
      {!tenant.shop.is_listed && <Badge variant="neutral">Unlisted</Badge>}
    </>
  )
}

export function UserStatusBadge({ user }: { user: Pick<AdminUser, 'isActive'> }) {
  return user.isActive ? (
    <Badge variant="success">Active</Badge>
  ) : (
    <Badge variant="destructive">Deactivated</Badge>
  )
}

const KIND_LABEL: Record<AdminUserKind, string> = {
  CUSTOMER: 'Customer',
  STAFF: 'Staff',
  PLATFORM_ADMIN: 'Platform admin',
}

const KIND_VARIANT = {
  PLATFORM_ADMIN: 'attention',
  STAFF: 'brand',
  CUSTOMER: 'neutral',
} as const satisfies Record<AdminUserKind, string>

export function KindBadge({ kind }: { kind: AdminUserKind }) {
  return <Badge variant={KIND_VARIANT[kind]}>{KIND_LABEL[kind]}</Badge>
}

export const ROLE_LABEL: Record<StaffRole, string> = {
  OWNER: 'Owner',
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}
