import { PASSWORD_MAX, PASSWORD_MIN } from '@/components/auth/password-strength'
import { ROLE_NAME } from '@/components/layout/account-menu'
import {
  ASSIGNABLE_ROLES,
  openJobs,
  plural,
  sortTeam,
} from '@/components/pos/overview/overview-data'
import type { MockBooking, MockTeamMember } from '@/lib/mock-data'

/**
 * O-02 Team management (spec 10): the rules of `POST` / `PATCH /api/v1/shops/{shop_id}/members`
 * (E-26, E-27) worked out on the mock store, so the screen already behaves the way the API will.
 */

export type MemberRole = MockTeamMember['role']

/** A role the owner can give (glossary §2.1 `StaffRole`): never `OWNER` (D19). */
export type StaffRole = Exclude<MemberRole, 'OWNER'>

/** Glossary order, as in the shop overview's team card. */
export const STAFF_ROLES: ReadonlyArray<StaffRole> = [
  'SERVICE_ADVISOR',
  'TECHNICIAN',
  'PARTS_PERSON',
  'QC_INSPECTOR',
]

/** What each role does in the workflow (spec 06), shown beside the role choice. */
export const ROLE_DUTY: Record<StaffRole, string> = {
  SERVICE_ADVISOR: 'Intake, estimates and hand-over',
  TECHNICIAN: 'Inspections and repairs',
  PARTS_PERSON: 'Parts, stock and purchase orders',
  QC_INSPECTOR: 'Safety checks and road tests',
}

/** The role tiles' labels (plural, sentence case). */
export const ROLE_GROUP: Record<StaffRole, string> = {
  SERVICE_ADVISOR: 'Service advisors',
  TECHNICIAN: 'Technicians',
  PARTS_PERSON: 'Parts staff',
  QC_INSPECTOR: 'QC inspectors',
}

export function isStaffRole(role: MemberRole): role is StaffRole {
  return role !== 'OWNER'
}

export const NAME_MAX = 120
export const EMAIL_MAX = 254
/** Prefilled initial password: the one every demo account uses. */
export const DEMO_PASSWORD = 'BayFlow@2026'

/** One `@` with text on both sides, so reserved addresses such as `x@test` pass (D62). */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+$/

export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase()
}

export interface MemberDraft {
  fullName: string
  email: string
  role: StaffRole
  password: string
}

export type DraftField = 'fullName' | 'email' | 'password'
export type DraftErrors = Partial<Record<DraftField, string>>

/** Focus order for the first error after a refused submit. */
export const DRAFT_FIELDS: ReadonlyArray<DraftField> = ['fullName', 'email', 'password']

export const ALREADY_MEMBER = 'Already a member of this shop.'
export const PASSWORD_NEEDED = `Enter an initial password of ${PASSWORD_MIN} to ${PASSWORD_MAX} characters: this e-mail doesn't have a BayFlow account yet.`

