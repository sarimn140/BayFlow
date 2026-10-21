'use client'

import {
  CalendarCheck,
  Globe,
  LayoutDashboard,
  ScrollText,
  ShieldCheck,
  Store,
  Users,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

import { ForbiddenState } from '@/components/feedback/forbidden-state'
import { AccountMenu } from '@/components/layout/account-menu'
import { ThemeToggle } from '@/components/theme/theme-toggle'
import { Logo } from '@/components/layout/logo'
import { Button } from '@/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { Skeleton } from '@/components/ui/skeleton'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { getAdminUsers } from '@/lib/mock-admin'
import { homePathFor } from '@/lib/mock-auth'
import { getCurrentUser } from '@/lib/mock-data'

const NAV: ReadonlyArray<{ href: string; label: string; icon: LucideIcon; exact?: boolean }> = [
  { href: '/admin', label: 'Overview', icon: LayoutDashboard, exact: true },
  { href: '/admin/shops', label: 'Shops', icon: Store },
  { href: '/admin/users', label: 'Users', icon: Users },
  { href: '/admin/bookings', label: 'Bookings', icon: CalendarCheck },
  { href: '/admin/audit', label: 'Audit log', icon: ScrollText },
]

/** The signed-in platform admin, or `null` while loading or when the user is not one (D94). */
export function useAdminActor() {
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const users = useMockStore(getAdminUsers)
  const account = users.find((u) => u.email === user.email.toLowerCase())
  const isAdmin = Boolean(account?.isPlatformAdmin && account.isActive)
  return { ready, user, account, isAdmin }
}

/**
 * Platform admin console shell (spec 19 §5): the light app bar, the admin side nav (collapsible
 * to icons, a sheet on phones) and the gate. The pages render only for an active platform admin,
 * after this browser's stored data is in use, so nothing time- or session-dependent is rendered
 * on the server.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { ready, user, isAdmin } = useAdminActor()

  return (
    <SidebarProvider className="min-h-dvh flex-col bg-canvas">
      {/* The light app bar (DESIGN.md "App shell"), with a dark "Platform admin" pill */}
      <header className="sticky top-0 z-40 h-16 shrink-0 border-b border-border-faint bg-card/90 backdrop-blur-md">
        <div className="flex h-full items-center gap-1.5 px-3 sm:gap-3 sm:px-4 lg:px-6">
          <SidebarTrigger
            aria-label="Toggle admin navigation"
            className="size-10 shrink-0 rounded-full text-muted-foreground hover:text-foreground"
          />
          <Link
            href="/admin"
            // Starts with the visible "BayFlow" and "Platform admin" (WCAG 2.5.3).
            aria-label="BayFlow Platform admin home"
            className="flex min-w-0 items-center gap-2.5 rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
          >
            <Logo size="sm" showText={false} className="sm:hidden" />
            <Logo size="sm" className="hidden sm:inline-flex" />
            {/* A real space, so the visible text reads "BayFlow Platform admin". */}{' '}
            <span className="inline-flex h-7 items-center gap-1.5 rounded-full bg-foreground px-3 text-xs font-semibold whitespace-nowrap text-background">
              <ShieldCheck className="size-3.5" aria-hidden="true" />
              Platform admin
            </span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden md:inline-flex">
              <Link href="/">
                <Globe aria-hidden="true" />
                Website
              </Link>
            </Button>
            <ThemeToggle tone="nav" />
            {ready && <AccountMenu context="admin" />}
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        <Sidebar collapsible="icon" className="top-16 h-[calc(100svh-4rem)]!">
          <SidebarContent className="py-2">
            <nav aria-label="Platform admin navigation">
              <SidebarGroup>
                <SidebarGroupLabel>Platform</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {NAV.map(({ href, label, icon: Icon, exact }) => {
                      const active = exact
                        ? pathname === href
                        : pathname === href || pathname.startsWith(`${href}/`)
                      return (
                        <SidebarMenuItem key={href}>
                          <SidebarMenuButton asChild isActive={active} tooltip={label}>
                            <Link href={href} aria-current={active ? 'page' : undefined}>
                              <Icon aria-hidden="true" />
                              <span>{label}</span>
                            </Link>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      )
                    })}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </nav>
          </SidebarContent>
          <SidebarRail />
        </Sidebar>

        <SidebarInset
          id="main"
          tabIndex={-1}
          className="min-w-0 overflow-x-clip bg-canvas outline-none"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            {!ready ? (
              <ConsoleSkeleton />
            ) : isAdmin ? (
              children
            ) : (
              <ForbiddenState
                message="This area is for BayFlow platform admins."
                homeHref={homePathFor(user)}
              />
            )}
          </div>
        </SidebarInset>
      </div>
    </SidebarProvider>
  )
}

function ConsoleSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <div className="space-y-3 pb-2">
        <Skeleton className="h-4 w-28 rounded-full" />
        <Skeleton className="h-10 w-72" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-2xl" />
    </div>
  )
}
