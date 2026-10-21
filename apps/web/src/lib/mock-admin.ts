import { bookingHistory, type HistoryActorRole } from '@/lib/mock-booking-history'
import {
  getBookings,
  getShops,
  getStoredData,
  getTeamMembers,
  setStoredData,
  type MockBooking,
  type MockShop,
  type MockTeamMember,
} from '@/lib/mock-data'

/**
 * Platform administration (spec 19) while the screens run on mock data: the people and tenants a
 * platform admin manages, shop suspension (D96), account flags (D94) and the audit log (D95). The
 * rules mirror the API (E-61…E-75) so the console behaves as it will once wired: self and
 * last-admin safeguards, reasons, 409s for no-op changes, and an append-only audit trail.
 */

// --- Types ---------------------------------------------------------------------------------------

export type StaffRole = MockTeamMember['role']
export type AdminUserKind = 'CUSTOMER' | 'STAFF' | 'PLATFORM_ADMIN'
export type AuditCategory = 'AUTH' | 'USER' | 'SHOP' | 'MEMBERSHIP' | 'BOOKING' | 'ADMIN'
export type AuditActorRole = StaffRole | HistoryActorRole | 'PLATFORM_ADMIN' | 'ANONYMOUS'

export interface AdminMembership {
  shopId: string
  shopName: string
  shopSlug: string
  role: StaffRole
  isActive: boolean
}

export interface AdminUser {
  id: string
  name: string
  email: string
  phone: string | null
  isActive: boolean
  isPlatformAdmin: boolean
  kind: AdminUserKind
  createdAt: string
  lastLoginAt: string | null
  memberships: AdminMembership[]
}

export interface ShopSuspension {
  at: string
  reason: string
  byName: string
  byEmail: string
}

export interface AdminShop {
  shop: MockShop
  createdAt: string
  owners: { name: string; email: string }[]
  activeMembers: number
  bookingsTotal: number
  suspension: ShopSuspension | null
}

export interface AuditEvent {
  id: string
  occurredAt: string
  category: AuditCategory
  action: string
  summary: string
  actor: { name: string; email: string | null; role: AuditActorRole } | null
  shop: { id: string; name: string; slug: string } | null
  target: { type: 'USER' | 'SHOP' | 'MEMBERSHIP' | 'BOOKING'; id: string; label: string } | null
  metadata: Record<string, unknown>
  ip: string | null
  userAgent: string | null
  requestId: string | null
}

/** Who performs an admin action: the signed-in platform admin. */
export interface AdminActor {
  name: string
  email: string
}

/** The API's answer to an action it refuses (spec 19 §1). */
export class AdminActionError extends Error {
  constructor(
    readonly code: 'FORBIDDEN' | 'CONFLICT' | 'VALIDATION_ERROR',
    message: string,
  ) {
    super(message)
    this.name = 'AdminActionError'
  }
}

// --- Seed facts ----------------------------------------------------------------------------------

/** The seeded platform admin (spec 19 §8). */
export const PLATFORM_ADMIN_ACCOUNT = {
  id: 'usr-areeba',
  name: 'Areeba Hashmi',
  email: 'admin@bayflow.test',
  phone: '+92 300 0001122',
  createdAt: '2026-09-01T06:00:00Z',
} as const

/** When each demo shop joined BayFlow. */
const SHOP_JOINED: Record<string, string> = {
  'shop-lahore-auto-care': '2026-09-03T05:00:00Z',
  'shop-raza-auto-works': '2026-09-12T07:30:00Z',
  'shop-clifton-car-clinic': '2026-09-15T06:00:00Z',
  'shop-margalla-motor-works': '2026-09-19T09:15:00Z',
  'shop-pindi-auto-garage': '2026-09-24T08:00:00Z',
  'shop-lyallpur-motors': '2026-09-28T10:45:00Z',
}

