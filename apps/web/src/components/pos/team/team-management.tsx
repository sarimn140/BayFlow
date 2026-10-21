'use client'

import { CircleCheck, Store, UserPlus, X } from 'lucide-react'
import Link from 'next/link'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/layout/page-header'
import { StatCard } from '@/components/layout/stat-card'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { getAdminUsers } from '@/lib/mock-admin'
import {
  getBookings,
  getCurrentUser,
  getShopById,
  getTeamMembers,
  saveTeamMember,
  type MockTeamMember,
} from '@/lib/mock-data'
import { sectionAccess } from '@/lib/pos-access'

import { AddMemberSheet } from './add-member-sheet'
import { ChangeRoleDialog, DeactivateDialog, ReactivateDialog } from './member-dialogs'
import { MEMBER_ACTIONS_ATTR, MembersCard, type MemberAction } from './members-card'
import { ROLE_ICON } from './role-choice'
import {
  ROLE_DUTY,
  ROLE_GROUP,
  canEditMember,
  isStaffRole,
  memberRows,
  planAddMember,
  roleCoverage,
  roleName,
  teamSummary,
  type DraftErrors,
  type MemberDraft,
  type RoleCoverage,
  type StaffRole,
} from './team-data'

/** Loading state shaped like the page (DESIGN.md §6.9): header, role tiles, the members card. */
function TeamSkeleton() {
  return (
    <div className="@container/team space-y-6" aria-busy="true">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-4 w-32 rounded-full" />
        <Skeleton className="h-10 w-36" />
        <Skeleton className="h-5 w-[28rem] max-w-full" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 @4xl/team:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-36 rounded-2xl" />
        ))}
      </div>
      <Skeleton className="h-[34rem] rounded-2xl" />
      <span className="sr-only">Loading the team…</span>
    </div>
  )
}

