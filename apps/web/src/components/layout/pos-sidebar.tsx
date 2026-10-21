'use client'

import {
  Boxes,
  CalendarCheck,
  ClipboardCheck,
  LayoutDashboard,
  PackageSearch,
  Settings,
  Tags,
  Truck,
  Users,
  Wrench,
  type LucideIcon,
  PhoneCall,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { useMockStore } from '@/hooks/use-mock-store'
import { getCurrentUser, getShopById, type CurrentUserSession } from '@/lib/mock-data'
import { CALLING_ENABLED } from '@/features/calls/config'
import { sectionAccess } from '@/lib/pos-access'

import { Logo } from './logo'

interface NavItem {
  segment: string
  label: string
  icon: LucideIcon
}

interface NavGroup {
  label: string
  items: NavItem[]
}

// Sections and icons per spec 10 §4 and spec 09 §3.9.
const ITEMS: Record<string, NavItem> = {
  overview: { segment: 'overview', label: 'Overview', icon: LayoutDashboard },
  bookings: { segment: 'bookings', label: 'Bookings', icon: CalendarCheck },
  calls: { segment: 'calls', label: 'AI calls & tasks', icon: PhoneCall },
  team: { segment: 'team', label: 'Team', icon: Users },
  services: { segment: 'services', label: 'Services', icon: Tags },
  settings: { segment: 'settings', label: 'Settings', icon: Settings },
  jobs: { segment: 'jobs', label: 'Jobs', icon: Wrench },
  parts: { segment: 'parts', label: 'Parts queue', icon: PackageSearch },
  inventory: { segment: 'inventory', label: 'Inventory', icon: Boxes },
  'purchase-orders': { segment: 'purchase-orders', label: 'Purchase orders', icon: Truck },
  qc: { segment: 'qc', label: 'QC queue', icon: ClipboardCheck },
}

const ORDER = [
  'overview',
  'bookings',
  // Only when in-app calling is configured (spec 05 §6.5: the panel needs the calls module).
  ...(CALLING_ENABLED ? ['calls'] : []),
  'jobs',
  'parts',
  'inventory',
  'purchase-orders',
  'qc',
  'team',
  'services',
  'settings',
]

/**
 * Items per role (spec 10 S-01 matrix): the Owner gets "Manage" plus read-only "Role views";
 * every other role sees its own queue only. Navigation scope only — the API enforces permissions.
 */
function navGroups(role: CurrentUserSession['role']): NavGroup[] {
  const visible = ORDER.filter((segment) => sectionAccess(role, segment))
  const pick = (segments: string[]) => segments.map((segment) => ITEMS[segment]!)
  if (role === 'OWNER') {
    return [
      { label: 'Manage', items: pick(visible.filter((s) => sectionAccess(role, s) === 'manage')) },
      {
        label: 'Role views (read-only)',
        items: pick(visible.filter((s) => sectionAccess(role, s) === 'read')),
      },
    ]
  }
  return [{ label: 'Your work', items: pick(visible) }]
}

export interface PosSidebarProps {
  shopId: string
  /** The person's role in this shop (their membership, D66); the session's role until known. */
  role?: CurrentUserSession['role']
}

export function PosSidebar({ shopId, role }: PosSidebarProps) {
  const pathname = usePathname()
  const user = useMockStore(getCurrentUser)
  const shop = useMockStore(() => getShopById(shopId))
  const groups = navGroups(role ?? user.role)
  const base = `/pos/shops/${encodeURIComponent(shopId)}`

  return (
    // App sidebar (DESIGN.md "App shell"): white, 256px, under the 64px sticky PosHeader; collapses
    // to a 64px icon rail on desktop (header toggle, ⌘B, or the rail) and is a sheet on phones.
    <Sidebar collapsible="icon" className="top-16 h-[calc(100svh-4rem)]!">
      <SidebarHeader className="border-b border-sidebar-border pt-4 pb-3 md:hidden">
        <Logo size="sm" />
        <p className="truncate text-sm font-semibold text-foreground">{shop?.name ?? 'Shop'}</p>
      </SidebarHeader>
      <SidebarContent className="py-2">
        <nav aria-label="Shop navigation">
          {groups.map((group) => (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((item) => {
                    const href = `${base}/${item.segment}`
                    const active = pathname === href || pathname.startsWith(`${href}/`)
                    return (
                      <SidebarMenuItem key={item.segment}>
                        <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
                          <Link href={href} aria-current={active ? 'page' : undefined}>
                            <item.icon aria-hidden="true" />
                            <span>{item.label}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    )
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}
