import { ArrowRight } from 'lucide-react'
import Link from 'next/link'

import { AuditEventList } from '@/components/admin/audit-events'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardDescription, CardHeader } from '@/components/ui/card'
import type { AuditEvent } from '@/lib/mock-admin'
import { cn } from '@/lib/utils'

import { CardHeading } from './card-heading'

/** A-01 "latest audit events" (spec 19 §5): a row opens the event's detail sheet. */
export function RecentActivityCard({
  events,
  className,
}: {
  events: ReadonlyArray<AuditEvent>
  className?: string
}) {
  return (
    <Card className={cn('gap-0 py-0', className)}>
      <CardHeader className="border-b pt-(--card-spacing)">
        <CardHeading>Recent activity</CardHeading>
        <CardDescription>The newest audit events across BayFlow</CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/admin/audit">
              Audit log
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <AuditEventList events={events} empty="Nothing has been recorded yet." />
    </Card>
  )
}