/** Recent sign-ins, so the console has a security trail before anyone uses it. */
const SEED_LOGINS: ReadonlyArray<{ email: string; at: string; ua: number }> = [
  { email: 'fatima.owner@bayflow.test', at: '2026-10-09T03:30:00Z', ua: 0 },
  { email: 'bilal.sa@bayflow.test', at: '2026-10-09T03:55:00Z', ua: 1 },
  { email: 'imran.tech@bayflow.test', at: '2026-10-09T04:02:00Z', ua: 2 },
  { email: 'usman.parts@bayflow.test', at: '2026-10-09T04:15:00Z', ua: 1 },
  { email: 'sara.qc@bayflow.test', at: '2026-10-09T08:10:00Z', ua: 2 },
  { email: 'ayesha.customer@bayflow.test', at: '2026-10-09T11:20:00Z', ua: 3 },
  { email: 'admin@bayflow.test', at: '2026-10-09T02:50:00Z', ua: 0 },
]

const SEED_FAILED_LOGINS: ReadonlyArray<{ email: string; at: string }> = [
  { email: 'bilal.sa@bayflow.test', at: '2026-10-09T03:54:00Z' },
  { email: 'admin@bayfIow.test', at: '2026-10-09T07:41:00Z' },
  { email: 'admin@bayfIow.test', at: '2026-10-09T07:41:30Z' },
]

const USER_AGENTS = [
  'Chrome 130 on Windows',
  'Edge 130 on Windows',
  'Chrome 130 on Android',
  'Safari on iPhone',
] as const

/** Documentation-only addresses (RFC 5737), never real ones. */
function demoIp(seed: string): string {
  let hash = 0
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return `${hash % 2 === 0 ? '203.0.113' : '198.51.100'}.${(hash % 200) + 10}`
}

function demoRequestId(seed: string): string {
  let a = 0x811c9dc5
  let b = 0x01000193
  for (const char of seed) {
    a = Math.imul(a ^ char.charCodeAt(0), 0x01000193) >>> 0
    b = Math.imul(b ^ char.charCodeAt(0), 0x811c9dc5) >>> 0
  }
  const hex = (n: number) => n.toString(16).padStart(8, '0')
  return `${hex(a)}-${hex(b).slice(0, 4)}-4${hex(b).slice(4, 7)}-${hex(a ^ b).slice(0, 4)}-${hex(b)}${hex(a).slice(0, 4)}`
}

const STAFF_JOINED_BASE = Date.parse('2026-09-03T06:00:00Z')

/** An owner registers, then creates the shop a quarter of an hour later. */
const OWNER_REGISTERED_BEFORE_SHOP = 15 * 60e3

// --- Stores --------------------------------------------------------------------------------------

const SUSPENSIONS_KEY = 'admin-shop-suspensions'
const USER_FLAGS_KEY = 'admin-user-flags'
const AUDIT_KEY = 'admin-audit-log'

type UserFlags = Record<string, { isActive?: boolean; isPlatformAdmin?: boolean }>

const NO_SUSPENSIONS: Record<string, ShopSuspension> = {}
const NO_FLAGS: UserFlags = {}
const NO_EVENTS: AuditEvent[] = []

export function getShopSuspensions(): Record<string, ShopSuspension> {
  return getStoredData(SUSPENSIONS_KEY, NO_SUSPENSIONS)
}

function getUserFlags(): UserFlags {
  return getStoredData(USER_FLAGS_KEY, NO_FLAGS)
}

/** Events recorded in this browser (admin actions, sign-ins), oldest first. */
function getLiveAudit(): AuditEvent[] {
  return getStoredData(AUDIT_KEY, NO_EVENTS)
}

// --- Memoisation over the stores' snapshots (useMockStore needs stable results) ------------------

function memo<R>(compute: (...sources: object[]) => R) {
  const root = new WeakMap<object, unknown>()
  return (...sources: object[]): R => {
    let level: WeakMap<object, unknown> = root
    for (const [index, source] of sources.entries()) {
      const last = index === sources.length - 1
      if (last) {
        if (!level.has(source)) level.set(source, compute(...sources))
        return level.get(source) as R
      }
      let next = level.get(source) as WeakMap<object, unknown> | undefined
      if (!next) {
        next = new WeakMap()
        level.set(source, next)
      }
      level = next
    }
    return compute()
  }
}

// --- Directory -----------------------------------------------------------------------------------

interface BaseUser extends Omit<
  AdminUser,
  'isActive' | 'isPlatformAdmin' | 'kind' | 'lastLoginAt'
