'use client'

import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import { Tabs as TabsPrimitive } from 'radix-ui'

function Tabs({
  className,
  orientation = 'horizontal',
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      data-orientation={orientation}
      className={cn('group/tabs flex gap-4 data-horizontal:flex-col', className)}
      {...props}
    />
  )
}

const tabsListVariants = cva(
  'group/tabs-list inline-flex w-fit max-w-full items-center overflow-x-auto text-muted-foreground group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col group-data-vertical/tabs:items-stretch',
  {
    variants: {
      variant: {
        // Segmented pill: views and filters inside a page (DESIGN.md "Tabs"). 48px, so each
        // trigger inside the 4px track is a 40px touch target.
        default: 'h-12 gap-1 rounded-full bg-secondary p-1 group-data-vertical/tabs:rounded-2xl',
        // Underline tabs (GarageBox): sections of a record page; blue indicator, semibold labels.
        line: 'h-12 gap-6 rounded-none border-b border-border-faint bg-transparent p-0 group-data-vertical/tabs:gap-1 group-data-vertical/tabs:border-r group-data-vertical/tabs:border-b-0',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

function TabsList({
  className,
  variant = 'default',
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List> & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "relative inline-flex h-full shrink-0 items-center justify-center gap-1.5 rounded-full px-4 text-sm font-medium whitespace-nowrap text-muted-foreground transition-[color,background-color,box-shadow] duration-150 outline-none group-data-vertical/tabs:min-h-10 group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid disabled:pointer-events-none disabled:opacity-50 data-active:bg-card data-active:text-foreground data-active:shadow-sm [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        // Underline variant
        'group-data-[variant=line]/tabs-list:rounded-none group-data-[variant=line]/tabs-list:px-0.5 group-data-[variant=line]/tabs-list:font-semibold group-data-[variant=line]/tabs-list:data-active:bg-transparent group-data-[variant=line]/tabs-list:data-active:text-brand-blue-ink group-data-[variant=line]/tabs-list:data-active:shadow-[inset_0_-2px_0_var(--brand-blue)] group-data-vertical/tabs:group-data-[variant=line]/tabs-list:data-active:shadow-[inset_-2px_0_0_var(--brand-blue)]',
        className,
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn(
        // Radix makes the panel a tab stop, so it needs a visible focus outline (WCAG 2.4.7).
        'flex-1 text-sm outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid',
        className,
      )}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