/** E-26 field rules: full name 1–120, e-mail ≤ 254 (D62), password 12–128 when given (D10). */
export function validateDraft(draft: MemberDraft): DraftErrors {
  const errors: DraftErrors = {}
  const name = draft.fullName.trim()
  if (!name) errors.fullName = 'Enter their full name.'
  else if (name.length > NAME_MAX) errors.fullName = `Use ${NAME_MAX} characters or fewer.`

  const email = draft.email.trim()
  if (!email) errors.email = 'Enter their e-mail address.'
  else if (email.length > EMAIL_MAX || !EMAIL_PATTERN.test(email))
    errors.email = 'Enter a valid e-mail address, like name@example.com.'

  const { password } = draft
  if (password && (password.length < PASSWORD_MIN || password.length > PASSWORD_MAX))
    errors.password = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`
  return errors
}

export type AddMemberPlan =
  | { ok: false; errors: DraftErrors }
  | { ok: true; member: MockTeamMember; existingAccount: boolean }

/**
 * E-26 on the mock store: field rules first (422), then "already a member" (409, active or not),
 * then the password, which only a new account needs. An e-mail that already has a BayFlow account
 * only gains the membership: its name and password stay as they are (D18).
 */
export function planAddMember(
  draft: MemberDraft,
  context: {
    id: string
    shopId: string
    /** The shop's members, inactive ones included. */
    team: ReadonlyArray<Pick<MockTeamMember, 'email'>>
    /** Every BayFlow account (customers, staff, platform admins). */
    accounts: ReadonlyArray<{ email: string; name: string }>
  },
): AddMemberPlan {
  const errors = validateDraft(draft)
  if (Object.keys(errors).length > 0) return { ok: false, errors }

  const email = normaliseEmail(draft.email)
  if (context.team.some((member) => normaliseEmail(member.email) === email)) {
    return { ok: false, errors: { email: ALREADY_MEMBER } }
  }
  const account = context.accounts.find((a) => normaliseEmail(a.email) === email)
  if (!account && !draft.password) return { ok: false, errors: { password: PASSWORD_NEEDED } }

  return {
    ok: true,
    existingAccount: Boolean(account),
    member: {
      id: context.id,
      shopId: context.shopId,
      name: account?.name ?? draft.fullName.trim(),
      email,
      role: draft.role,
      is_active: true,
    },
  }
}

/**
 * D19 and the last-owner rule: the `OWNER` membership is never re-roled or deactivated (and no
 * one can be made an owner here), so every shop keeps its owner; nobody edits their own row.
 */
export function canEditMember(member: Pick<MockTeamMember, 'role' | 'email'>, selfEmail: string) {
  return member.role !== 'OWNER' && normaliseEmail(member.email) !== normaliseEmail(selfEmail)
}

export interface MemberRow {
  member: MockTeamMember
  /** E-25 `open_jobs`; `null` for an owner or advisor, who are never assigned jobs, with none. */
  openJobs: number | null
  isSelf: boolean
  /** Whether the row menu (change role, deactivate / reactivate) is offered (R1, D19). */
  editable: boolean
}

/** The table rows: by role, then name (as on the shop overview), with `open_jobs` worked out. */
export function memberRows(
  team: ReadonlyArray<MockTeamMember>,
  bookings: ReadonlyArray<MockBooking>,
  selfEmail: string,
  canManage: boolean,
): MemberRow[] {
  const self = normaliseEmail(selfEmail)
  return sortTeam(team).map((member) => {
    const count = openJobs(member.id, bookings)
    return {
      member,
      openJobs: ASSIGNABLE_ROLES.has(member.role) || count > 0 ? count : null,
      isSelf: normaliseEmail(member.email) === self,
      editable: canManage && canEditMember(member, selfEmail),
    }
  })
}

export interface RoleCoverage {
  role: StaffRole
  active: number
  inactive: number
}

/** Who covers each step of the workflow: active and inactive members per staff role. */
export function roleCoverage(team: ReadonlyArray<MockTeamMember>): RoleCoverage[] {
  return STAFF_ROLES.map((role) => ({
    role,
    active: team.filter((m) => m.role === role && m.is_active).length,
    inactive: team.filter((m) => m.role === role && !m.is_active).length,
  }))
}

/** "7 members · all active", "7 members · 1 inactive". */
export function teamSummary(team: ReadonlyArray<MockTeamMember>): string {
  const inactive = team.filter((m) => !m.is_active).length
  return `${plural(team.length, 'member')} · ${inactive === 0 ? 'all active' : `${inactive} inactive`}`
}

/** The deactivation warning (spec 10 O-02; D9: their bookings stay assigned, D19). */
export function deactivateMessage(name: string, shopName: string, jobs: number | null): string {
  const access = `${name} loses access to ${shopName} immediately.`
  if (jobs === 1) return `${access} Their open job stays assigned — reassign it from the booking.`
  if (jobs !== null && jobs > 1) {
    return `${access} Their ${jobs} open jobs stay assigned — reassign them from each booking.`
  }
  return `${access} You can reactivate them at any time.`
}

export function roleName(role: MemberRole): string {
  return ROLE_NAME[role]
}
