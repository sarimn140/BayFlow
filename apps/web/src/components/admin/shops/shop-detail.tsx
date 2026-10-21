'use client'

import { ArrowRight, Ban, ExternalLink, RotateCcw } from 'lucide-react'
import Link from 'next/link'
import { useMemo } from 'react'

import { ConfirmDialog, ReasonDialog } from '@/components/admin/action-dialogs'
import { useAdminActor } from '@/components/admin/admin-shell'
import { ShopStatusBadges } from '@/components/admin/admin-ui'
import { AuditEventList } from '@/components/admin/audit-events'
import { NotFoundPanel } from '@/components/admin/not-found-panel'
import { CardHeading } from '@/components/admin/overview/card-heading'
import { DetailLayout } from '@/components/layout/detail-layout'
import { PageHeader } from '@/components/layout/page-header'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import { useMockStore } from '@/hooks/use-mock-store'
import { formatDate, formatDateTime } from '@/lib/format'
import {
  getAdminShops,
  getAdminUsers,
  getAuditEvents,
  reactivateShop,
  suspendShop,
} from '@/lib/mock-admin'
import { getBookings } from '@/lib/mock-data'

import { ShopBookingsCard } from './shop-bookings-card'
import { ShopProfileCard } from './shop-profile-card'
import { ShopTeamCard } from './shop-team-card'
import { shopTeam } from './shops-data'

/** How many of the shop's audit events A-03 lists (the audit log has them all). */
const AUDIT_TRAIL = 25

/**
 * A-03 Shop detail (spec 19 §5; E-63…E-65 once wired): the shop's profile, owners and team,
 * bookings by phase and the latest ones, its audit trail, and the Suspend (reason required) and
 * Reactivate levers with their consequences spelled out.
 */
export function ShopDetail({ shopId }: { shopId: string }) {
  const { user } = useAdminActor()
  const tenants = useMockStore(getAdminShops)
  const users = useMockStore(getAdminUsers)
  const bookings = useMockStore(getBookings)
  const audit = useMockStore(getAuditEvents)

  const tenant = tenants.find((t) => t.shop.id === shopId)
  const team = useMemo(() => shopTeam(users, shopId), [users, shopId])
  const shopBookings = useMemo(
    () =>
      bookings
        .filter((b) => b.shopId === shopId)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    [bookings, shopId],
  )
  const shopAudit = useMemo(() => audit.filter((e) => e.shop?.id === shopId), [audit, shopId])

  if (!tenant) return <NotFoundPanel backHref="/admin/shops" backLabel="All shops" />

  const actor = { name: user.name, email: user.email }
  const { shop, suspension } = tenant

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ href: '/admin/shops', label: 'All shops' }}
        title={shop.name}
        badges={<ShopStatusBadges tenant={tenant} />}
        description={`${shop.address}, ${shop.city} · joined ${formatDate(tenant.createdAt)}`}
        actions={
          <>
            <Button asChild variant="outline">
              <Link href={`/shops/${shop.slug}`} target="_blank" rel="noreferrer">
                Public page
                <ExternalLink data-icon="inline-end" aria-hidden="true" />
                <span className="sr-only"> (opens in a new tab)</span>
              </Link>
            </Button>
            {suspension ? (
              <ConfirmDialog
                trigger={
                  <Button>
                    <RotateCcw data-icon="inline-start" aria-hidden="true" />
                    Reactivate shop
                  </Button>
                }
                icon={RotateCcw}
                title={`Reactivate ${shop.name}?`}
                description={
                  shop.is_listed
                    ? 'The shop reappears in the directory, takes bookings again and its staff can sign in to the POS.'
                    : 'Its staff can sign in to the POS again. The shop stays out of the directory until its owner lists it.'
                }
                confirmLabel="Reactivate"
                success={`${shop.name} is active again`}
                onConfirm={() => reactivateShop(shop.id, actor)}
              />
            ) : (
              <ReasonDialog
                trigger={
                  <Button variant="destructive-outline">
                    <Ban data-icon="inline-start" aria-hidden="true" />
                    Suspend shop
                  </Button>
                }
                icon={Ban}
                title={`Suspend ${shop.name}?`}
                description="Suspension is reversible and keeps every record."
                consequences={[
                  shop.is_listed
                    ? 'The shop disappears from the public directory and takes no new bookings.'
                    : 'The shop stays out of the public directory and takes no new bookings.',
                  'Every member, the owner included, is locked out of its POS.',
                  'Customers can still see their bookings and cancel them.',
                ]}
                confirmLabel="Suspend shop"
                success={`${shop.name} is suspended`}
                onConfirm={(reason) => suspendShop(shop.id, reason, actor)}
              />
            )}
          </>
        }
      />

      {suspension ? (
        <Alert variant="destructive">
          <Ban aria-hidden="true" />
          <AlertTitle>
            Suspended {formatDateTime(suspension.at)} by {suspension.byName}
          </AlertTitle>
          <AlertDescription>
            <p>Reason: {suspension.reason}</p>
            <p>
              Hidden from customers and closed to its staff until it is reactivated. Customers can
              still see and cancel their bookings.
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      <DetailLayout aside={<ShopProfileCard tenant={tenant} />}>
        <ShopTeamCard team={team} activeMembers={tenant.activeMembers} />
        <ShopBookingsCard bookings={shopBookings} />
        <Card className="gap-0 py-0">
          <CardHeader className="border-b pt-(--card-spacing)">
            <CardHeading>Audit trail</CardHeading>
            <CardDescription>
              {shopAudit.length > AUDIT_TRAIL
                ? `The ${AUDIT_TRAIL} newest of ${shopAudit.length} events recorded for this shop`
                : 'Everything recorded for this shop, newest first'}
            </CardDescription>
            <CardAction>
              <Button asChild variant="ghost" size="sm">
                <Link href="/admin/audit">
                  Audit log
                  <ArrowRight data-icon="inline-end" aria-hidden="true" />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <AuditEventList
            events={shopAudit.slice(0, AUDIT_TRAIL)}
            showShop={false}
            empty="Nothing recorded yet."
          />
        </Card>
      </DetailLayout>
    </div>
  )
}
