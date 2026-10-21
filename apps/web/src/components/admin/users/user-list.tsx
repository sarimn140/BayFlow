import { ChevronRight } from 'lucide-react'
import Link from 'next/link'

import { KindBadge, ROLE_LABEL, UserStatusBadge, initials } from '@/components/admin/admin-ui'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDate, formatDateTime, formatRelative } from '@/lib/format'
import type { AdminMembership, AdminUser } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

const LINK_FOCUS =
  'rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid'

/** Initials on a soft tile; grey for a deactivated account. Decorative: the name is beside it. */
export function UserAvatar({
  user,
  className,
}: {
  user: Pick<AdminUser, 'name' | 'isActive'>
  className?: string
}) {
  return (
    <Avatar aria-hidden="true" className={cn('size-9 after:hidden', className)}>
      <AvatarFallback
        className={cn(
          'text-xs font-semibold',
          user.isActive
            ? 'bg-brand-blue-subtle text-brand-blue-ink'
            : 'bg-secondary text-muted-foreground',
        )}
      >
        {initials(user.name)}
      </AvatarFallback>
    </Avatar>
  )
}

/** "Owner · Lahore Auto Care", one line per shop; an inactive membership says so. */
function Memberships({ memberships }: { memberships: ReadonlyArray<AdminMembership> }) {
  if (memberships.length === 0) {
    return (
      <>
        <span aria-hidden="true" className="text-helper">
          —
        </span>
        <span className="sr-only">No shop memberships</span>
      </>
    )
  }
  return (
    <ul className="space-y-0.5">
      {memberships.map((m) => (
        <li key={m.shopId} className={cn(!m.isActive && 'text-muted-foreground')}>
          <span className="font-medium">{ROLE_LABEL[m.role]}</span>
          <span className="text-muted-foreground"> · {m.shopName}</span>
          {m.isActive ? null : <span className="text-helper"> (inactive)</span>}
        </li>
      ))}
    </ul>
  )
}

function LastSignIn({ at, nowIso }: { at: string | null; nowIso: string | null }) {
  if (!at) return <span className="text-helper">Never</span>
  return (
    <time dateTime={at} title={formatDateTime(at)}>
      {nowIso ? formatRelative(at, new Date(nowIso)) : ''}
    </time>
  )
}

/** Wide screens: one row per account (spec 19 §5 A-04). The name opens A-05. */
export function UsersTable({
  users,
  nowIso,
}: {
  users: ReadonlyArray<AdminUser>
  nowIso: string | null
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Memberships</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Last sign-in</TableHead>
          <TableHead>Joined</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((u) => (
          <TableRow key={u.id}>
            {/* The kind chip sits beside the name, so the table fits a laptop screen. */}
            <TableCell className="py-2.5">
              <div className="flex items-center gap-3">
                <UserAvatar user={u} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/admin/users/${u.id}`}
                      className={cn(
                        'font-semibold text-brand-blue-ink hover:underline',
                        LINK_FOCUS,
                      )}
                    >
                      {u.name}
                    </Link>
                    <KindBadge kind={u.kind} />
                  </div>
                  <p className="text-xs text-helper">{u.email}</p>
                </div>
              </div>
            </TableCell>
            <TableCell className="min-w-40 py-2.5 whitespace-normal">
              <Memberships memberships={u.memberships} />
            </TableCell>
            <TableCell>
              <UserStatusBadge user={u} />
            </TableCell>
            <TableCell className="text-muted-foreground">
              <LastSignIn at={u.lastLoginAt} nowIso={nowIso} />
            </TableCell>
            <TableCell className="text-muted-foreground">{formatDate(u.createdAt)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** Narrow screens: each account is one tappable row that opens A-05. */
export function UsersList({
  users,
  nowIso,
}: {
  users: ReadonlyArray<AdminUser>
  nowIso: string | null
}) {
  return (
    <ul className="divide-y divide-border-faint">
      {users.map((u) => (
        <li key={u.id}>
          <Link
            href={`/admin/users/${u.id}`}
            className="group flex items-start gap-3 px-5 py-4 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
          >
            <UserAvatar user={u} className="mt-0.5" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <span className="font-semibold text-brand-blue-ink">{u.name}</span>
                <KindBadge kind={u.kind} />
                <UserStatusBadge user={u} />
              </div>
              <p className="truncate text-sm text-muted-foreground">{u.email}</p>
              {u.memberships.length > 0 ? (
                <div className="text-sm text-foreground">
                  <Memberships memberships={u.memberships} />
                </div>
              ) : null}
              <p className="text-xs text-helper">
                {u.lastLoginAt ? (
                  <>
                    Signed in <LastSignIn at={u.lastLoginAt} nowIso={nowIso} />
                  </>
                ) : (
                  'Never signed in'
                )}{' '}
                · Joined {formatDate(u.createdAt)}
              </p>
            </div>
            <ChevronRight
              className="mt-1 size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </Link>
        </li>
      ))}
    </ul>
  )
}