> {
  seedAdmin: boolean
}

function shopRef(shops: ReadonlyArray<MockShop>, shopId: string) {
  const shop = shops.find((s) => s.id === shopId)
  return { shopId, shopName: shop?.name ?? shopId, shopSlug: shop?.slug ?? shopId }
}

const baseDirectory = memo(
  (teamSource: object, bookingsSource: object, shopsSource: object): BaseUser[] => {
    const team = teamSource as MockTeamMember[]
    const bookings = bookingsSource as MockBooking[]
    const shops = shopsSource as MockShop[]
    const byEmail = new Map<string, BaseUser>()

    byEmail.set(PLATFORM_ADMIN_ACCOUNT.email, {
      id: PLATFORM_ADMIN_ACCOUNT.id,
      name: PLATFORM_ADMIN_ACCOUNT.name,
      email: PLATFORM_ADMIN_ACCOUNT.email,
      phone: PLATFORM_ADMIN_ACCOUNT.phone,
      createdAt: PLATFORM_ADMIN_ACCOUNT.createdAt,
      memberships: [],
      seedAdmin: true,
    })

    // Spec 11: each seeded shop's owner registers (a quarter of an hour before the shop is
    // created, as the audit log records it), then adds the team, one person an hour, in team order.
    const placeInShop = new Map<string, number>()
    team.forEach((member, index) => {
      const email = member.email.toLowerCase()
      const membership: AdminMembership = {
        ...shopRef(shops, member.shopId),
        role: member.role,
        isActive: member.is_active,
      }
      const place = placeInShop.get(member.shopId) ?? 0
      placeInShop.set(member.shopId, place + 1)
      const existing = byEmail.get(email)
      if (existing) {
        existing.memberships.push(membership)
        return
      }
      const shopJoined = SHOP_JOINED[member.shopId]
      const joined = !shopJoined
        ? STAFF_JOINED_BASE + index * 36e5
        : member.role === 'OWNER'
          ? Date.parse(shopJoined) - OWNER_REGISTERED_BEFORE_SHOP
          : Date.parse(shopJoined) + place * 36e5
      byEmail.set(email, {
        id: member.id,
        name: member.name,
        email,
        phone: null,
        createdAt: new Date(joined).toISOString(),
        memberships: [membership],
        seedAdmin: false,
      })
    })

    const firstBooking = new Map<string, MockBooking>()
    for (const b of bookings) {
      const email = b.customerEmail.toLowerCase()
      const seen = firstBooking.get(email)
      if (!seen || b.createdAt < seen.createdAt) firstBooking.set(email, b)
    }
    for (const [email, b] of firstBooking) {
      if (byEmail.has(email)) continue
      byEmail.set(email, {
        id: `cus-${email.split('@')[0]!.replace(/[^a-z0-9]+/g, '-')}`,
        name: b.customerName,
        email,
        phone: b.customerPhone,
        createdAt: b.createdAt,
        memberships: [],
        seedAdmin: false,
      })
    }
    return [...byEmail.values()]
  },
)

const directory = memo(
  (
    teamSource: object,
    bookingsSource: object,
    shopsSource: object,
    flagsSource: object,
    auditSource: object,
  ): AdminUser[] => {
    const base = baseDirectory(teamSource, bookingsSource, shopsSource)
    const flags = flagsSource as UserFlags
    const audit = auditSource as AuditEvent[]
    const lastLogin = new Map<string, string>()
    for (const event of audit) {
      if (event.action !== 'auth.login_succeeded' || !event.actor?.email) continue
      const prev = lastLogin.get(event.actor.email)
      if (!prev || event.occurredAt > prev) lastLogin.set(event.actor.email, event.occurredAt)
    }
    return base
      .map((user) => {
        const isActive = flags[user.id]?.isActive ?? true
        const isPlatformAdmin = flags[user.id]?.isPlatformAdmin ?? user.seedAdmin
        const staff = user.memberships.some((m) => m.isActive)
        return {
          id: user.id,
          name: user.name,
          email: user.email,
          phone: user.phone,
          createdAt: user.createdAt,
          memberships: user.memberships,
          isActive,
          isPlatformAdmin,
          kind: isPlatformAdmin ? 'PLATFORM_ADMIN' : staff ? 'STAFF' : 'CUSTOMER',
          lastLoginAt: lastLogin.get(user.email) ?? null,
        } satisfies AdminUser
      })
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  },
)

