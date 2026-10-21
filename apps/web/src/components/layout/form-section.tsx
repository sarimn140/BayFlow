import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export interface FormSectionProps {
  /** Section title (an `<h2>`), e.g. "Opening hours". */
  title: ReactNode
  /** What the section controls, one or two sentences. */
  description?: ReactNode
  /** The fields (`FieldGroup` of `Field`s). */
  children: ReactNode
  /** Save / cancel row at the bottom of the card. */
  footer?: ReactNode
  className?: string
}

/**
 * Settings / form section (DESIGN.md "Forms"): title and description on the left from `lg`, the
 * fields in a white card on the right, an optional footer row with the save pill.
 */
export function FormSection({ title, description, children, footer, className }: FormSectionProps) {
  return (
    <section
      className={cn('grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] lg:gap-8', className)}
    >
      <div className="space-y-1 lg:pt-2">
        <h2 className="text-lg leading-7 font-semibold text-foreground">{title}</h2>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      <div className="overflow-clip rounded-2xl border border-border bg-card shadow-xs">
        <div className="p-5 sm:p-6">{children}</div>
        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border-faint bg-muted px-5 py-3 sm:px-6">
            {footer}
          </div>
        ) : null}
      </div>
    </section>
  )
}
