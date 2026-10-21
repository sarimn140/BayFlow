import type { Metadata } from 'next'

import { AuditLog } from '@/components/admin/audit/audit-log'

export const metadata: Metadata = { title: { absolute: 'Audit log · Platform admin · BayFlow' } }

/** A-08 Audit log (spec 19 §5; E-74 and E-75 once wired). */
export default function AdminAuditPage() {
  return <AuditLog />
}
