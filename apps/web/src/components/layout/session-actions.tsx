'use client'

import Link from 'next/link'

import { NotificationBell } from '@/components/notifications/notification-bell'
import { Button } from '@/components/ui/button'
import { useHasMockSession } from '@/hooks/use-mock-session'
import { cn } from '@/lib/utils'

import { AccountMenu } from './account-menu'

/**
 * Right side of the public header (spec 10 X-01, S-01 UserMenu): Sign In when signed out; the
 * notification bell and the account menu when signed in.
 */
export function SessionActions({ compact = false }: { compact?: boolean }) {
  const signedIn = useHasMockSession()

  if (!signedIn) {
    return (
      // The green Sign In button, on the AA-safe green (white on #047857 is 5.5 : 1).
      <Button
        asChild
        size={compact ? 'sm' : 'default'}
        className={cn(
          '[--btn-fill:var(--brand-green)] bg-brand-green font-semibold text-brand-green-foreground',
          compact ? 'h-9 px-4' : 'px-6',
        )}
      >
        <Link href="/login">Sign In</Link>
      </Button>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      <NotificationBell />
      <AccountMenu context="public" />
    </div>
  )
}
