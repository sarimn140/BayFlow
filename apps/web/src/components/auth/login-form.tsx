'use client'

import { ArrowRight, CircleAlert, Eye, EyeOff, Info, Lock, Mail } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useRef, useState, type FormEvent } from 'react'

import { DemoAccountsPanel } from '@/components/auth/demo-accounts-panel'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { DEMO_PASSWORD, type DemoAccount } from '@/content/demo-accounts'
import { isAccountActive, recordSignIn } from '@/lib/mock-admin'
import { homePathFor, resolveMockSession } from '@/lib/mock-auth'
import { setCurrentUser } from '@/lib/mock-data'
import { safeNextPath } from '@/lib/safe-next'
import { signInToApi } from '@/features/calls/session'

/** P-04 Login (spec 10): e-mail and password, the session-expired banner, and the demo accounts. */
export function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const expired = searchParams.get('reason') === 'expired'
  const next = safeNextPath(searchParams.get('next'))
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const pickDemoAccount = (account: DemoAccount) => {
    setEmail(account.email)
    setPassword(DEMO_PASSWORD)
    setError(null)
    submitRef.current?.focus()
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (loading) return
    if (!email.trim() || !password) {
      setError('Enter your e-mail address and password.')
      // Focus the first empty field so the fix is one keystroke away.
      const firstEmpty = email.trim() ? passwordRef.current : emailRef.current
      firstEmpty?.focus()
      return
    }
    // A deactivated account gets the same answer as a wrong password (D9: no account enumeration).
    // As for a wrong password (spec 10 P-04), the e-mail stays and the password is cleared.
    if (!isAccountActive(email)) {
      recordSignIn(email, false)
      setError('E-mail or password is incorrect.')
      setPassword('')
      passwordRef.current?.focus()
      return
    }
    setError(null)
    setLoading(true)
    // The real API session (D8) next to the mock one, for in-app calling. Its httpOnly
    // `bf_session` cookie cannot be replaced by the mock one below; `setCurrentUser` also sets
    // the readable `bf_signed_in` flag the header reads (hooks/use-mock-session).
    await signInToApi(email.trim(), password)

    const session = resolveMockSession(email)
    recordSignIn(email, true)
    setCurrentUser(session)
    // The proxy only checks that a session cookie exists (spec 09 §2.8).
    document.cookie = `bf_session=active_${Date.now()}; path=/; max-age=86400; SameSite=Lax`
    window.setTimeout(() => router.push(next ?? homePathFor(session)), 350)
  }

  return (
    <div data-auth-width="narrow" className="w-full space-y-6">
      <Card>
        <CardHeader className="gap-2">
          <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl">
            Log in to BayFlow
          </h1>
          <p className="text-base text-muted-foreground">
            Owners, workshop staff and customers all sign in here.
          </p>
        </CardHeader>

        <CardContent className="gap-6">
          {expired && (
            <Alert variant="info">
              <Info aria-hidden="true" />
              <AlertDescription>Your session has expired. Please log in again.</AlertDescription>
            </Alert>
          )}

          {/* POST: a submit that beats hydration must not put the password in the URL */}
          <form
            method="post"
            onSubmit={(event) => void handleSubmit(event)}
            noValidate
            className="space-y-6"
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="email">E-mail</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <Mail aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    ref={emailRef}
                    id="email"
                    name="email"
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    placeholder="name@bayflow.test"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    aria-invalid={Boolean(error) && !email.trim()}
                    aria-describedby={error ? 'login-error' : undefined}
                    required
                  />
                </InputGroup>
              </Field>

              <Field>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <InputGroup>
                  <InputGroupAddon>
                    <Lock aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    ref={passwordRef}
                    id="password"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder="Your password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    aria-invalid={Boolean(error) && !password}
                    aria-describedby={error ? 'login-error' : undefined}
                    maxLength={128}
                    required
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupButton
                      size="icon-sm"
                      className="relative after:absolute after:-inset-1"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword((shown) => !shown)}
                    >
                      {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                    </InputGroupButton>
                  </InputGroupAddon>
                </InputGroup>
              </Field>
            </FieldGroup>

            {error && (
              <Alert variant="destructive" id="login-error">
                <CircleAlert aria-hidden="true" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button ref={submitRef} type="submit" size="lg" disabled={loading} className="w-full">
              {loading ? (
                <>
                  <Spinner aria-hidden="true" />
                  Logging in…
                </>
              ) : (
                <>
                  Log in
                  <ArrowRight data-icon="inline-end" aria-hidden="true" />
                </>
              )}
            </Button>
          </form>
        </CardContent>

        <CardFooter className="flex-col items-stretch gap-2 border-t text-center text-sm text-balance text-muted-foreground">
          <p>
            Own a garage?{' '}
            <Link
              href="/register"
              className="font-semibold text-brand-blue-ink underline-offset-4 hover:underline"
            >
              Register your shop
            </Link>
          </p>
          <p>
            New customer?{' '}
            <Link
              href="/book"
              className="font-semibold text-brand-blue-ink underline-offset-4 hover:underline"
            >
              Book a service
            </Link>{' '}
            — your account is created as you book.
          </p>
        </CardFooter>
      </Card>

      <DemoAccountsPanel onPick={pickDemoAccount} selectedEmail={email.trim().toLowerCase()} />
    </div>
  )
}

/** Shaped like the login card and the demo accounts card (shown until the form can read `?next`). */
export function LoginSkeleton() {
  return (
    <div data-auth-width="narrow" className="w-full space-y-6" aria-busy="true">
      <div className="space-y-6 rounded-2xl border border-border bg-card p-5 shadow-xs sm:p-6">
        <div className="space-y-3">
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-5 w-full" />
        </div>
        <div className="space-y-5">
          {[0, 1].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-10.5 w-full" />
            </div>
          ))}
          <Skeleton className="h-12 w-full rounded-full" />
        </div>
      </div>
      <Skeleton className="h-72 rounded-2xl" />
      <span className="sr-only">Loading the login form…</span>
    </div>
  )
}
