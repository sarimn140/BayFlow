import type { Metadata } from 'next'

import { PlatformOverview } from '@/components/admin/overview/platform-overview'

export const metadata: Metadata = { title: { absolute: 'Overview · Platform admin · BayFlow' } }

/** A-01 Platform overview (spec 19 §5; E-61 once wired). */
export default function AdminOverviewPage() {
  return <PlatformOverview />
}