/** Every account on the platform, newest first (E-66's default order). */
export function getAdminUsers(): AdminUser[] {
  return directory(getTeamMembers(), getBookings(), getShops(), getUserFlags(), getAuditEvents())
}

// --- Tenants -------------------------------------------------------------------------------------

const tenants = memo(
  (
    shopsSource: object,
    usersSource: object,
    bookingsSource: object,
    suspensionsSource: object,
  ): AdminShop[] => {
    const shops = shopsSource as MockShop[]
    const users = usersSource as AdminUser[]
    const bookings = bookingsSource as MockBooking[]
    const suspensions = suspensionsSource as Record<string, ShopSuspension>
    return shops.map((shop) => {
      const members = users.flatMap((u) =>
        u.memberships
          .filter((m) => m.shopId === shop.id && m.isActive && u.isActive)
          .map((m) => ({ user: u, membership: m })),
      )
      return {
        shop,
        createdAt: SHOP_JOINED[shop.id] ?? '2026-09-01T00:00:00Z',
        owners: members
          .filter(({ membership }) => membership.role === 'OWNER')
          .map(({ user }) => ({ name: user.name, email: user.email })),
        activeMembers: members.length,
        bookingsTotal: bookings.filter((b) => b.shopId === shop.id).length,
        suspension: suspensions[shop.id] ?? null,
      }
    })
  },
)

/** Every shop with its owners, size and suspension, in directory order. */
export function getAdminShops(): AdminShop[] {
  return tenants(getShops(), getAdminUsers(), getBookings(), getShopSuspensions())
}

export function getShopSuspension(shopId: string): ShopSuspension | null {
  return getShopSuspensions()[shopId] ?? null
}

// --- Audit log -----------------------------------------------------------------------------------

function seedEvent(event: Omit<AuditEvent, 'ip' | 'userAgent' | 'requestId'>, ua?: number) {
  return {
    ...event,
    ip: event.actor ? demoIp(`${event.actor.email}:${event.occurredAt}`) : demoIp(event.id),
    userAgent: USER_AGENTS[(ua ?? event.id.length) % USER_AGENTS.length]!,
    requestId: demoRequestId(event.id),
  } satisfies AuditEvent
}

