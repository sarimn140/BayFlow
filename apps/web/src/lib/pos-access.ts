import type { CurrentUserSession } from '@/lib/mock-data'

type Role = CurrentUserSession['role']
export type StaffRole = Exclude<Role, 'CUSTOMER' | 'PLATFORM_ADMIN'>
export type SectionAccess = 'manage' | 'read'

/**
 * Spec 10 S-01 role navigation matrix: which shop sections each role opens, and whether the
 * Owner's view of another role's queue is read-only (D16). Navigation scope only; the API
 * enforces every permission (spec 09 §2.8).
 */
export const SECTION_ACCESS: Readonly<Record<string, Partial<Record<StaffRole, SectionAccess>>>> = {
  overview: { OWNER: 'manage' },
  bookings: { OWNER: 'manage', SERVICE_ADVISOR: 'manage' },
  calls: { OWNER: 'manage', SERVICE_ADVISOR: 'manage' }, // AI calls & tasks (spec 05 §6.5, D21)
  jobs: { OWNER: 'read', TECHNICIAN: 'manage' },
  parts: { OWNER: 'read', PARTS_PERSON: 'manage' },
  inventory: { OWNER: 'manage', PARTS_PERSON: 'manage' },
  'purchase-orders': { OWNER: 'read', PARTS_PERSON: 'manage' },
  qc: { OWNER: 'read', QC_INSPECTOR: 'manage' },
  team: { OWNER: 'manage' },
  services: { OWNER: 'manage' },
  settings: { OWNER: 'manage' },
}

/** How `role` may use a shop section; `null` when it is another role's area (X-03). */
export function sectionAccess(role: Role, segment: string): SectionAccess | null {
  const rule = SECTION_ACCESS[segment]
  if (!rule) return 'manage' // not a gated section (e.g. the role-home redirect)
  // Customers and platform admins have no shop role (a platform admin manages shops from /admin).
  if (role === 'CUSTOMER' || role === 'PLATFORM_ADMIN') return null
  return rule[role] ?? null
}

const AUDIENCE: Record<StaffRole, string> = {
  OWNER: 'Owners',
  SERVICE_ADVISOR: 'Service Advisors',
  TECHNICIAN: 'Technicians',
  PARTS_PERSON: 'Parts staff',
  QC_INSPECTOR: 'QC inspectors',
}

/** X-03 copy, e.g. "This area is for Service Advisors and Owners." */
export function sectionAudience(segment: string): string {
  const roles = Object.keys(SECTION_ACCESS[segment] ?? {}) as StaffRole[]
  const ordered = [...roles.filter((r) => r !== 'OWNER'), ...roles.filter((r) => r === 'OWNER')]
  const names = ordered.map((role) => AUDIENCE[role])
  if (names.length === 0) return 'This area is for other roles.'
  const list =
    names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
  return `This area is for ${list}.`
}

/** The shop section a POS path belongs to: `/pos/shops/{id}/{section}/…` → `section`. */
export function sectionOf(pathname: string): string | null {
  const [, pos, shops, shopId, section] = pathname.split('/')
  return pos === 'pos' && shops === 'shops' && shopId && section ? section : null
}
