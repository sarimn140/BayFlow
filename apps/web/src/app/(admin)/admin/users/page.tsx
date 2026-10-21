import type { Metadata } from 'next'

import { UsersDirectory } from '@/components/admin/users/users-directory'

export const metadata: Metadata = { title: { absolute: 'Users · Platform admin · BayFlow' } }

/** A-04 Users (spec 19 §5; E-66 once wired). */
export default function AdminUsersPage() {
  return <UsersDirectory />
}
