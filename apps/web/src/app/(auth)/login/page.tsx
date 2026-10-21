import type { Metadata } from 'next'
import { Suspense } from 'react'

import { LoginForm, LoginSkeleton } from '@/components/auth/login-form'

export const metadata: Metadata = { title: 'Log in' }

/**
 * P-04 Login (spec 10). The form reads `?next` and `?reason` with `useSearchParams`, so it renders
 * in the browser behind a skeleton shaped like it.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<LoginSkeleton />}>
      <LoginForm />
    </Suspense>
  )
}
