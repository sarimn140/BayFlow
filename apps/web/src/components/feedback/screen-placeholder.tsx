import { Construction } from 'lucide-react'
import type { ReactNode } from 'react'

import { EmptyState } from '@/components/layout/empty-state'
import { PageHeader } from '@/components/layout/page-header'

export interface ScreenPlaceholderProps {
  /** Screen ID from spec 10 (e.g. `SA-01`). */
  screenId: string
  /** The page `<h1>`. */
  title: string
  /** What the screen is for (spec 10 "Purpose"). */
  description: string
  variant?: 'portal' | 'pos'
  actions?: ReactNode
  /** Route facts worth showing (e.g. the booking ID from the URL). Never fake data. */
  children?: ReactNode
}

/**
 * Route-skeleton placeholder: the right shell, a real `<h1>`, and an honest "not built yet"
 * state. Feature work replaces it with the screen defined in spec 10.
 */
export function ScreenPlaceholder({
  screenId,
  title,
  description,
  actions,
  children,
}: ScreenPlaceholderProps) {
  return (
    <div className="space-y-6">
      <PageHeader title={title} description={description} actions={actions} />
      {children}
      <div data-screen={screenId}>
        <EmptyState
          icon={Construction}
          tone="neutral"
          title="Coming soon"
          description={`This screen (${screenId}) is part of the next build phase.`}
        />
      </div>
    </div>
  )
}
