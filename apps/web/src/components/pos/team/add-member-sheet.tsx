'use client'

import { Eye, EyeOff, Lock, Mail, UserRound } from 'lucide-react'
import { useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'

import { PASSWORD_MAX } from '@/components/auth/password-strength'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '@/components/ui/input-group'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

import { RoleChoice } from './role-choice'
import {
  DEMO_PASSWORD,
  DRAFT_FIELDS,
  EMAIL_MAX,
  NAME_MAX,
  validateDraft,
  type DraftErrors,
  type DraftField,
  type MemberDraft,
  type StaffRole,
} from './team-data'

const FIELD_ID: Record<DraftField, string> = {
  fullName: 'member-name',
  email: 'member-email',
  password: 'member-password',
}

function FormField({
  field,
  label,
  error,
  children,
}: {
  field: DraftField
  label: string
  error?: string
  children: ReactNode
}) {
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={FIELD_ID[field]}>{label}</FieldLabel>
      {children}
      {error ? <FieldError id={`${FIELD_ID[field]}-error`}>{error}</FieldError> : null}
    </Field>
  )
}

export interface AddMemberSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  shopName: string
  /** Saves the member, or returns the field errors that refused it (E-26 422 / 409). */
  onAdd: (draft: MemberDraft) => DraftErrors | null
  /** Where focus goes when the sheet closes (call `preventDefault` to move it yourself). */
  onCloseAutoFocus?: (event: Event) => void
}

/**
 * "Add team member" (spec 10 O-02) in a right sheet: full name, e-mail, role and an initial
 * password (D10). Errors show on submit and clear as each field is fixed; the input survives a
 * refused submit and closing the sheet (R9).
 */
export function AddMemberSheet({
  open,
  onOpenChange,
  shopName,
  onAdd,
  onCloseAutoFocus,
}: AddMemberSheetProps) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<StaffRole>('TECHNICIAN')
  const [password, setPassword] = useState(DEMO_PASSWORD)
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<DraftErrors>({})

  const describe = (field: DraftField, extra?: string) =>
    [extra, errors[field] ? `${FIELD_ID[field]}-error` : null].filter(Boolean).join(' ') ||
    undefined

  /** Once a field shows an error, it is re-checked as the owner fixes it. */
  const change =
    (field: DraftField, setValue: (value: string) => void) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value = event.target.value
      setValue(value)
      if (!errors[field]) return
      const next = validateDraft({ fullName, email, role, password, [field]: value })
      setErrors((current) => ({ ...current, [field]: next[field] }))
    }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const refused = onAdd({ fullName, email, role, password })
    if (refused) {
      setErrors(refused)
      const first = DRAFT_FIELDS.find((field) => refused[field])
      if (first) event.currentTarget.querySelector<HTMLInputElement>(`#${FIELD_ID[first]}`)?.focus()
      return
    }
    setErrors({})
    setFullName('')
    setEmail('')
    onOpenChange(false)
  }

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) setErrors({})
      }}
    >
      <SheetContent className="gap-0" onCloseAutoFocus={onCloseAutoFocus}>
        {/* POST: a submit that beats hydration must not put the password in the URL */}
        <form method="post" noValidate onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <SheetHeader>
            <SheetTitle>Add team member</SheetTitle>
            <SheetDescription>
              They sign in with their e-mail and get the screens of their role at {shopName}.
            </SheetDescription>
          </SheetHeader>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-6">
            <FieldGroup>
              <FormField field="fullName" label="Full name" error={errors.fullName}>
                <InputGroup>
                  <InputGroupAddon>
                    <UserRound aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    id={FIELD_ID.fullName}
                    name="full-name"
                    autoComplete="off"
                    placeholder="Kamran Abbasi"
                    value={fullName}
                    onChange={change('fullName', setFullName)}
                    aria-invalid={Boolean(errors.fullName)}
                    aria-describedby={describe('fullName')}
                    maxLength={NAME_MAX}
                    required
                  />
                </InputGroup>
              </FormField>

              <FormField field="email" label="E-mail" error={errors.email}>
                <InputGroup>
                  <InputGroupAddon>
                    <Mail aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    id={FIELD_ID.email}
                    name="member-email"
                    type="email"
                    inputMode="email"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="kamran.tech@bayflow.test"
                    value={email}
                    onChange={change('email', setEmail)}
                    aria-invalid={Boolean(errors.email)}
                    aria-describedby={describe('email')}
                    maxLength={EMAIL_MAX}
                    required
                  />
                </InputGroup>
              </FormField>

              <FieldSet>
                <FieldLegend variant="label" id="member-role-label">
                  Role
                </FieldLegend>
                <RoleChoice
                  idPrefix="member-role"
                  value={role}
                  onValueChange={setRole}
                  labelledBy="member-role-label"
                />
              </FieldSet>

              <FormField field="password" label="Initial password" error={errors.password}>
                <InputGroup>
                  <InputGroupAddon>
                    <Lock aria-hidden="true" />
                  </InputGroupAddon>
                  <InputGroupInput
                    id={FIELD_ID.password}
                    name="initial-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={change('password', setPassword)}
                    aria-invalid={Boolean(errors.password)}
                    aria-describedby={describe('password', 'member-password-help')}
                    maxLength={PASSWORD_MAX}
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
                <FieldDescription id="member-password-help">
                  At least 12 characters. Needed only if this person doesn&apos;t have a BayFlow
                  account yet — share it with them privately. Demo accounts use {DEMO_PASSWORD}.
                </FieldDescription>
              </FormField>
            </FieldGroup>
          </div>

          <SheetFooter className="flex-col-reverse sm:flex-row sm:justify-end">
            <SheetClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </SheetClose>
            <Button type="submit">Add team member</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}
