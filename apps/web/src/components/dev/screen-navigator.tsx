'use client'

import { Cancel01Icon, GridViewIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useId, useMemo, useState } from 'react'

import { cn } from '@/lib/utils'

/**
 * Development-only design navigator: a small floating icon (bottom right) that opens a panel to
 * jump straight to any screen, so the UI can be reviewed one page at a time. Dynamic routes use
 * IDs from `lib/mock-data.ts`. Rendered from the root layout only when NODE_ENV !== 'production'.
 */

/** Cookie the dev proxy honours to skip the login redirect (see `proxy.ts`). */
export const DESIGN_PREVIEW_COOKIE = 'bf_design_preview'

const SHOP = '/pos/shops/shop-lahore-auto-care'

const GROUPS: { name: string; screens: { label: string; href: string; note?: string }[] }[] = [
  {
    name: 'Public',
    screens: [
      { label: 'Landing page', href: '/' },
      { label: 'Find a shop', href: '/book' },
      { label: 'Shop profile', href: '/shops/lahore-auto-care' },
      { label: 'Booking wizard', href: '/book/lahore-auto-care' },
    ],
  },
  {
    name: 'Auth',
    screens: [
      { label: 'Login', href: '/login' },
      { label: 'Register', href: '/register' },
    ],
  },
  {
    name: 'Customer',
    screens: [
      { label: 'My bookings', href: '/bookings' },
      { label: 'Booking detail', href: '/bookings/bk-002', note: 'estimate awaiting approval' },
      { label: 'Booking detail', href: '/bookings/bk-001', note: 'in repair' },
      { label: 'Booking confirmed', href: '/book/confirmed/bk-004' },
    ],
  },
  {
    name: 'POS · Owner',
    screens: [
      { label: 'Workshop hub', href: '/pos', note: 'may redirect to role home' },
      { label: 'New shop', href: '/pos/shops/new' },
      { label: 'All shops summary', href: '/pos/summary' },
      { label: 'Shop home', href: SHOP },
      { label: 'Overview', href: `${SHOP}/overview` },
      { label: 'Services', href: `${SHOP}/services` },
      { label: 'Team', href: `${SHOP}/team` },
      { label: 'Settings', href: `${SHOP}/settings` },
    ],
  },
  {
    name: 'POS · Service advisor',
    screens: [
      { label: 'Bookings', href: `${SHOP}/bookings` },
      { label: 'Booking detail', href: `${SHOP}/bookings/bk-002` },
    ],
  },
  {
    name: 'POS · Technician',
    screens: [
      { label: 'Jobs', href: `${SHOP}/jobs` },
      { label: 'Job detail', href: `${SHOP}/jobs/bk-001` },
    ],
  },
  {
    name: 'POS · Parts',
    screens: [
      { label: 'Parts queue', href: `${SHOP}/parts` },
      { label: 'Parts request', href: `${SHOP}/parts/bk-001` },
      { label: 'Inventory', href: `${SHOP}/inventory` },
      { label: 'Purchase orders', href: `${SHOP}/purchase-orders` },
      { label: 'Purchase order', href: `${SHOP}/purchase-orders/po-1001` },
    ],
  },
  {
    name: 'Platform admin',
    screens: [
      { label: 'Overview', href: '/admin' },
      { label: 'Shops', href: '/admin/shops' },
      { label: 'Shop detail', href: '/admin/shops/shop-raza-auto-works' },
      { label: 'Users', href: '/admin/users' },
      { label: 'User detail', href: '/admin/users/usr-bilal' },
      { label: 'Bookings', href: '/admin/bookings' },
      { label: 'Booking detail', href: '/admin/bookings/bk-002' },
      { label: 'Audit log', href: '/admin/audit' },
    ],
  },
  {
    name: 'POS · QC',
    screens: [
      { label: 'QC queue', href: `${SHOP}/qc` },
      { label: 'QC inspection', href: `${SHOP}/qc/bk-003` },
    ],
  },
]

const ALL = GROUPS.flatMap((g) => g.screens.map((s) => ({ ...s, group: g.name })))