const auditLog = memo(
  (
    teamSource: object,
    bookingsSource: object,
    shopsSource: object,
    liveSource: object,
  ): AuditEvent[] => {
    const base = baseDirectory(teamSource, bookingsSource, shopsSource)
    const bookings = bookingsSource as MockBooking[]
    const shops = shopsSource as MockShop[]
    const live = liveSource as AuditEvent[]
    const userByEmail = new Map(base.map((u) => [u.email, u]))
    const shopOf = (id: string) => {
      const s = shops.find((shop) => shop.id === id)
      return s ? { id: s.id, name: s.name, slug: s.slug } : null
    }
    const events: AuditEvent[] = []

    // Owners registered (once, before their first shop) and created their shops.
    const ownerOf = (shopId: string) =>
      base.find((u) => u.memberships.some((m) => m.shopId === shopId && m.role === 'OWNER'))
    const registered = new Set<string>()
    for (const shop of shops) {
      const owner = ownerOf(shop.id)
      const at = SHOP_JOINED[shop.id] ?? '2026-09-01T00:00:00Z'
      // Seeded owners only: a shop created in this browser has no seeded registration.
      if (owner && SHOP_JOINED[shop.id] && !registered.has(owner.id)) {
        registered.add(owner.id)
        events.push(
          seedEvent({
            id: `seed:auth.owner_registered:${owner.id}`,
            occurredAt: new Date(Date.parse(at) - OWNER_REGISTERED_BEFORE_SHOP).toISOString(),
            category: 'AUTH',
            action: 'auth.owner_registered',
            summary: `${owner.name} registered as a shop owner`,
            actor: { name: owner.name, email: owner.email, role: 'OWNER' },
            shop: null,
            target: { type: 'USER', id: owner.id, label: owner.email },
            metadata: {},
          }),
        )
      }
      events.push(
        seedEvent({
          id: `seed:shop.created:${shop.id}`,
          occurredAt: at,
          category: 'SHOP',
          action: 'shop.created',
          summary: `${owner?.name ?? 'The owner'} created ${shop.name}`,
          actor: owner ? { name: owner.name, email: owner.email, role: 'OWNER' } : null,
          shop: shopOf(shop.id),
          target: { type: 'SHOP', id: shop.id, label: shop.name },
          metadata: {},
        }),
      )
    }

    // Each shop's team was added by that shop's owner.
    for (const user of base) {
      for (const membership of user.memberships) {
        if (membership.role === 'OWNER') continue
        const owner = ownerOf(membership.shopId)
        events.push(
          seedEvent({
            id: `seed:membership.added:${membership.shopId}:${user.id}`,
            occurredAt: user.createdAt,
            category: 'MEMBERSHIP',
            action: 'membership.added',
            summary: `${owner?.name ?? 'The owner'} added ${user.name} to ${membership.shopName} as ${ROLE_LABEL[membership.role]}`,
            actor: owner ? { name: owner.name, email: owner.email, role: 'OWNER' } : null,
            shop: shopOf(membership.shopId),
            target: {
              type: 'MEMBERSHIP',
              id: `${membership.shopId}:${user.id}`,
              label: user.email,
            },
            metadata: { role: membership.role, member_email: user.email },
          }),
        )
      }
    }

    // Customers' accounts and every booking action.
    for (const b of bookings) {
      const customer = userByEmail.get(b.customerEmail.toLowerCase())
      const steps = bookingHistory(b)
      steps.forEach((step, index) => {
        if (index === 0 && customer && customer.createdAt === b.createdAt) {
          events.push(
            seedEvent({
              id: `seed:user.customer_created:${customer.id}`,
              occurredAt: step.at,
              category: 'USER',
              action: 'user.customer_created',
              summary: `${customer.name} created an account while booking`,
              actor: { name: customer.name, email: customer.email, role: 'CUSTOMER' },
              shop: null,
              target: { type: 'USER', id: customer.id, label: customer.email },
              metadata: {},
            }),
          )
        }
        const previous = index > 0 ? steps[index - 1]!.status : null
        const actorEmail =
          step.actorRole === 'CUSTOMER'
            ? b.customerEmail.toLowerCase()
            : ([...userByEmail.values()].find((u) => u.name === step.actorName)?.email ?? null)
        events.push(
          seedEvent({
            id: `seed:booking:${b.id}:${step.action}`,
            occurredAt: step.at,
            category: 'BOOKING',
            action: `booking.${step.action.replaceAll('-', '_')}`,
            summary: `${step.actorName} ${ACTION_VERB[step.action] ?? step.action.replaceAll('-', ' ')} ${b.reference}`,
            actor: { name: step.actorName, email: actorEmail, role: step.actorRole },
            shop: shopOf(b.shopId),
            target: { type: 'BOOKING', id: b.id, label: b.reference },
            metadata: { from_status: previous, to_status: step.status },
          }),
        )
      })
    }

    // Sign-ins, including failed attempts.
    for (const login of SEED_LOGINS) {
      const user = userByEmail.get(login.email)
      if (!user) continue
      events.push(
        seedEvent(
          {
            id: `seed:auth.login_succeeded:${user.id}:${login.at}`,
            occurredAt: login.at,
            category: 'AUTH',
            action: 'auth.login_succeeded',
            summary: `${user.name} signed in`,
            actor: { name: user.name, email: user.email, role: roleOf(user) },
            shop: null,
            target: { type: 'USER', id: user.id, label: user.email },
            metadata: {},
          },
          login.ua,
        ),
      )
    }
    for (const failed of SEED_FAILED_LOGINS) {
      events.push(
        seedEvent({
          id: `seed:auth.login_failed:${failed.email}:${failed.at}`,
          occurredAt: failed.at,
          category: 'AUTH',
          action: 'auth.login_failed',
          summary: `Failed sign-in for ${failed.email}`,
          actor: null,
          shop: null,
          target: null,
          metadata: { email: failed.email },
        }),
      )
    }

    return [...events, ...live].sort(
      (a, b) => b.occurredAt.localeCompare(a.occurredAt) || b.id.localeCompare(a.id),
    )
  },
)

