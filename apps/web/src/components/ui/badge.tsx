import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import { Slot } from 'radix-ui'

const badgeVariants = cva(
  // Pill chip (DESIGN.md "Chips"): 24px, 12px medium label, soft fill + hairline border + ink.
  'group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-2.5 text-xs leading-none font-medium whitespace-nowrap transition-[color,background-color,box-shadow] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 aria-invalid:border-destructive [&>svg]:pointer-events-none [&>svg]:size-3.5',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground [a]:hover:bg-primary-hover',
        secondary: 'bg-secondary text-secondary-foreground [a]:hover:bg-layer-selected',
        destructive:
          'border-status-estimate-rejected-border bg-danger-subtle text-danger-ink [a]:hover:bg-danger-subtle/70',
        outline: 'border-border bg-card text-foreground [a]:hover:bg-secondary',
        ghost: 'text-muted-foreground hover:bg-secondary hover:text-foreground',
        link: 'text-brand-blue-ink underline-offset-4 hover:underline',
        // Soft semantic chips (same recipe as the status chips)
        success: 'border-status-handover-border bg-success-subtle text-success-ink',
        warning: 'border-status-estimate-border bg-warning-subtle text-warning-ink',
        info: 'border-status-intake-border bg-info-subtle text-info-ink',
        neutral: 'border-status-closed-border bg-status-closed-bg text-status-closed-fg',
        brand: 'border-brand-blue/20 bg-brand-blue-subtle text-brand-blue-ink',
        // BayFlow: booking status phases (spec 09 §3.3) — soft fill, 1 px border, dark ink.
        intake: 'border-status-intake-border bg-status-intake-bg text-status-intake-fg',
        inspection:
          'border-status-inspection-border bg-status-inspection-bg text-status-inspection-fg',
        estimate: 'border-status-estimate-border bg-status-estimate-bg text-status-estimate-fg',
        'estimate-rejected':
          'border-status-estimate-rejected-border bg-status-estimate-rejected-bg text-status-estimate-rejected-fg',
        parts: 'border-status-parts-border bg-status-parts-bg text-status-parts-fg',
        'repair-qc':
          'border-status-repair-qc-border bg-status-repair-qc-bg text-status-repair-qc-fg',
        handover: 'border-status-handover-border bg-status-handover-bg text-status-handover-fg',
        closed: 'border-status-closed-border bg-status-closed-bg text-status-closed-fg',
        // "Action needed" chip (spec 09 §3.4): attention surface, cta ink.
        attention: 'border-attention-border bg-attention text-cta',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

function Badge({
  className,
  variant = 'default',
  asChild = false,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : 'span'

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
