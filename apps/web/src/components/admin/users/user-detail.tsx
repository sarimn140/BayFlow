'use client'

import { RotateCcw, ShieldCheck, ShieldOff, UserX } from 'lucide-react'
import { useEffect, useId, useMemo } from 'react'

import { ConfirmDialog, ReasonDialog } from '@/components/admin/action-dialogs'
import { useAdminActor } from '@/components/admin/admin-shell'
import { KindBadge, UserStatusBadge } from '@/components/admin/admin-ui'
import { NotFoundPanel } from '@/components/admin/not-found-panel'
import {
  AccessCard,
  AccessItem,
  AuditTrailCard,
  CustomerBookingsCard,
  MembershipsCard,
  ProfileCard,
} from '@/components/admin/users/user-cards'
import { UserAvatar } from '@/components/admin/users/user-list'
import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useMockStore } from '@/hooks/use-mock-store'
import {
  accountActionBlock,
  getAdminShops,
  getAdminUsers,
  getAuditEvents,
  recordAdminView,
  setPlatformAdmin,
  setUserActive,
} from '@/lib/mock-admin'
import { getBookings } from '@/lib/mock-data'

/** Why "Make platform admin" is unavailable for a deactivated account (E-70: 422). */
const GRANT_NEEDS_ACTIVE = 'Reactivate the account before granting admin access.'

