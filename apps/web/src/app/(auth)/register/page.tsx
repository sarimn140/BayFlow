import type { Metadata } from 'next'

import { RegisterForm } from '@/components/auth/register-form'

export const metadata: Metadata = { title: 'Create your owner account' }

/** P-05 Owner registration (spec 10). The brand panel beside it comes from the `(auth)` layout. */
export default function RegisterPage() {
  return <RegisterForm />
}
