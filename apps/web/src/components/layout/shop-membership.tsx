'use client'

import { Store } from 'lucide-react'
import Link from 'next/link'

import { workspacesOf, type Workspace } from '@/components/pos/hub/hub-data'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
} from '@/components/ui/empty'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { getCurrentUser, getShops, getTeamMembers } from '@/lib/mock-data'

export interface ShopMembership {
  /** False until this browser's stored session is read (the seed user never decides). */
  ready: boolean
  /** The signed-in person's active membership of the shop, with their role there; or null. */
  membership: Workspace | null
}

/**
 * D20 (`require_shop_member`): the person's own active membership of `shopId`, from their
 * memberships only (`workspacesOf`, the `/me` list). Null for anyone else — other shops' staff,
 * customers (never POS users) and platform admins without a membership (spec 19: a separate hat) —
 * and for a shop that does not exist, so the two look the same.
 */
export function useShopMembership(shopId: string): ShopMembership {
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const team = useMockStore(getTeamMembers)
  const shops = useMockStore(getShops)
  if (user.role === 'CUSTOMER') return { ready, membership: null }
  const membership =
    workspacesOf(user.email, team, shops).find((workspace) => workspace.shop.id === shopId) ?? null
  return { ready, membership }
}

/**
 * The API's 404 for a shop the person is not a member of (D20): the same words whether the shop
 * exists or not, and nothing of the shop's (not even its name).
 */
export function ShopNotFoundState() {
  const user = useMockStore(getCurrentUser)
  const customer = user.role === 'CUSTOMER'
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
          {customer
            ? 'Check the link. Your bookings are in My bookings.'
            : 'Check the link, or open one of your shops from the workshop hub.'}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={customer ? '/bookings' : '/pos'}>
            {customer ? 'Go to my bookings' : 'Go to my shops'}
          </Link>
        </Button>
      </EmptyContent>
    </Empty>
  )
}
