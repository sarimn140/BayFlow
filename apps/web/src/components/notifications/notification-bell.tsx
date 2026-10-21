'use client'

import {
  Bell,
  BellOff,
  CalendarCheck,
  CalendarPlus,
  CarFront,
  CheckCheck,
  ClipboardCheck,
  ClipboardList,
  ClipboardX,
  FileCheck,
  FileText,
  FileX,
  PackageCheck,
  PackageSearch,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useIsMobile } from '@/hooks/use-mobile'
import { useNowMinute } from '@/hooks/use-now'
import { useMockStore, useMockStoreReady } from '@/hooks/use-mock-store'
import { formatRelative } from '@/lib/format'
import { getBookings, getCurrentUser, getTeamMembers } from '@/lib/mock-data'
import {
  deriveNotifications,
  getReadNotificationIds,
  markNotificationsRead,
  type MockNotification,
  type NotificationType,
} from '@/lib/mock-notifications'
import { safeNextPath } from '@/lib/safe-next'
import { cn } from '@/lib/utils'

/** Type icon, tinted with the booking phase it belongs to (spec 09 §3.3). */
const TYPE_STYLE: Record<NotificationType, { icon: LucideIcon; tone: string }> = {
  BOOKING_CREATED: { icon: CalendarPlus, tone: 'bg-status-intake-bg text-status-intake-fg' },
  BOOKING_CONFIRMED: { icon: CalendarCheck, tone: 'bg-status-intake-bg text-status-intake-fg' },
  TECHNICIAN_ASSIGNED: {
    icon: Wrench,
    tone: 'bg-status-inspection-bg text-status-inspection-fg',
  },
  ESTIMATE_SUBMITTED: { icon: FileText, tone: 'bg-status-estimate-bg text-status-estimate-fg' },
  ESTIMATE_SENT: { icon: FileText, tone: 'bg-status-estimate-bg text-status-estimate-fg' },
  ESTIMATE_APPROVED: { icon: FileCheck, tone: 'bg-status-handover-bg text-status-handover-fg' },
  ESTIMATE_REJECTED: {
    icon: FileX,
    tone: 'bg-status-estimate-rejected-bg text-status-estimate-rejected-fg',
  },
  PARTS_NEEDED: { icon: PackageSearch, tone: 'bg-status-parts-bg text-status-parts-fg' },
  PARTS_READY: { icon: PackageCheck, tone: 'bg-status-parts-bg text-status-parts-fg' },
  QC_REQUESTED: { icon: ClipboardList, tone: 'bg-status-repair-qc-bg text-status-repair-qc-fg' },
  QC_FAILED: {
    icon: ClipboardX,
    tone: 'bg-status-estimate-rejected-bg text-status-estimate-rejected-fg',
  },
  QC_PASSED: { icon: ClipboardCheck, tone: 'bg-status-handover-bg text-status-handover-fg' },
  VEHICLE_READY: { icon: CarFront, tone: 'bg-status-handover-bg text-status-handover-fg' },
}

export interface NotificationBellProps {
  /** Kept for older call sites: the app bars are light now, so both tones look the same. */
  tone?: 'default' | 'nav'
  className?: string
}

/** X-01 notifications (spec 10, spec 09 §4.10): popover on desktop, side sheet on mobile. */
export function NotificationBell({ className }: NotificationBellProps) {
  const isMobile = useIsMobile()
  const ready = useMockStoreReady()
  const user = useMockStore(getCurrentUser)
  const bookings = useMockStore(getBookings)
  const team = useMockStore(getTeamMembers)
  const readIds = useMockStore(getReadNotificationIds)
  const [open, setOpen] = useState(false)

  const items = useMemo(() => deriveNotifications(user, bookings, team), [user, bookings, team])
  const read = useMemo(() => new Set(readIds), [readIds])
  // Until this browser's stored data is in use, the bell shows no count (it matches the server).
  const unread = ready ? items.filter((n) => !read.has(n.id)).length : 0

  const trigger = (
    <Button
      variant="ghost"
      size="icon"
      aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
      className={cn(
        'relative text-muted-foreground hover:text-foreground aria-expanded:text-foreground',
        className,
      )}
    >
      <Bell className="size-5" aria-hidden="true" />
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute -top-0.5 -right-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-cta px-1 text-xs leading-none font-semibold text-cta-foreground ring-2 ring-card"
        >
          {unread > 9 ? '9+' : unread}
        </span>
      )}
    </Button>
  )

  const panel = (
    <NotificationPanel
      items={items}
      read={read}
      onOpenItem={() => setOpen(false)}
      fill={isMobile}
    />
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>{trigger}</SheetTrigger>
        {/* Full width on phones, 448px from `sm` (the primitive's own widths). */}
        <SheetContent side="right" className="gap-0 p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Notifications</SheetTitle>
            <SheetDescription>Your latest booking updates</SheetDescription>
          </SheetHeader>
          {panel}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="w-[380px] gap-0 p-0">
        {panel}
      </PopoverContent>
    </Popover>
  )
}

