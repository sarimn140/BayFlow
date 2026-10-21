import type { Metadata } from 'next'

import { TeamManagement } from '@/components/pos/team/team-management'

export const metadata: Metadata = { title: 'Team' }

/**
 * O-02 Team management (spec 10), Owner only: add staff with a role, change roles, deactivate
 * or reactivate them. The owner's own membership can't be changed (D19).
 */
export default async function TeamPage({ params }: PageProps<'/pos/shops/[shopId]/team'>) {
  const { shopId } = await params
  // Keyed by shop: an open dialog or a notice never carries over to another shop's team.
  return <TeamManagement key={shopId} shopId={shopId} />
}
