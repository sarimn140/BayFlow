'use client'

import {
  ArrowRight,
  Building2,
  Eye,
  EyeOff,
  Info,
  Lock,
  LogOut,
  Mail,
  Phone,
  Plus,
  UserRound,
} from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'

import { OnboardingSteps } from '@/components/auth/onboarding-steps'
import { PASSWORD_MAX, PASSWORD_MIN, PasswordStrength } from '@/components/auth/password-strength'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import { Spinner } from '@/components/ui/spinner'
import { endMockSession, useHasMockSession } from '@/hooks/use-mock-session'
import { useMockStore } from '@/hooks/use-mock-store'
import { getCurrentUser, setCurrentUser } from '@/lib/mock-data'

type FieldName = 'fullName' | 'email' | 'phone' | 'password'
type Errors = Partial<Record<FieldName, string>>

/**
 * Spec 10 P-05 field rules, which are spec 03's (spec 09 §2.10): D10 passwords; the e-mail needs
 * one `@` with text on both sides, so reserved addresses such as `x@test` pass (D62).
 */
function validate(values: { fullName: string; email: string; phone: string; password: string }) {
  const errors: Errors = {}
  const name = values.fullName.trim()
  if (!name) errors.fullName = 'Enter your full name.'
  else if (name.length > 120) errors.fullName = 'Use 120 characters or fewer.'

  const email = values.email.trim()
  if (!email) errors.email = 'Enter your e-mail address.'
  else if (email.length > 254 || !/^[^\s@]+@[^\s@]+$/.test(email))
    errors.email = 'Enter a valid e-mail address, like name@example.com.'

  const phone = values.phone.trim()
  if (phone && !/^\+?[0-9 -]{7,20}$/.test(phone))
    errors.phone = 'Use 7 to 20 digits, spaces or hyphens, with an optional leading +.'

  if (values.password.length < PASSWORD_MIN || values.password.length > PASSWORD_MAX)
    errors.password = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`
  return errors
}

function FormField({
  id,
  label,
  optional,
  error,
  children,
}: {
  id: string
  label: string
  optional?: boolean
  error?: string
  children: ReactNode
}) {
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional && <span className="font-normal text-helper">(optional)</span>}
      </FieldLabel>
      {children}
      {error && <FieldError id={`${id}-error`}>{error}</FieldError>}
    </Field>
  )
}

/**
 * P-05 Owner registration (spec 10): the account first, then the shop (S-03) and the team (O-02).
 * Staff never self-register (brief §4). Someone already logged in is offered "Create a new shop"
 * instead (D17: any logged-in user may open a shop).
 */
export function RegisterForm() {
  const router = useRouter()
  const signedIn = useHasMockSession()
  const user = useMockStore(getCurrentUser)

  const [fullName, setFullName] = useState('')
  const [garageName, setGarageName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<Errors>({})
  const [loading, setLoading] = useState(false)

  const logOut = () => {
    endMockSession()
    // The form replaces the notice; put the keyboard on its first field.
    window.setTimeout(() => document.getElementById('fullName')?.focus(), 0)
  }

  // Registering signs the new owner in; keep the form (and its spinner) until the redirect.
  if (signedIn && !loading) return <SignedInNotice name={user.name} onLogOut={logOut} />

  const describe = (field: FieldName, extra?: string) =>
    [errors[field] ? `${field}-error` : null, extra].filter(Boolean).join(' ') || undefined

  /** Errors appear on submit; once a field shows one, it is re-checked as the user fixes it. */
  const change =
    (field: FieldName, setValue: (value: string) => void) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value
      setValue(value)
      if (!errors[field]) return
      const next = validate({ fullName, email, phone, password, [field]: value })
      setErrors((current) => ({ ...current, [field]: next[field] }))
    }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (loading) return
    const found = validate({ fullName, email, phone, password })
    setErrors(found)
    const first = (['fullName', 'email', 'phone', 'password'] as const).find((f) => found[f])
    if (first) {
      event.currentTarget.querySelector<HTMLInputElement>(`#${first}`)?.focus()
      return
    }

    setLoading(true)
    // A new owner has no shop yet (`memberships: []` until S-03 creates one), so no shop is
    // current: never another shop, which would open its POS as Owner (D20).
    setCurrentUser({
      name: fullName.trim(),
      email: email.trim().toLowerCase(),
      role: 'OWNER',
      shopId: '',
      shopName: '',
    })
    // The proxy only checks that a session cookie exists (spec 09 §2.8).
    document.cookie = `bf_session=active_${Date.now()}; path=/; max-age=86400; SameSite=Lax`
    window.setTimeout(() => router.replace('/pos/shops/new'), 400)
  }

  return (
    <Card className="w-full">
      <CardHeader className="gap-6">
        <OnboardingSteps current={0} />
        <div className="space-y-2">
          <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl">
            Create your owner account
          </h1>
          <p className="text-base text-muted-foreground">
            Set up your account, then create your shop and add your team.
          </p>
        </div>
      </CardHeader>

      <CardContent>
        {/* POST: a submit that beats hydration must not put the password in the URL */}
        <form method="post" onSubmit={handleSubmit} noValidate className="space-y-6">
          <FieldGroup>
            <FormField id="fullName" label="Full name" error={errors.fullName}>
              <InputGroup>
                <InputGroupAddon>
                  <UserRound aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  id="fullName"
                  name="name"
                  autoComplete="name"
                  placeholder="Tariq Mehmood"
                  value={fullName}
                  onChange={change('fullName', setFullName)}
                  aria-invalid={Boolean(errors.fullName)}
                  aria-describedby={describe('fullName')}
                  maxLength={120}
                  required
                />
              </InputGroup>
            </FormField>

            <FormField id="garageName" label="Shop or garage name" optional>
              <InputGroup>
                <InputGroupAddon>
                  <Building2 aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  id="garageName"
                  name="organization"
                  autoComplete="organization"
                  placeholder="Falcon Auto Works"
                  value={garageName}
                  onChange={(event) => setGarageName(event.target.value)}
                  maxLength={120}
                />
              </InputGroup>
            </FormField>

            <div className="grid gap-5 @md/field-group:grid-cols-2">
              <FormField id="email" label="E-mail" error={errors.email}>
                <InputGroup>
                  <InputGroupAddon>
                    <Mail aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    id="email"
                    name="email"
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    placeholder="tariq@falconauto.pk"
                    value={email}
                    onChange={change('email', setEmail)}
                    aria-invalid={Boolean(errors.email)}
                    aria-describedby={describe('email')}
                    maxLength={254}
                    required
                  />
                </InputGroup>
              </FormField>

              <FormField id="phone" label="Phone" optional error={errors.phone}>
                <InputGroup>
                  <InputGroupAddon>
                    <Phone aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    id="phone"
                    name="tel"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="+92 300 1234567"
                    value={phone}
                    onChange={change('phone', setPhone)}
                    aria-invalid={Boolean(errors.phone)}
                    aria-describedby={describe('phone')}
                    maxLength={21}
                  />
                </InputGroup>
              </FormField>
            </div>

            <FormField id="password" label="Password" error={errors.password}>
              <InputGroup>
                <InputGroupAddon>
                  <Lock aria-hidden="true" />
                </InputGroupAddon>
                <InputGroupInput
                  id="password"
                  name="new-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder={`At least ${PASSWORD_MIN} characters`}
                  value={password}
                  onChange={change('password', setPassword)}
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={describe('password', 'password-strength')}
                  maxLength={PASSWORD_MAX}
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
              <PasswordStrength id="password-strength" password={password} />
            </FormField>
          </FieldGroup>

          <Alert variant="info">
            <Info aria-hidden="true" />
            <AlertDescription>
              Staff accounts are created by the shop owner. Work in a garage? Ask your owner for
              your login.
            </AlertDescription>
          </Alert>

          <Button type="submit" size="lg" disabled={loading} className="w-full">
            {loading ? (
              <>
                <Spinner aria-hidden="true" />
                Creating your account…
              </>
            ) : (
              <>
                Create account
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </>
            )}
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center border-t text-center text-sm text-muted-foreground">
        <p>
          Already have an account?{' '}
          <Link
            href="/login"
            className="font-semibold text-brand-blue-ink underline-offset-4 hover:underline"
          >
            Log in
          </Link>
        </p>
      </CardFooter>
    </Card>
  )
}

/** P-05 "Access": a logged-in visitor opens a shop instead of registering again (D17). */
function SignedInNotice({ name, onLogOut }: { name: string; onLogOut: () => void }) {
  return (
    <Card className="w-full">
      <CardHeader className="gap-2">
        <h1 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl">
          You&apos;re logged in as {name}
        </h1>
        <p className="text-base text-muted-foreground">
          Any BayFlow account can open a shop, and you become its owner. To register a different
          owner account, log out first.
        </p>
      </CardHeader>
      <CardContent className="flex-col gap-3 sm:flex-row">
        <Button asChild size="lg" className="w-full sm:w-auto">
          <Link href="/pos/shops/new">
            <Plus data-icon="inline-start" aria-hidden="true" />
            Create a new shop
          </Link>
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full sm:w-auto"
          onClick={onLogOut}
        >
          <LogOut data-icon="inline-start" aria-hidden="true" />
          Log out
        </Button>
      </CardContent>
    </Card>
  )
}