/** The platform audit log, newest first (E-74's default order). */
export function getAuditEvents(): AuditEvent[] {
  return auditLog(getTeamMembers(), getBookings(), getShops(), getLiveAudit())
}

const ROLE_LABEL: Record<StaffRole, string> = {
  OWNER: 'Owner',
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
}

const ACTION_VERB: Record<string, string> = {
  create: 'booked',
  confirm: 'confirmed',
  'assign-technician': 'assigned a technician to',
  'start-inspection': 'started the inspection of',
  'submit-estimate': 'submitted the estimate for',
  'send-estimate': 'sent the estimate for',
  'approve-estimate': 'approved the estimate for',
  'reject-estimate': 'declined the estimate for',
  'assign-parts-person': 'assigned a parts person to',
  'order-parts': 'ordered parts for',
  'mark-parts-ready': 'marked the parts ready for',
  'allocate-parts': 'allocated the parts for',
  'send-to-qc': 'sent to QC',
  'pick-qc': 'picked for QC',
  'pass-qc': 'passed QC for',
  complete: 'completed',
  cancel: 'cancelled',
}

function roleOf(user: Pick<AdminUser, 'memberships'> & { seedAdmin?: boolean }): AuditActorRole {
  if (user.seedAdmin) return 'PLATFORM_ADMIN'
  return user.memberships.find((m) => m.isActive)?.role ?? 'CUSTOMER'
}

function appendAudit(
  event: Omit<AuditEvent, 'id' | 'occurredAt' | 'ip' | 'userAgent' | 'requestId'>,
) {
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  // Strictly increasing, so two actions in the same millisecond keep their order.
  const live = getLiveAudit()
  const last = live.length ? Date.parse(live[live.length - 1]!.occurredAt) : 0
  const entry: AuditEvent = {
    ...event,
    id: `live:${id}`,
    occurredAt: new Date(Math.max(Date.now(), last + 1)).toISOString(),
    ip: '203.0.113.10',
    userAgent: typeof navigator === 'undefined' ? null : navigator.userAgent.slice(0, 255),
    requestId: demoRequestId(id),
  }
  setStoredData(AUDIT_KEY, [...live, entry])
  return entry
}

const adminActor = (actor: AdminActor) =>
  ({ name: actor.name, email: actor.email, role: 'PLATFORM_ADMIN' }) as const

// --- Admin actions (E-64, E-65, E-68…E-71) ------------------------------------------------------

function requireReason(reason: string): string {
  const trimmed = reason.trim()
  if (trimmed.length < 5 || trimmed.length > 500) {
    throw new AdminActionError('VALIDATION_ERROR', 'Give a reason of 5 to 500 characters.')
  }
  return trimmed
}

export function suspendShop(shopId: string, reason: string, actor: AdminActor): void {
  const why = requireReason(reason)
  const target = getAdminShops().find((s) => s.shop.id === shopId)
  if (!target) throw new AdminActionError('VALIDATION_ERROR', 'Unknown shop.')
  if (target.suspension) throw new AdminActionError('CONFLICT', 'This shop is already suspended.')
  const suspension: ShopSuspension = {
    at: new Date().toISOString(),
    reason: why,
    byName: actor.name,
    byEmail: actor.email,
  }
  setStoredData(SUSPENSIONS_KEY, { ...getShopSuspensions(), [shopId]: suspension })
  appendAudit({
    category: 'SHOP',
    action: 'shop.suspended',
    summary: `${actor.name} suspended ${target.shop.name}`,
    actor: adminActor(actor),
    shop: { id: shopId, name: target.shop.name, slug: target.shop.slug },
    target: { type: 'SHOP', id: shopId, label: target.shop.name },
    metadata: { reason: why },
  })
}