function NotificationPanel({
  items,
  read,
  onOpenItem,
  fill = false,
}: {
  items: ReadonlyArray<MockNotification>
  read: ReadonlySet<string>
  onOpenItem: () => void
  /** Fill the container's height (the mobile sheet) instead of capping the list. */
  fill?: boolean
}) {
  const router = useRouter()
  const now = useNowMinute()
  const unreadIds = items.filter((n) => !read.has(n.id)).map((n) => n.id)

  const open = (n: MockNotification) => {
    markNotificationsRead([n.id])
    onOpenItem()
    // D67: follow the server's link only when it is a path on this site.
    const link = safeNextPath(n.link)
    if (link) router.push(link)
  }

  return (
    <div className={cn('flex min-h-0 flex-col', fill && 'h-full')}>
      <div
        className={cn(
          'flex items-center justify-between gap-3 border-b border-border-faint px-4 py-3',
          // In the sheet, the sheet's own ✕ sits in the top-right corner (top-4 right-4, 32px):
          // keep "Mark all as read" clear of it.
          fill && 'min-h-16 pr-14',
        )}
      >
        <h2 className="text-base font-semibold text-foreground">Notifications</h2>
        <Button
          variant="ghost"
          size="sm"
          disabled={unreadIds.length === 0}
          onClick={() => markNotificationsRead(unreadIds)}
          className={cn(
            'text-brand-blue-ink hover:text-brand-blue-ink',
            // A finger taps it in the sheet: a 44px hit area around the 36px pill (DESIGN.md §2.6).
            fill ? 'relative after:absolute after:-inset-1' : '-mr-2',
          )}
        >
          <CheckCheck aria-hidden="true" />
          Mark all as read
        </Button>
      </div>

      {items.length === 0 ? (
        <Empty className="py-12">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BellOff aria-hidden="true" />
            </EmptyMedia>
            <EmptyTitle>You&apos;re all caught up</EmptyTitle>
            <EmptyDescription>New hand-offs on your bookings appear here.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ScrollArea
          className={cn(
            // Radix sizes the viewport, so the height cap goes on it (the root has no overflow).
            'min-h-0 flex-1 overflow-hidden',
            fill
              ? '[&>[data-slot=scroll-area-viewport]]:h-full'
              : '[&>[data-slot=scroll-area-viewport]]:max-h-[min(70vh,460px)]',
          )}
        >
          <ul>
            {items.map((n) => {
              const unread = !read.has(n.id)
              const { icon: Icon, tone } = TYPE_STYLE[n.type]
              return (
                <li key={n.id} className="border-b border-border-faint last:border-0">
                  <button
                    type="button"
                    onClick={() => open(n)}
                    className={cn(
                      'flex w-full gap-3 px-4 py-3 text-left transition-colors duration-100 hover:bg-secondary focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid',
                      unread && 'bg-brand-blue-subtle/50 hover:bg-brand-blue-subtle',
                    )}
                  >
                    <span
                      className={cn(
                        'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full',
                        tone,
                      )}
                    >
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <span
                          className={cn(
                            'text-sm text-foreground',
                            unread ? 'font-semibold' : 'font-normal',
                          )}
                        >
                          {n.title}
                        </span>
                        {unread && (
                          <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand-blue">
                            <span className="sr-only">Unread</span>
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 line-clamp-2 block text-sm leading-snug text-muted-foreground">
                        {n.body}
                      </span>
                      <span className="mt-1 block text-xs text-helper">
                        {n.reference} · {n.shopName}
                        {now ? ` · ${formatRelative(n.createdAt, new Date(now))}` : ''}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </ScrollArea>
      )}
    </div>
  )
}
