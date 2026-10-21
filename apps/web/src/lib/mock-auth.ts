import { getAdminUsers, type AdminMembership, type AdminUser } from '@/lib/mock-admin'
import { normaliseEmail, type CurrentUserSession } from '@/lib/mock-data'

/**
 * Stand-in for `POST /api/v1/auth/login` + `GET /api/v1/me` while the screens run on mock data.
 * Any password is accepted, but nobody is signed in by anything except this form (D52: no
 * auto-login, no bypass). The e-mail is looked up as an account first — the shop memberships,
 * the platform admin flag (D94) and the customers known from their bookings — and the session
 * opens where spec 09 `resolveHome` sends that account. Only an e-mail the mock does not know
 * falls back to the keyword rules below, and it never gets a shop: a shop is reached through a
 * membership only (D20). Replaced by the real API client (spec 09 §2.8).
 */

type Role = CurrentUserSession['role']

const NO_SHOP = { shopId: '', shopName: '' }

/**
 * For e-mails the mock doesn't know: the role a word in the address suggests. Tokens are matched
 * whole (`sara.qc` is QC, not Service Advisor because it contains "sa").
 */
const RULES: ReadonlyArray<{ tokens: ReadonlyArray<string>; role: Role }> = [
  { tokens: ['admin'], role: 'PLATFORM_ADMIN' },
  { tokens: ['owner'], role: 'OWNER' },
  { tokens: ['tech', 'technician'], role: 'TECHNICIAN' },
  { tokens: ['qc'], role: 'QC_INSPECTOR' },
  { tokens: ['parts'], role: 'PARTS_PERSON' },
  { tokens: ['sa', 'advisor'], role: 'SERVICE_ADVISOR' },
  { tokens: ['customer'], role: 'CUSTOMER' },
]

function capitalise(word: string) {
  return word ? word[0]!.toUpperCase() + word.slice(1) : word
}

/** By shop name, then id: the order of `/me`, the hub and the shop switcher. */
function byShopName(a: AdminMembership, b: AdminMembership) {
  return a.shopName.localeCompare(b.shopName) || a.shopId.localeCompare(b.shopId)
}

/**
 * A known account's session. Staff open their first shop as Owner by name, else their first shop
 * by name (spec 11 "first login": Fatima → Lahore Auto Care). A platform admin without
 * memberships opens the console (spec 19 §5). Anyone else — a customer, or someone whose
 * memberships were all deactivated (D19) — has no shop and lands on My bookings.
 */
function accountSession(account: AdminUser): CurrentUserSession {
  const memberships = account.memberships.filter((m) => m.isActive).sort(byShopName)
  const home = memberships.find((m) => m.role === 'OWNER') ?? memberships[0]
  const person = { email: account.email, name: account.name }
  if (home) return { ...person, role: home.role, shopId: home.shopId, shopName: home.shopName }
  if (account.isPlatformAdmin) return { ...person, role: 'PLATFORM_ADMIN', ...NO_SHOP }
  return { ...person, role: 'CUSTOMER', ...NO_SHOP }
}

export function resolveMockSession(rawEmail: string): CurrentUserSession {
  const email = normaliseEmail(rawEmail)
  const account = getAdminUsers().find((user) => user.email === email)
  if (account) return accountSession(account)

  const local = email.split('@')[0] ?? ''
  const tokens = local.split(/[._+-]+/).filter(Boolean)
  const rule = RULES.find((r) => r.tokens.some((t) => tokens.includes(t)))
  return {
    email,
    role: rule?.role ?? 'OWNER',
    name: capitalise(tokens[0] ?? 'User'),
    ...NO_SHOP,
  }
}

/** Where each persona lands after login (spec 10 S-04 role homes; customers go to C-01; platform
 * admins to the console, spec 19 §5). Staff without a shop go to the POS hub (S-02). */
export function homePathFor(session: Pick<CurrentUserSession, 'role' | 'shopId'>): string {
  if (session.role === 'CUSTOMER') return '/bookings'
  if (session.role === 'PLATFORM_ADMIN') return '/admin'
  if (!session.shopId) return '/pos'
  const shop = `/pos/shops/${session.shopId}`
  switch (session.role) {
    case 'OWNER':
      return `${shop}/overview`
    case 'SERVICE_ADVISOR':
      return `${shop}/bookings`
    case 'TECHNICIAN':
      return `${shop}/jobs`
    case 'PARTS_PERSON':
      return `${shop}/parts`
    case 'QC_INSPECTOR':
      return `${shop}/qc`
  }
}