export function reactivateShop(shopId: string, actor: AdminActor): void {
  const target = getAdminShops().find((s) => s.shop.id === shopId)
  if (!target) throw new AdminActionError('VALIDATION_ERROR', 'Unknown shop.')
  if (!target.suspension) throw new AdminActionError('CONFLICT', 'This shop is not suspended.')
  const remaining = { ...getShopSuspensions() }
  delete remaining[shopId]
  setStoredData(SUSPENSIONS_KEY, remaining)
  appendAudit({
    category: 'SHOP',
    action: 'shop.reactivated',
    summary: `${actor.name} reactivated ${target.shop.name}`,
    actor: adminActor(actor),
    shop: { id: shopId, name: target.shop.name, slug: target.shop.slug },
    target: { type: 'SHOP', id: shopId, label: target.shop.name },
    metadata: {},
  })
}

function findUser(userId: string): AdminUser {
  const user = getAdminUsers().find((u) => u.id === userId)
  if (!user) throw new AdminActionError('VALIDATION_ERROR', 'Unknown account.')
  return user
}

function activeAdmins(): AdminUser[] {
  return getAdminUsers().filter((u) => u.isPlatformAdmin && u.isActive)
}

const LAST_ADMIN = 'BayFlow needs at least one active platform admin.'

function setFlag(userId: string, patch: UserFlags[string]) {
  const flags = getUserFlags()
  setStoredData(USER_FLAGS_KEY, { ...flags, [userId]: { ...flags[userId], ...patch } })
}

/** Why the signed-in admin cannot change this account, or null when they can (spec 19 §1). */
export function accountActionBlock(
  user: AdminUser,
  action: 'deactivate' | 'revoke',
  actor: AdminActor,
): string | null {
  if (user.email === actor.email.toLowerCase()) {
    return action === 'deactivate'
      ? "You can't deactivate your own account."
      : "You can't remove your own admin access."
  }
  if (user.isPlatformAdmin && user.isActive && activeAdmins().length <= 1) return LAST_ADMIN
  return null
}

export function setUserActive(
  userId: string,
  active: boolean,
  reason: string | null,
  actor: AdminActor,
): void {
  const user = findUser(userId)
  if (user.isActive === active) {
    throw new AdminActionError(
      'CONFLICT',
      active ? 'This account is already active.' : 'This account is already deactivated.',
    )
  }
  let why: string | null = null
  if (!active) {
    const block = accountActionBlock(user, 'deactivate', actor)
    if (block) throw new AdminActionError(block === LAST_ADMIN ? 'CONFLICT' : 'FORBIDDEN', block)
    why = requireReason(reason ?? '')
  }
  setFlag(userId, { isActive: active })
  appendAudit({
    category: 'USER',
    action: active ? 'user.reactivated' : 'user.deactivated',
    summary: `${actor.name} ${active ? 'reactivated' : 'deactivated'} ${user.name}`,
    actor: adminActor(actor),
    shop: null,
    target: { type: 'USER', id: user.id, label: user.email },
    metadata: why ? { reason: why } : {},
  })
}

export function setPlatformAdmin(userId: string, grant: boolean, actor: AdminActor): void {
  const user = findUser(userId)
  if (user.isPlatformAdmin === grant) {
    throw new AdminActionError(
      'CONFLICT',
      grant ? 'This account is already a platform admin.' : 'This account is not a platform admin.',
    )
  }
  if (grant && !user.isActive) {
    throw new AdminActionError(
      'VALIDATION_ERROR',
      'Reactivate the account before granting admin access.',
    )
  }
  if (!grant) {
    const block = accountActionBlock(user, 'revoke', actor)
    if (block) throw new AdminActionError(block === LAST_ADMIN ? 'CONFLICT' : 'FORBIDDEN', block)
  }
  setFlag(userId, { isPlatformAdmin: grant })
  appendAudit({
    category: 'USER',
    action: grant ? 'user.platform_admin_granted' : 'user.platform_admin_revoked',
    summary: `${actor.name} ${grant ? 'granted platform admin access to' : 'removed platform admin access from'} ${user.name}`,
    actor: adminActor(actor),
    shop: null,
    target: { type: 'USER', id: user.id, label: user.email },
    metadata: {},
  })
}

// --- Reads that are audited (E-67, E-73, E-75) ---------------------------------------------------

