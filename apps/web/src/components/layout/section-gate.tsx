'use client'

import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import { ForbiddenState } from '@/components/feedback/forbidden-state'
import { ShopSuspendedState } from '@/components/feedback/shop-suspended-state'
import { useMockStore } from '@/hooks/use-mock-store'
import { getShopSuspensions } from '@/lib/mock-admin'
import { homePathFor } from '@/lib/mock-auth'
import { sectionAccess, sectionAudience, sectionOf } from '@/lib/pos-access'

import { ShopNotFoundState, useShopMembership } from './shop-membership'

/**
 * Shop gate (spec 10 S-01, X-03), in the order the API answers:
 * 1. not an active member of this shop → the 404 view (D20), whether or not the shop exists;
 * 2. the shop is suspended → `ShopSuspendedState` for every member, the Owner too (D96);
 * 3. another role's section → `ForbiddenState`, judged by the person's role in THIS shop (their
 *    membership, D66), so the Owner keeps the read-only role views (D16).
 * Waits for this browser's stored session, so the seed user never decides.
 */
export function SectionGate({ shopId, children }: { shopId: string; children: ReactNode }) {
  const pathname = usePathname()
  const { ready, membership } = useShopMembership(shopId)
  const suspensions = useMockStore(getShopSuspensions)
  const section = sectionOf(pathname)

  if (!ready) return children
  if (!membership) return <ShopNotFoundState />
  if (suspensions[shopId]) return <ShopSuspendedState />
  if (!section || sectionAccess(membership.role, section)) return children

  return (
    <ForbiddenState
      message={sectionAudience(section)}
      homeHref={homePathFor({ role: membership.role, shopId })}
    />
  )
}
