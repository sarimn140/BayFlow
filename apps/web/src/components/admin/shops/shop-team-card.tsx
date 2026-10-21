import { ChevronRight, Users } from 'lucide-react'
import Link from 'next/link'

import { ROLE_LABEL, UserStatusBadge, initials } from '@/components/admin/admin-ui'
import { CardHeading } from '@/components/admin/overview/card-heading'
import { EmptyState } from '@/components/layout/empty-state'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Card, CardDescription, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import type { TeamMember } from './shops-data'

/**
 * A-03 owners and team (spec 19 §5): every membership of the shop, owner first, inactive members
 * and deactivated accounts marked; a row opens the person (A-05).
 */
export function ShopTeamCard({
  team,
  activeMembers,
}: {
  team: ReadonlyArray<TeamMember>
  activeMembers: number
}) {
  const inactive = team.length - activeMembers

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Team</CardHeading>
        <CardDescription>
          {activeMembers} active {activeMembers === 1 ? 'member' : 'members'}
          {inactive > 0 ? ` · ${inactive} inactive` : ''}
        </CardDescription>
      </CardHeader>
      {team.length === 0 ? (
        <EmptyState
          variant="inline"
          tone="neutral"
          icon={Users}
          title="No members"
          description="Nobody belongs to this shop, the owner included."
          className="p-6 sm:p-8"
        />
      ) : (
        <ul className="divide-y divide-border-faint">
          {team.map(({ user, membership }) => {
            const active = membership.isActive && user.isActive
            return (
              <li key={user.id}>
                <Link
                  href={`/admin/users/${encodeURIComponent(user.id)}`}
                  className="group flex items-center gap-3 px-5 py-3 transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:gap-4 sm:px-6"
                >
                  <Avatar size="lg" className={cn(!active && 'opacity-60')}>
                    <AvatarFallback className="font-semibold">{initials(user.name)}</AvatarFallback>
                  </Avatar>
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        'block truncate text-sm font-medium',
                        active ? 'text-foreground' : 'text-muted-foreground',
                      )}
                    >
                      {user.name}
                    </span>
                    <span className="block truncate text-xs text-helper">{user.email}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1 sm:flex-row sm:items-center sm:gap-2">
                    {!user.isActive ? (
                      <UserStatusBadge user={user} />
                    ) : !membership.isActive ? (
                      <Badge variant="neutral">Inactive</Badge>
                    ) : null}
                    <Badge variant="brand">{ROLE_LABEL[membership.role]}</Badge>
                  </span>
                  <ChevronRight
                    className="size-4 shrink-0 text-helper transition-transform duration-150 group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
