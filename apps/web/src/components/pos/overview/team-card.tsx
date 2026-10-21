import { UserPlus } from 'lucide-react'
import Link from 'next/link'

import { ROLE_NAME, initials } from '@/components/layout/account-menu'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import type { MockTeamMember } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'
import { ASSIGNABLE_ROLES, plural } from './overview-data'

export interface TeamCardProps {
  /** By role, then name; the owner row and inactive members included. */
  members: ReadonlyArray<MockTeamMember & { openJobs: number }>
  base: string
}

/** Team at a glance (spec 10 O-01 §5): name, role chip, active state, open jobs, "Manage team". */
export function TeamCard({ members, base }: TeamCardProps) {
  const inactive = members.filter((m) => !m.is_active).length
  const staff = members.filter((m) => m.role !== 'OWNER')

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Team</CardHeading>
        <CardDescription>
          {plural(members.length, 'member')} ·{' '}
          {inactive === 0 ? 'all active' : `${inactive} inactive`}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href={`${base}/team`}>Manage team</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <ul className="divide-y divide-border-faint">
        {members.map((member) => (
          <li key={member.id} className="flex items-center gap-3 px-5 py-3 sm:px-6">
            <Avatar size="lg" className={cn(!member.is_active && 'opacity-60')}>
              <AvatarFallback className="font-semibold">{initials(member.name)}</AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="flex min-w-0 items-center gap-2">
                <span
                  className={cn(
                    'truncate text-sm font-medium',
                    member.is_active ? 'text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {member.name}
                </span>
                {member.is_active ? null : <Badge variant="neutral">Inactive</Badge>}
              </p>
              <p className="truncate text-xs text-helper">{member.email}</p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge variant="brand">{ROLE_NAME[member.role]}</Badge>
              {ASSIGNABLE_ROLES.has(member.role) ? (
                <span className="text-xs text-helper tabular-nums">
                  {member.openJobs === 0 ? 'No open jobs' : plural(member.openJobs, 'open job')}
                </span>
              ) : null}
            </div>
          </li>
        ))}
        {staff.length === 0 ? (
          <li>
            <Link
              href={`${base}/team`}
              className="flex items-center gap-3 px-5 py-3.5 text-sm font-medium text-brand-blue-ink transition-colors duration-150 outline-none hover:bg-brand-blue-subtle/40 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid sm:px-6"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-blue-subtle">
                <UserPlus className="size-5" aria-hidden="true" />
              </span>
              Add your service advisor, technicians, parts staff and QC inspectors
            </Link>
          </li>
        ) : null}
      </ul>
    </Card>
  )
}