/** A-05 User detail (spec 19 §5; E-67…E-71 once wired). */
export function UserDetail({ userId }: { userId: string }) {
  const { user: me } = useAdminActor()
  const users = useMockStore(getAdminUsers)
  const tenants = useMockStore(getAdminShops)
  const bookings = useMockStore(getBookings)
  const audit = useMockStore(getAuditEvents)
  const id = useId()

  const person = users.find((u) => u.id === userId)
  const actor = useMemo(() => ({ name: me.name, email: me.email }), [me.name, me.email])

  // E-67 records that an admin looked at this person's details (D95).
  const personId = person?.id
  const personEmail = person?.email
  useEffect(() => {
    if (personId && personEmail)
      recordAdminView('user', { id: personId, label: personEmail }, actor)
  }, [personId, personEmail, actor])

  const ownBookings = useMemo(
    () =>
      person
        ? bookings
            .filter((b) => b.customerEmail.toLowerCase() === person.email)
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
        : [],
    [bookings, person],
  )
  const trail = useMemo(
    () =>
      person
        ? audit.filter((e) => e.actor?.email === person.email || e.target?.id === person.id)
        : [],
    [audit, person],
  )

  if (!person) return <NotFoundPanel backHref="/admin/users" backLabel="All users" />

  const soleOwnerOf = tenants.filter(
    (t) => t.owners.length === 1 && t.owners[0]!.email === person.email,
  )
  const deactivateBlock = accountActionBlock(person, 'deactivate', actor)
  const revokeBlock = accountActionBlock(person, 'revoke', actor)
  const grantBlock = person.isActive ? null : GRANT_NEEDS_ACTIVE

  const adminReason = person.isPlatformAdmin ? revokeBlock : grantBlock
  const adminReasonId = `${id}-admin-reason`
  const accountReason = person.isActive ? deactivateBlock : null
  const accountReasonId = `${id}-account-reason`

  const adminLever = person.isPlatformAdmin ? (
    <ConfirmDialog
      trigger={
        <Button
          variant="destructive-outline"
          disabled={Boolean(revokeBlock)}
          aria-describedby={revokeBlock ? adminReasonId : undefined}
          className="w-full"
        >
          <ShieldOff data-icon="inline-start" aria-hidden="true" />
          Remove admin access
        </Button>
      }
      title={`Remove platform admin access from ${person.name}?`}
      description="They keep their account and memberships but lose the admin console."
      confirmLabel="Remove access"
      success={`${person.name} is no longer a platform admin`}
      destructive
      onConfirm={() => setPlatformAdmin(person.id, false, actor)}
    />
  ) : (
    <ConfirmDialog
      trigger={
        <Button
          variant="outline"
          disabled={!person.isActive}
          aria-describedby={grantBlock ? adminReasonId : undefined}
          className="w-full"
        >
          <ShieldCheck data-icon="inline-start" aria-hidden="true" />
          Make platform admin
        </Button>
      }
      title={`Make ${person.name} a platform admin?`}
      description="Platform admins see every shop, account and booking, can suspend shops and deactivate accounts. Everything they do is recorded in the audit log."
      confirmLabel="Grant access"
      success={`${person.name} is now a platform admin`}
      onConfirm={() => setPlatformAdmin(person.id, true, actor)}
    />
  )

  const accountLever = person.isActive ? (
    <ReasonDialog
      trigger={
        <Button
          variant="destructive-outline"
          disabled={Boolean(deactivateBlock)}
          aria-describedby={deactivateBlock ? accountReasonId : undefined}
          className="w-full"
        >
          <UserX data-icon="inline-start" aria-hidden="true" />
          Deactivate account
        </Button>
      }
      title={`Deactivate ${person.name}?`}
      description="Deactivation is reversible and keeps every record."
      consequences={[
        'They are signed out at their next request and cannot sign in.',
        'Their memberships and bookings stay as they are.',
      ]}
      warning={
        soleOwnerOf.length
          ? `${person.name} is the only active owner of ${soleOwnerOf.map((t) => t.shop.name).join(', ')}. Those shops keep running, but nobody can manage them until the owner is back.`
          : null
      }
      confirmLabel="Deactivate"
      success={`${person.name} is deactivated`}
      onConfirm={(reason) => setUserActive(person.id, false, reason, actor)}
    />
  ) : (
    <ConfirmDialog
      trigger={
        <Button className="w-full">
          <RotateCcw data-icon="inline-start" aria-hidden="true" />
          Reactivate account
        </Button>
      }
      title={`Reactivate ${person.name}?`}
      description="They can sign in again with their existing password and memberships."
      confirmLabel="Reactivate"
      success={`${person.name} is active again`}
      onConfirm={() => setUserActive(person.id, true, null, actor)}
    />
  )

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: '/admin/users', label: 'All users' }}
        title={
          <span className="flex items-center gap-3">
            <UserAvatar user={person} className="size-11 sm:size-12 [&_span]:text-sm" />
            <span className="min-w-0 break-words">{person.name}</span>
          </span>
        }
        badges={
          <>
            <KindBadge kind={person.kind} />
            <UserStatusBadge user={person} />
          </>
        }
        description={person.email}
      />

      <DetailLayout
        aside={
          <>
            <AccessCard>
              <AccessItem
                title="Platform admin"
                state={
                  person.isPlatformAdmin ? (
                    <Badge variant="brand">Granted</Badge>
                  ) : (
                    <Badge variant="secondary">Not granted</Badge>
                  )
                }
                description={
                  person.isPlatformAdmin
                    ? 'Can open this console: every shop, account and booking.'
                    : "Can't open this console."
                }
                control={adminLever}
                blockedReason={adminReason}
                reasonId={adminReasonId}
              />
              <AccessItem
                title="Sign-in"
                state={<UserStatusBadge user={person} />}
                description={
                  person.isActive
                    ? 'Can sign in and use their memberships.'
                    : "Can't sign in. Memberships and bookings are kept."
                }
                control={accountLever}
                blockedReason={accountReason}
                reasonId={accountReasonId}
              />
            </AccessCard>
            <ProfileCard person={person} />
          </>
        }
      >
        {/* Side by side when the column is wide enough, so neither short list stands alone. */}
        <div className="@container/sections">
          <div className="grid gap-6 @2xl/sections:grid-cols-2">
            <MembershipsCard memberships={person.memberships} tenants={tenants} />
            <CustomerBookingsCard bookings={ownBookings} />
          </div>
        </div>
        <AuditTrailCard events={trail} />
      </DetailLayout>
    </div>
  )
}
