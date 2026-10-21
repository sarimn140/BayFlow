'use client'

import { CalendarCheck, Globe, LayoutDashboard, LogOut, ShieldCheck } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'

import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { endMockSession } from '@/hooks/use-mock-session'
import { useMockStore } from '@/hooks/use-mock-store'
import { getAdminUsers } from '@/lib/mock-admin'
import { homePathFor } from '@/lib/mock-auth'
import { getCurrentUser } from '@/lib/mock-data'
import { signOutOfApi } from '@/features/calls/session'

export const ROLE_NAME = {
  OWNER: 'Owner',
  SERVICE_ADVISOR: 'Service Advisor',
  TECHNICIAN: 'Technician',
  PARTS_PERSON: 'Parts Person',
  QC_INSPECTOR: 'QC Inspector',
  CUSTOMER: 'Customer',
  PLATFORM_ADMIN: 'Platform admin',
} as const

export function initials(name: string) {
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/**
 * The signed-in user's avatar and account menu (spec 10 S-01 UserMenu), shared by the public
 * header, the POS bar and the admin console. `context` picks the links that make sense there.
 */
export function AccountMenu({ context = 'public' }: { context?: 'public' | 'pos' | 'admin' }) {
  const router = useRouter()
  const user = useMockStore(getCurrentUser)
  const users = useMockStore(getAdminUsers)
  const account = users.find((u) => u.email === user.email.toLowerCase())
  const isPlatformAdmin = Boolean(account?.isPlatformAdmin && account.isActive)
  const hasMemberships = Boolean(account?.memberships.some((m) => m.isActive))
  const isStaff = user.role !== 'CUSTOMER' && user.role !== 'PLATFORM_ADMIN'
  const roleName = context === 'admin' ? ROLE_NAME.PLATFORM_ADMIN : ROLE_NAME[user.role]

  const signOut = () => {
    void signOutOfApi()
    endMockSession()
    router.push('/login')
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex shrink-0 items-center rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <Avatar className="size-9 after:hidden">
            <AvatarFallback className="bg-brand-blue text-xs font-semibold text-brand-blue-foreground">
              {initials(user.name)}
            </AvatarFallback>
          </Avatar>
          {/* The name starts with the visible initials (WCAG 2.5.3 label in name). */}
          <span className="sr-only">Account: {user.name}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="flex items-center gap-3 py-2">
          <Avatar className="size-9 after:hidden">
            <AvatarFallback className="bg-brand-blue-subtle text-xs font-semibold text-brand-blue-ink">
              {initials(user.name)}
            </AvatarFallback>
          </Avatar>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-foreground">
              {user.name}
            </span>
            <span className="block truncate text-xs font-normal text-muted-foreground">
              {user.email}
            </span>
            <span className="block text-xs font-medium text-brand-blue-ink">{roleName}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {context !== 'admin' && (
          <DropdownMenuItem asChild>
            <Link href="/bookings">
              <CalendarCheck aria-hidden="true" />
              My bookings
            </Link>
          </DropdownMenuItem>
        )}
        {context === 'public' && isPlatformAdmin && (
          <DropdownMenuItem asChild>
            <Link href="/admin">
              <ShieldCheck aria-hidden="true" />
              Platform admin
            </Link>
          </DropdownMenuItem>
        )}
        {((context === 'public' && isStaff) || (context === 'admin' && hasMemberships)) && (
          <DropdownMenuItem asChild>
            <Link href={homePathFor(user)}>
              <LayoutDashboard aria-hidden="true" />
              Workshop POS
            </Link>
          </DropdownMenuItem>
        )}
        {context !== 'public' && (
          <DropdownMenuItem asChild>
            <Link href="/">
              <Globe aria-hidden="true" />
              Website
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