const recentViews = new Map<string, number>()

/** `admin.user_viewed` / `admin.booking_viewed`, once per target per minute (React may re-run). */
export function recordAdminView(
  kind: 'user' | 'booking',
  target: { id: string; label: string; shop?: AuditEvent['shop'] },
  actor: AdminActor,
): void {
  const key = `${actor.email}:${kind}:${target.id}`
  const now = Date.now()
  if (now - (recentViews.get(key) ?? 0) < 60_000) return
  recentViews.set(key, now)
  appendAudit({
    category: 'ADMIN',
    action: `admin.${kind}_viewed`,
    summary: `${actor.name} viewed ${target.label}`,
    actor: adminActor(actor),
    shop: target.shop ?? null,
    target: { type: kind === 'user' ? 'USER' : 'BOOKING', id: target.id, label: target.label },
    metadata: {},
  })
}

export const AUDIT_EXPORT_LIMIT = 10_000

export function recordAuditExport(
  filters: Record<string, unknown>,
  rows: number,
  actor: AdminActor,
): void {
  appendAudit({
    category: 'ADMIN',
    action: 'admin.audit_exported',
    summary: `${actor.name} exported ${rows} audit ${rows === 1 ? 'event' : 'events'}`,
    actor: adminActor(actor),
    shop: null,
    target: null,
    metadata: { filters, rows },
  })
}

// --- Sign-in (mock login, D95 auth events) -------------------------------------------------------

/** Whether this e-mail may sign in: unknown e-mails may (the mock accepts new users). */
export function isAccountActive(email: string): boolean {
  const user = getAdminUsers().find((u) => u.email === email.trim().toLowerCase())
  return user ? user.isActive : true
}

export function isPlatformAdminEmail(email: string): boolean {
  const user = getAdminUsers().find((u) => u.email === email.trim().toLowerCase())
  return Boolean(user?.isPlatformAdmin && user.isActive)
}

export function recordSignIn(email: string, succeeded: boolean): void {
  const normalised = email.trim().toLowerCase()
  const user = getAdminUsers().find((u) => u.email === normalised)
  if (succeeded && user) {
    appendAudit({
      category: 'AUTH',
      action: 'auth.login_succeeded',
      summary: `${user.name} signed in`,
      actor: {
        name: user.name,
        email: user.email,
        role: user.isPlatformAdmin ? 'PLATFORM_ADMIN' : roleOf(user),
      },
      shop: null,
      target: { type: 'USER', id: user.id, label: user.email },
      metadata: {},
    })
    return
  }
  if (!succeeded) {
    appendAudit({
      category: 'AUTH',
      action: 'auth.login_failed',
      summary: `Failed sign-in for ${normalised}`,
      actor: null,
      shop: null,
      target: null,
      metadata: { email: normalised },
    })
  }
}

// --- CSV export (E-75) ---------------------------------------------------------------------------

const CSV_HEADER = [
  'occurred_at',
  'category',
  'action',
  'summary',
  'actor_name',
  'actor_email',
  'actor_role',
  'shop',
  'target_type',
  'target_label',
  'ip',
  'user_agent',
  'request_id',
  'metadata',
] as const

/** RFC 4180 cell, with spreadsheet formula prefixes neutralised (CSV injection). */
export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/** The audit log as CSV, newest first, at most `AUDIT_EXPORT_LIMIT` rows. */
export function auditCsv(events: ReadonlyArray<AuditEvent>): string {
  const rows = events
    .slice(0, AUDIT_EXPORT_LIMIT)
    .map((e) =>
      [
        e.occurredAt,
        e.category,
        e.action,
        e.summary,
        e.actor?.name ?? '',
        e.actor?.email ?? '',
        e.actor?.role ?? 'ANONYMOUS',
        e.shop?.name ?? '',
        e.target?.type ?? '',
        e.target?.label ?? '',
        e.ip ?? '',
        e.userAgent ?? '',
        e.requestId ?? '',
        JSON.stringify(e.metadata),
      ]
        .map(csvCell)
        .join(','),
    )
  return [CSV_HEADER.join(','), ...rows].join('\r\n') + '\r\n'
}
