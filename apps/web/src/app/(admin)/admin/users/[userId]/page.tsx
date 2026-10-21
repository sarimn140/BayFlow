import type { Metadata } from 'next'

import { UserDetail } from '@/components/admin/users/user-detail'

export const metadata: Metadata = { title: { absolute: 'User details · Platform admin · BayFlow' } }

/** A-05 User detail (spec 19 §5; E-67…E-71 once wired). */
export default async function AdminUserPage({ params }: PageProps<'/admin/users/[userId]'>) {
  const { userId } = await params
  return <UserDetail userId={userId} />
}
