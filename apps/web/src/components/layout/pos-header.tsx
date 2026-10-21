'use client'

import { Check, ChevronDown, LayoutGrid, Plus, ShieldCheck, Store } from 'lucide-react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'

import { NotificationBell } from '@/components/notifications/notification-bell'
import { workspaceHref, workspacesOf, type Workspace } from '@/components/pos/hub/hub-data'
import { ThemeToggle } from '@/components/theme/theme-toggle'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { useMockStore } from '@/hooks/use-mock-store'
import { getCurrentUser, getShops, getTeamMembers, setCurrentUser } from '@/lib/mock-data'

import { AccountMenu, ROLE_NAME } from './account-menu'
import { Logo } from './logo'

/** The shop of a shop page (`/pos/shops/{id}/…`), not `/pos/shops/new`; null elsewhere. */
function shopIdOf(pathname: string): string | null {
  const [, pos, shops, shopId] = pathname.split('/')
  return pos === 'pos' && shops === 'shops' && shopId && shopId !== 'new' ? shopId : null
}

const PILL =
  'inline-flex h-9 min-w-0 items-center gap-2 rounded-full border text-sm font-medium transition-colors duration-150 outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring [&_svg]:shrink-0'

/**
 * POS app bar (spec 09 §4.1, spec 10 S-01; DESIGN.md "App shell"): a light, translucent 64px bar
 * like the landing header. Left: sidebar toggle (shop pages), logo, shop switcher pill. Right: the
 * person's role in the current shop, notifications, account menu.
 *
 * Everything comes from the person's own active memberships (`/me`, D66): the switcher lists
 * only their shops, switching takes their role there, and a shop they don't belong to is never
 * named. There is no role or account switching here (D52: no "log in as"); demo accounts are on
 * the login page.
 */
export function PosHeader() {
  const router = useRouter()
  const pathname = usePathname()
  const user = useMockStore(() => getCurrentUser())
  const shops = useMockStore(() => getShops())
  const team = useMockStore(() => getTeamMembers())
  const workspaces = workspacesOf(user.email, team, shops)
  // O-07 is for owners of two or more shops (spec 10 S-01 "All shops summary").
  const ownedShops = workspaces.filter((workspace) => workspace.role === 'OWNER').length

  // On a shop page, the shop in the address; elsewhere, the last one opened.
  const pageShopId = shopIdOf(pathname)
  const current = workspaces.find((w) => w.shop.id === (pageShopId ?? user.shopId))
  const pillLabel = current?.shop.name ?? (workspaces.length > 0 ? 'Choose a shop' : 'No shop yet')

  // Their role there (D66: one role per membership), and that role's home (spec 10 S-04).
  const handleSwitchShop = ({ shop, role }: Workspace) => {
    setCurrentUser({
      ...user,
      role,
      shopId: shop.id,
      shopName: shop.name,
    })
    router.push(workspaceHref({ shop, role }))
  }

  return (
    <header className="sticky top-0 z-40 h-16 shrink-0 border-b border-border-faint bg-card/90 backdrop-blur-md">
      <div className="flex h-full items-center gap-1.5 px-3 sm:gap-3 sm:px-4 lg:px-6">
        {/* Only a member's shop page has the sidebar (the 404 view has none). */}
        {pageShopId && current ? (
          <SidebarTrigger
            aria-label="Toggle shop navigation"
            className="size-10 shrink-0 rounded-full text-muted-foreground hover:text-foreground"
          />
        ) : null}

        <Link
          href="/pos"
          // The name starts with the visible "BayFlow" (and "POS" from lg), WCAG 2.5.3.
          aria-label="BayFlow POS home"
          className="flex shrink-0 items-center gap-2 rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid"
        >
          <Logo size="sm" showText={false} className="sm:hidden" />
          <Logo size="sm" className="hidden sm:inline-flex" />
          {/* A real space, so the visible text reads "BayFlow POS", not "BayFlowPOS". */}{' '}
          <span className="hidden rounded-md bg-secondary px-1.5 py-0.5 text-xs font-semibold text-muted-foreground lg:inline">
            POS
          </span>
        </Link>

        <span aria-hidden="true" className="mx-1 hidden h-6 w-px bg-border sm:block" />

        {/* Shop switcher: All shops first, the person's shops, Create shop last (spec 10 S-01) */}
        <DropdownMenu>
          <DropdownMenuTrigger
            className={`${PILL} border-border-medium bg-card py-1 pr-2.5 pl-3 text-foreground shadow-xs hover:bg-secondary aria-expanded:bg-secondary sm:pl-1`}
          >
            <span className="hidden size-7 items-center justify-center rounded-full bg-brand-blue text-brand-blue-foreground sm:flex">
              <Store className="size-3.5" aria-hidden="true" />
            </span>
            {/* The visible text leads the button's name (WCAG 2.5.3); the purpose follows. */}
            <span className="max-w-[6.5rem] truncate min-[400px]:max-w-[8rem] sm:max-w-[16rem]">
              {pillLabel}
            </span>
            <span className="sr-only">, shop menu</span>
            <ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-72">
            {ownedShops >= 2 ? (
              <>
                <DropdownMenuItem asChild>
                  <Link href="/pos/summary">
                    <LayoutGrid aria-hidden="true" />
                    All shops summary
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            ) : null}
            {workspaces.length > 0 ? (
              <>
                <DropdownMenuLabel>Switch shop</DropdownMenuLabel>
                <DropdownMenuGroup>
                  {workspaces.map((workspace) => (
                    <DropdownMenuItem
                      key={workspace.shop.id}
                      onSelect={() => handleSwitchShop(workspace)}
                    >
                      <Store aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate">{workspace.shop.name}</span>
                      {workspace.shop.id === current?.shop.id ? (
                        <Check className="text-brand-blue-ink" aria-label="Current shop" />
                      ) : null}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
              </>
            ) : (
              <>
                <DropdownMenuItem asChild>
                  <Link href="/pos">
                    <LayoutGrid aria-hidden="true" />
                    Workshop hub
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem asChild>
              <Link href="/pos/shops/new">
                <Plus aria-hidden="true" />
                Create new shop
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          {/* The person's role in this shop: their membership, not a switch. */}
          {current ? (
            <span
              className={`${PILL} w-9 shrink-0 justify-center border-brand-blue/20 bg-brand-blue-subtle text-brand-blue-ink sm:w-auto sm:px-3`}
            >
              <ShieldCheck className="size-4" aria-hidden="true" />
              <span className="sr-only">Your role: </span>
              <span className="sr-only sm:not-sr-only">{ROLE_NAME[current.role]}</span>
            </span>
          ) : null}

          <ThemeToggle tone="nav" />
          <NotificationBell />
          <AccountMenu context="pos" />
        </div>
      </div>
    </header>
  )
}
