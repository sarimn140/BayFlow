import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import { Slot } from 'radix-ui'

// Soft-UI button (DESIGN.md "Buttons"): raised, lit from the top-left, and sunk in while pressed
// or toggled on (`neu-*` utilities in globals.css). Two shapes: `pill` (the default, a full pill
// or a circle at icon sizes) and `square` (rounded-xl, a rounded rectangle or square). Heights:
// sm 36 / default 42 / lg 48. Focus is a 2px ring 2px outside the button, so it shows on
// coloured fills too. The press nudge is `scale`, which makes the button the containing block of
// its own `::after` while pressed: a stretched link (`after:absolute after:inset-0` covering a
// card) must add `active:scale-none` (DESIGN.md §6.14), or a press on the card outside the
// button is lost.
const buttonVariants = cva(
  "group/button neu-press inline-flex shrink-0 items-center justify-center border border-transparent text-sm leading-5 font-semibold tracking-[0.01em] whitespace-nowrap transition-[background-color,border-color,color,box-shadow,transform,filter] duration-150 ease-out outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 disabled:shadow-none aria-invalid:outline-2 aria-invalid:outline-offset-2 aria-invalid:outline-destructive aria-invalid:outline-solid [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // The one primary action of a view: the accent colour, raised.
        default: 'neu-primary bg-primary text-primary-foreground hover:brightness-110',
        // Attention: the orange ink, kept for the rare "act now" conversion (spec 09 §3.1, R7).
        cta: 'neu-cta bg-cta text-cta-foreground hover:brightness-110',
        // Secondary action: a raised neutral button.
        outline: 'neu-raised border-border/60 bg-card text-foreground hover:brightness-105',
        // A destructive action that is not the decision itself (spec 09 §4.6 rule 3: "Cancel
        // booking", "Suspend shop"; the AlertDialog's confirm is the solid `destructive`).
        'destructive-outline':
          'neu-raised border-border/60 bg-card text-danger-ink hover:brightness-105',
        // Quiet raised action on cards.
        secondary: 'neu-raised bg-secondary text-secondary-foreground hover:brightness-105',
        // Toolbar and inline actions: flat until hovered, then raised.
        ghost:
          'bg-transparent text-foreground shadow-none hover:neu-raised hover:bg-card aria-expanded:bg-card',
        // Solid danger (white label stays AA on both themes).
        destructive:
          'neu-danger bg-destructive-strong text-destructive-foreground hover:brightness-110 focus-visible:outline-destructive',
        // `scale-none`, not `scale-100`: any scale value makes a containing block (see above).
        link: 'h-auto! rounded-sm! bg-none! px-0! text-brand-blue-ink underline-offset-4 shadow-none! hover:underline active:scale-none',
      },
      size: {
        default:
          'h-10.5 gap-2 px-5 has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4',
        xs: "h-7 gap-1 px-3 text-xs [&_svg:not([class*='size-'])]:size-3.5",
        sm: 'h-9 gap-1.5 px-4 has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3',
        lg: 'h-12 gap-2 px-6 text-base has-data-[icon=inline-end]:pr-5 has-data-[icon=inline-start]:pl-5',
        icon: 'size-10',
        'icon-xs': "size-6 [&_svg:not([class*='size-'])]:size-3",
        'icon-sm': 'size-8',
        'icon-lg': 'size-12',
      },
      // pill = fully round (a circle at icon sizes); square = rounded rectangle.
      shape: {
        pill: 'rounded-full',
        square: 'rounded-xl',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
      shape: 'pill',
    },
  },
)

function Button({
  className,
  variant = 'default',
  size = 'default',
  shape = 'pill',
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : 'button'

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      data-shape={shape}
      className={cn(buttonVariants({ variant, size, shape, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