export function ScreenNavigator() {
  const pathname = usePathname()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const panelId = useId()

  // Let protected screens open without logging in (dev proxy checks this cookie).
  useEffect(() => {
    document.cookie = `${DESIGN_PREVIEW_COOKIE}=1; path=/; SameSite=Lax`
  }, [])

  const index = ALL.findIndex((s) => s.href === pathname)
  const current = index >= 0 ? ALL[index] : undefined

  const go = (step: number) => {
    const next = ALL[(Math.max(index, 0) + step + ALL.length) % ALL.length]
    if (next) router.push(next.href)
  }

  // Shortcuts: ` toggles the panel, [ and ] step through screens (ignored while typing), Escape
  // closes it from anywhere, including the search box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        return
      }
      const t = e.target as HTMLElement
      if (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) return
      if (e.key === '`') {
        e.preventDefault() // or the ` lands in the search box the panel has just focused
        setOpen((o) => !o)
      } else if (e.key === '[') go(-1)
      else if (e.key === ']') go(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return GROUPS
    return GROUPS.map((g) => ({
      ...g,
      screens: g.screens.filter((s) =>
        `${g.name} ${s.label} ${s.note ?? ''} ${s.href}`.toLowerCase().includes(q),
      ),
    })).filter((g) => g.screens.length)
  }, [query])

  return (
    // Bottom right, just left of the TanStack Query devtools button; Next's indicator is bottom left.
    <div className="fixed right-[78px] bottom-4 z-[60] flex flex-col items-end gap-2 font-sans">
      {open && (
        <div
          id={panelId}
          className="flex max-h-[min(70vh,560px)] w-80 flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl"
        >
          {/* Current screen, with previous / next */}
          <div className="flex items-center gap-1 border-b border-border-faint p-1.5">
            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Previous screen"
              className="flex size-8 shrink-0 items-center justify-center rounded-full text-helper hover:bg-secondary hover:text-foreground"
            >
              ←
            </button>
            <p className="min-w-0 flex-1 truncate text-center text-xs font-medium text-foreground">
              {current ? (
                <>
                  <span className="text-subtle-foreground">{current.group} /</span> {current.label}
                </>
              ) : (
                'Not a listed screen'
              )}
              <span className="ml-1.5 text-subtle-foreground tabular-nums">
                {index >= 0 ? index + 1 : '–'}/{ALL.length}
              </span>
            </p>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Next screen"
              className="flex size-8 shrink-0 items-center justify-center rounded-full text-helper hover:bg-secondary hover:text-foreground"
            >
              →
            </button>
          </div>
          <div className="border-b border-border-faint p-3">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search screens…"
              className="w-full rounded-lg bg-field px-3 py-2 text-sm outline-none placeholder:text-subtle-foreground focus:ring-2 focus:ring-foreground/10"
            />
          </div>
          <nav className="flex-1 overflow-y-auto p-2" aria-label="Design screens">
            {groups.map((g) => (
              <div key={g.name} className="mb-2">
                <p className="px-2 py-1.5 text-[10px] font-semibold tracking-wider text-subtle-foreground uppercase">
                  {g.name}
                </p>
                {g.screens.map((s) => {
                  const active = s.href === pathname
                  return (
                    <Link
                      key={s.href}
                      href={s.href}
                      onClick={() => setOpen(false)}
                      className={cn(
                        'flex items-baseline justify-between gap-3 rounded-lg px-2 py-1.5 text-sm transition',
                        active
                          ? 'bg-foreground text-background'
                          : 'text-muted-foreground hover:bg-secondary',
                      )}
                    >
                      <span>{s.label}</span>
                      {s.note && (
                        <span
                          className={cn(
                            'truncate text-[11px]',
                            active ? 'text-background/60' : 'text-subtle-foreground',
                          )}
                        >
                          {s.note}
                        </span>
                      )}
                    </Link>
                  )
                })}
              </div>
            ))}
            {!groups.length && (
              <p className="p-4 text-center text-sm text-subtle-foreground">No screens match.</p>
            )}
          </nav>
          <p className="border-t border-border-faint px-3 py-2 text-[11px] text-subtle-foreground">
            <kbd className="font-mono">`</kbd> toggle · <kbd className="font-mono">[</kbd>{' '}
            <kbd className="font-mono">]</kbd> prev / next screen
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={open ? 'Close screen navigator' : 'Open screen navigator'}
        title="Design screens ( ` )"
        className="flex size-10 items-center justify-center rounded-full bg-foreground text-background shadow-lg transition hover:bg-foreground/85 focus-visible:ring-2 focus-visible:ring-foreground/30 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <HugeiconsIcon icon={open ? Cancel01Icon : GridViewIcon} className="size-[18px]" />
      </button>
    </div>
  )
}
