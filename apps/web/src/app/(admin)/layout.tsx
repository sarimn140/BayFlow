import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { AdminShell } from '@/components/admin/admin-shell'

// `default` goes through the root template ("Platform admin · BayFlow"); a page's own title gets
// this segment's template ("Users · Platform admin · BayFlow"). A plain string here would drop the
// template for every admin page.
export const metadata: Metadata = {
  title: { default: 'Platform admin', template: '%s · Platform admin · BayFlow' },
}

/** `(admin)` shell (spec 19 §5): the platform admin console, separate from the POS. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>
}
