'use client'

import { MoreHorizontal, Plus, UserCheck, UserCog, UserPlus, UserX } from 'lucide-react'
import { useRef } from 'react'

import { ROLE_NAME, initials } from '@/components/layout/account-menu'
import { DataTableCard } from '@/components/layout/data-table-card'
import { EmptyState } from '@/components/layout/empty-state'
import { plural } from '@/components/pos/overview/overview-data'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { MockTeamMember } from '@/lib/mock-data'
import { cn } from '@/lib/utils'

import type { MemberRow } from './team-data'

export type MemberAction = 'role' | 'deactivate' | 'reactivate'

/** Marks a member's row-menu buttons (one in the list, one in the table) to return focus to. */
export const MEMBER_ACTIONS_ATTR = 'data-member-actions'

function MemberAvatar({ member }: { member: MockTeamMember }) {
  return (
    <Avatar size="lg" className={cn(!member.is_active && 'opacity-60')}>
      <AvatarFallback className="font-semibold">{initials(member.name)}</AvatarFallback>
    </Avatar>
  )
}

function MemberName({ row }: { row: MemberRow }) {
  const { member } = row
  return (
    <div className="min-w-0">
      <p className="flex min-w-0 items-center gap-2">
        <span
          className={cn(
            'truncate text-sm font-medium',
            member.is_active ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          {member.name}
        </span>
        {row.isSelf ? <Badge variant="outline">You</Badge> : null}
      </p>
      <p className="truncate text-sm text-muted-foreground">{member.email}</p>
    </div>
  )
}

function MemberStatus({ active }: { active: boolean }) {
  return active ? (
    <Badge variant="success">Active</Badge>
  ) : (
    <Badge variant="neutral">Inactive</Badge>
  )
}

/** Change role and deactivate / reactivate; each item opens its confirmation dialog. */
function RowMenu({
  member,
  onAction,
}: {
  member: MockTeamMember
  onAction: (action: MemberAction, member: MockTeamMember) => void
}) {
  // The dialog an item opens takes focus; the menu must not pull it back to its button.
  const openingDialog = useRef(false)
  const choose = (action: MemberAction) => () => {
    openingDialog.current = true
    onAction(action, member)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Actions for ${member.name}`}
          data-member-actions={member.id}
        >
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-52"
        onCloseAutoFocus={(event) => {
          if (!openingDialog.current) return
          openingDialog.current = false
          event.preventDefault()
        }}
      >
        <DropdownMenuItem onSelect={choose('role')}>
          <UserCog aria-hidden="true" />
          Change role…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {member.is_active ? (
          <DropdownMenuItem variant="destructive" onSelect={choose('deactivate')}>
            <UserX aria-hidden="true" />
            Deactivate…
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onSelect={choose('reactivate')}>
            <UserCheck aria-hidden="true" />
            Reactivate…
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export interface MembersCardProps {
  rows: ReadonlyArray<MemberRow>
  /** "7 members · all active". */
  summary: string
  /** Only the owner so far: the first-use prompt (spec 10 O-02 empty state). */
  ownerOnly: boolean
  onAction: (action: MemberAction, member: MockTeamMember) => void
  onAdd: () => void
}

/**
 * The team (spec 10 O-02 table): avatar, name and e-mail, role chip, status, open jobs and the
 * row menu. Stacked rows while the content area is narrow (phones, tablets, an open sidebar on a
 * small laptop), the table from 768px of content width. The owner's row has no menu (D19).
 */
export function MembersCard({ rows, summary, ownerOnly, onAction, onAdd }: MembersCardProps) {
  return (
    <DataTableCard title="Members" description={summary}>
      <ul
        aria-label="Team members"
        className="divide-y divide-border-faint border-t border-border-faint @3xl/team:hidden"
      >
        {rows.map((row) => (
          <li key={row.member.id} className="flex items-start gap-3 px-5 py-4">
            <MemberAvatar member={row.member} />
            <div className="min-w-0 flex-1 space-y-2">
              <MemberName row={row} />
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <Badge variant="brand">{ROLE_NAME[row.member.role]}</Badge>
                <MemberStatus active={row.member.is_active} />
                {row.openJobs !== null ? (
                  <span className="text-xs text-helper tabular-nums">
                    {row.openJobs === 0 ? 'No open jobs' : plural(row.openJobs, 'open job')}
                  </span>
                ) : null}
              </div>
            </div>
            {row.editable ? <RowMenu member={row.member} onAction={onAction} /> : null}
          </li>
        ))}
      </ul>

      <div className="hidden border-t border-border-faint @3xl/team:block">
        <Table aria-label="Team members">
          <TableHeader>
            <TableRow>
              <TableHead>Member</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Open jobs</TableHead>
              <TableHead className="w-0">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.member.id}>
                <TableCell className="py-3">
                  <div className="flex items-center gap-3">
                    <MemberAvatar member={row.member} />
                    <MemberName row={row} />
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="brand">{ROLE_NAME[row.member.role]}</Badge>
                </TableCell>
                <TableCell>
                  <MemberStatus active={row.member.is_active} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {row.openJobs === null ? (
                    <>
                      <span aria-hidden="true" className="text-helper">
                        —
                      </span>
                      <span className="sr-only">Not assigned jobs</span>
                    </>
                  ) : (
                    <span
                      className={cn(
                        row.openJobs > 0
                          ? 'font-semibold text-foreground'
                          : 'text-muted-foreground',
                      )}
                    >
                      {row.openJobs}
                    </span>
                  )}
                </TableCell>
                <TableCell className="w-0 py-1 text-right">
                  {row.editable ? <RowMenu member={row.member} onAction={onAction} /> : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {ownerOnly ? (
        <div className="border-t border-border-faint">
          <EmptyState
            variant="inline"
            icon={UserPlus}
            title="Add your team"
            description="Add your service advisor, technicians, QC inspector and parts person to start taking bookings."
            action={
              <Button variant="outline" onClick={onAdd}>
                <Plus data-icon="inline-start" aria-hidden="true" />
                Add team member
              </Button>
            }
          />
        </div>
      ) : null}
    </DataTableCard>
  )
}
