import type { AdminShop, AdminUser, StaffRole } from '@/lib/mock-admin'

/**
 * A-02 Shops (spec 19 §5; E-62 once wired): the directory's filters, with the API's rules — status
 * (active / suspended), directory listing, city and a text search over name, slug, city and owner
 * e-mails — newest shop first.
 */

export type StatusFilter = 'ALL' | 'ACTIVE' | 'SUSPENDED'
export type ListedFilter = 'ALL' | 'LISTED' | 'UNLISTED'

export interface ShopFilters {
  q: string
  status: StatusFilter
  /** A city name, or `ALL`. */
  city: string
  listed: ListedFilter
}

export const NO_FILTERS: ShopFilters = { q: '', status: 'ALL', city: 'ALL', listed: 'ALL' }

export function hasActiveFilters(filters: ShopFilters): boolean {
  return (
    filters.q.trim() !== '' ||
    filters.status !== 'ALL' ||
    filters.city !== 'ALL' ||
    filters.listed !== 'ALL'
  )
}

function matchesStatus(tenant: AdminShop, status: StatusFilter): boolean {
  if (status === 'ALL') return true
  return status === 'SUSPENDED' ? Boolean(tenant.suspension) : !tenant.suspension
}

function matchesRest(tenant: AdminShop, filters: ShopFilters): boolean {
  const needle = filters.q.trim().toLowerCase()
  return (
    (filters.city === 'ALL' || tenant.shop.city === filters.city) &&
    (filters.listed === 'ALL' || (filters.listed === 'LISTED') === tenant.shop.is_listed) &&
    (!needle ||
      [tenant.shop.name, tenant.shop.slug, tenant.shop.city, ...tenant.owners.map((o) => o.email)]
        .join(' ')
        .toLowerCase()
        .includes(needle))
  )
}

/** The shops that match every filter, newest first. */
export function filterShops(tenants: ReadonlyArray<AdminShop>, filters: ShopFilters): AdminShop[] {
  return tenants
    .filter((t) => matchesStatus(t, filters.status) && matchesRest(t, filters))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

/** How many shops each status pill would show, given the other filters. */
export function statusCounts(
  tenants: ReadonlyArray<AdminShop>,
  filters: ShopFilters,
): Record<StatusFilter, number> {
  const rest = tenants.filter((t) => matchesRest(t, filters))
  return {
    ALL: rest.length,
    ACTIVE: rest.filter((t) => !t.suspension).length,
    SUSPENDED: rest.filter((t) => Boolean(t.suspension)).length,
  }
}

/** Every city with a shop, A to Z. */
export function cityOptions(tenants: ReadonlyArray<AdminShop>): string[] {
  return [...new Set(tenants.map((t) => t.shop.city))].sort((a, b) => a.localeCompare(b))
}

/** Glossary §2.1 order: the owner first, then the roles in the order work flows. */
const ROLE_ORDER: ReadonlyArray<StaffRole> = [
  'OWNER',
  'SERVICE_ADVISOR',
  'TECHNICIAN',
  'PARTS_PERSON',
  'QC_INSPECTOR',
]

export interface TeamMember {
  user: AdminUser
  membership: AdminUser['memberships'][number]
}

/** Everyone with a membership in the shop (inactive ones too), by role and then name. */
export function shopTeam(users: ReadonlyArray<AdminUser>, shopId: string): TeamMember[] {
  return users
    .flatMap((user) =>
      user.memberships
        .filter((m) => m.shopId === shopId)
        .map((membership) => ({ user, membership })),
    )
    .sort(
      (a, b) =>
        ROLE_ORDER.indexOf(a.membership.role) - ROLE_ORDER.indexOf(b.membership.role) ||
        a.user.name.localeCompare(b.user.name),
    )
}