/** D20: an unknown shop reads as "not found", never as another shop's team. */
function ShopNotFound() {
  return (
    <Empty className="border bg-card py-16 sm:py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Store aria-hidden="true" />
        </EmptyMedia>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          We couldn&apos;t find that shop
        </h1>
        <EmptyDescription className="text-base">
          Check the link, or open one of your shops from the workshop hub.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href="/pos">Go to my shops</Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}

const ADD_BUTTON_ID = 'team-add-member'

function coverageHint({ role, active, inactive }: RoleCoverage): string {
  const duty = active === 0 ? 'None active yet' : ROLE_DUTY[role]
  return inactive > 0 ? `${duty} · ${inactive} inactive` : duty
}

/** A dialog's member and action stay set while it animates closed. */
interface MemberDialogState {
  action: MemberAction
  member: MockTeamMember
}

/**
 * O-02 Team management (spec 10), Owner only: who works in the shop, in which role, whether they
 * can sign in and how many open jobs they hold; add a member, change a role, deactivate or
 * reactivate. The owner's own membership is never changed (D19). Renders this browser's stored
 * data only (a skeleton until then), so nothing flashes.
 */
export function TeamManagement({ shopId }: { shopId: string }) {
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const team = useMockStore(() => getTeamMembers(shop?.id ?? shopId))
  const bookings = useMockStore(() => getBookings(shopId))

  const [addOpen, setAddOpen] = useState(false)
  /** The control that opened the sheet; focus goes back to it when the sheet closes. */
  const addOpener = useRef<Element | null>(null)
  /** D18: the e-mail already had an account, so only the membership was added. */
  const [notice, setNotice] = useState<{ name: string; role: StaffRole } | null>(null)
  const [dialog, setDialog] = useState<MemberDialogState | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [nextRole, setNextRole] = useState<StaffRole>('TECHNICIAN')

  if (!ready) return <TeamSkeleton />
  if (!shop) return <ShopNotFound />

  const canManage = sectionAccess(user.role, 'team') === 'manage'
  const rows = memberRows(team, bookings, user.email, canManage)
  const ownerOnly = team.every((member) => member.role === 'OWNER')

  const openAdd = () => {
    addOpener.current = document.activeElement
    setAddOpen(true)
  }

  /** The first-use prompt's button is gone once a member is added: use the header's instead. */
  const addSheetCloseFocus = (event: Event) => {
    if (addOpener.current?.isConnected) return
    event.preventDefault()
    document.getElementById(ADD_BUTTON_ID)?.focus()
  }

  const addMember = (draft: MemberDraft): DraftErrors | null => {
    const plan = planAddMember(draft, {
      id: `usr-${Date.now()}`,
      shopId: shop.id,
      team,
      accounts: getAdminUsers(),
    })
    if (!plan.ok) return plan.errors
    saveTeamMember(plan.member)
    if (plan.existingAccount) {
      setNotice({ name: plan.member.name, role: draft.role })
    } else {
      setNotice(null)
      toast.success(`${plan.member.name} added as ${roleName(draft.role)}`)
    }
    return null
  }

  const openDialog = (action: MemberAction, member: MockTeamMember) => {
    if (!canManage || !canEditMember(member, user.email)) return
    setDialog({ action, member })
    if (isStaffRole(member.role)) setNextRole(member.role)
    setDialogOpen(true)
  }

  /** The member as stored now: another tab may have changed it while the dialog was open. */
  const stored = (member: MockTeamMember) => getTeamMembers().find((m) => m.id === member.id)

  const changeRole = (member: MockTeamMember, role: StaffRole) => {
    const current = stored(member)
    if (!current || !canEditMember(current, user.email) || current.role === role) return
    saveTeamMember({ ...current, role })
    toast.success(`${current.name} is now a ${roleName(role)}`)
  }

  const setActive = (member: MockTeamMember, isActive: boolean) => {
    const current = stored(member)
    if (!current || !canEditMember(current, user.email) || current.is_active === isActive) return
    saveTeamMember({ ...current, is_active: isActive })
    toast.success(`${current.name} ${isActive ? 'reactivated' : 'deactivated'}`)
  }

  /** The menu item that opened the dialog is gone: focus returns to the member's row menu. */
  const returnFocus = (event: Event) => {
    if (!dialog) return
    event.preventDefault()
    const menus = document.querySelectorAll<HTMLElement>(`[${MEMBER_ACTIONS_ATTR}]`)
    const visible = [...menus].find(
      (menu) =>
        menu.getAttribute(MEMBER_ACTIONS_ATTR) === dialog.member.id &&
        menu.getClientRects().length > 0,
    )
    visible?.focus()
  }

  const dialogMember = dialog?.member
  const dialogRow = dialogMember ? rows.find((row) => row.member.id === dialogMember.id) : undefined

  return (
    <div className="@container/team space-y-6">
      <PageHeader
        eyebrow={shop.name}
        title="Team"
        description="Add your staff, choose what each person does, and deactivate anyone who leaves."
        actions={
          canManage ? (
            <Button id={ADD_BUTTON_ID} onClick={openAdd}>
              <UserPlus data-icon="inline-start" aria-hidden="true" />
              Add team member
            </Button>
          ) : null
        }
      />

      {notice ? (
        <Alert variant="success">
          <CircleCheck aria-hidden="true" />
          <AlertTitle>
            {notice.name} added as {roleName(notice.role)}
          </AlertTitle>
          <AlertDescription>
            This e-mail already has a BayFlow account — we added them to {shop.name} as{' '}
            {roleName(notice.role)}. Their existing password is unchanged.
          </AlertDescription>
          <AlertAction>
            <Button
              variant="ghost"
              size="icon-sm"
              className="relative after:absolute after:-inset-1"
              aria-label="Dismiss"
              onClick={() => setNotice(null)}
            >
              <X aria-hidden="true" />
            </Button>
          </AlertAction>
        </Alert>
      ) : null}

      {ownerOnly ? null : (
        <section aria-labelledby="team-roles-heading">
          <h2 id="team-roles-heading" className="sr-only">
            Roles in this shop
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 @4xl/team:grid-cols-4">
            {roleCoverage(team).map((coverage) => (
              <StatCard
                key={coverage.role}
                label={ROLE_GROUP[coverage.role]}
                value={coverage.active}
                icon={ROLE_ICON[coverage.role]}
                tone={coverage.active === 0 ? 'warning' : 'brand'}
                hint={coverageHint(coverage)}
              />
            ))}
          </div>
        </section>
      )}

      <MembersCard
        rows={rows}
        summary={teamSummary(team)}
        ownerOnly={ownerOnly && canManage}
        onAction={openDialog}
        onAdd={openAdd}
      />

      {canManage ? (
        <AddMemberSheet
          open={addOpen}
          onOpenChange={setAddOpen}
          shopName={shop.name}
          onAdd={addMember}
          onCloseAutoFocus={addSheetCloseFocus}
        />
      ) : null}

      {dialog ? (
        <>
          <ChangeRoleDialog
            open={dialogOpen && dialog.action === 'role'}
            onOpenChange={setDialogOpen}
            member={dialog.member}
            onCloseAutoFocus={returnFocus}
            value={nextRole}
            onValueChange={setNextRole}
            onConfirm={(role) => changeRole(dialog.member, role)}
          />
          <DeactivateDialog
            open={dialogOpen && dialog.action === 'deactivate'}
            onOpenChange={setDialogOpen}
            member={dialog.member}
            onCloseAutoFocus={returnFocus}
            shopName={shop.name}
            openJobs={dialogRow?.openJobs ?? null}
            onConfirm={() => setActive(dialog.member, false)}
          />
          <ReactivateDialog
            open={dialogOpen && dialog.action === 'reactivate'}
            onOpenChange={setDialogOpen}
            member={dialog.member}
            onCloseAutoFocus={returnFocus}
            shopName={shop.name}
            onConfirm={() => setActive(dialog.member, true)}
          />
        </>
      ) : null}
    </div>
  )
}
