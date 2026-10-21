'use client'

import { CalendarCheck, ClipboardCheck, PackageSearch, Wrench, type LucideIcon } from 'lucide-react'

import { ROLE_NAME } from '@/components/layout/account-menu'
import { Badge } from '@/components/ui/badge'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  FieldTitle,
} from '@/components/ui/field'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'

import { ROLE_DUTY, STAFF_ROLES, type StaffRole } from './team-data'

/** The icon of each role's own area in the shop sidebar (bookings, jobs, parts queue, QC queue). */
export const ROLE_ICON: Record<StaffRole, LucideIcon> = {
  SERVICE_ADVISOR: CalendarCheck,
  TECHNICIAN: Wrench,
  PARTS_PERSON: PackageSearch,
  QC_INSPECTOR: ClipboardCheck,
}

export interface RoleChoiceProps {
  /** Prefix for the radio ids, unique on the page. */
  idPrefix: string
  value: StaffRole
  onValueChange: (role: StaffRole) => void
  /** The member's role today, marked "Current" (change-role dialog). */
  current?: StaffRole
  /** The id of the visible label of the group. */
  labelledBy: string
}

/** The four staff roles as choice cards (radio group): icon, role name and what the role does. */
export function RoleChoice({
  idPrefix,
  value,
  onValueChange,
  current,
  labelledBy,
}: RoleChoiceProps) {
  return (
    <RadioGroup
      value={value}
      onValueChange={(next) => onValueChange(next as StaffRole)}
      aria-labelledby={labelledBy}
      className="gap-2"
    >
      {STAFF_ROLES.map((role) => {
        const Icon = ROLE_ICON[role]
        const id = `${idPrefix}-${role.toLowerCase()}`
        return (
          <FieldLabel key={role} htmlFor={id} className="*:data-[slot=field]:p-3">
            <Field orientation="horizontal" className="gap-3">
              <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-blue-subtle text-brand-blue-ink transition-colors duration-150 group-has-data-checked/field-label:bg-primary group-has-data-checked/field-label:text-primary-foreground"
              >
                <Icon className="size-[18px]" />
              </span>
              <FieldContent className="min-w-0 gap-0.5">
                <FieldTitle id={`${id}-name`}>
                  {ROLE_NAME[role]}
                  {role === current ? <Badge variant="secondary">Current</Badge> : null}
                </FieldTitle>
                <FieldDescription id={`${id}-duty`}>{ROLE_DUTY[role]}</FieldDescription>
              </FieldContent>
              {/* The radio is a button: name it from the title (a wrapping label isn't enough
                  for every screen reader), and describe it with the duty. */}
              <RadioGroupItem
                value={role}
                id={id}
                aria-labelledby={`${id}-name`}
                aria-describedby={`${id}-duty`}
              />
            </Field>
          </FieldLabel>
        )
      })}
    </RadioGroup>
  )
}
