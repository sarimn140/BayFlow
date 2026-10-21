import type { Metadata } from 'next'

import { ShopsDirectory } from '@/components/admin/shops/shops-directory'

export const metadata: Metadata = { title: { absolute: 'Shops · Platform admin · BayFlow' } }

/** A-02 Shops (spec 19 §5; E-62 once wired). */
export default function AdminShopsPage() {
  return <ShopsDirectory />
}
