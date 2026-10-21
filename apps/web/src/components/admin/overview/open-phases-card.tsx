import { CheckCheck } from 'lucide-react'

import { EmptyState } from '@/components/layout/empty-state'
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'

import { CardHeading } from './card-heading'
import { plural, type PhaseCount } from './overview-data'
import { PhaseBreakdown } from './phase-breakdown'

/** A-01 "open bookings by phase" (spec 19 §5): where the platform's unfinished work sits. */
export function OpenPhasesCard({
  phases,
  open,
  className,
}: {
  phases: ReadonlyArray<PhaseCount>
  open: number
  className?: string
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardHeading>Open bookings by phase</CardHeading>
        <CardDescription>
          {open === 0
            ? 'Nothing is open right now.'
            : `${plural(open, 'open booking')} across all shops`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {open === 0 ? (
          <EmptyState
            variant="inline"
            tone="success"
            icon={CheckCheck}
            title="No open bookings"
            description="Every booking on BayFlow is completed or cancelled."
            className="p-6 sm:p-8"
          />
        ) : (
          <PhaseBreakdown phases={phases} total={open} />
        )}
      </CardContent>
    </Card>
  )
}
