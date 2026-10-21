import * as React from 'react'
import { cn } from 'cn'

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        // Landing-style field: 42px, rounded-lg (12px), full 1px border (≥ 3 : 1, spec 09 §5), white,
        // a hairline shadow; focus = brand-blue border plus a soft blue halo. 16px text on phones
        // so iOS does not zoom on focus.
        'h-10.5 w-full min-w-0 rounded-lg border border-input bg-card px-3.5 text-base text-foreground shadow-xs transition-[border-color,box-shadow,background-color] duration-150 ease-out outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-helper focus-visible:border-brand-blue focus-visible:ring-4 focus-visible:ring-brand-blue/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:opacity-70 disabled:shadow-none aria-invalid:border-destructive aria-invalid:ring-4 aria-invalid:ring-destructive/15 aria-invalid:focus-visible:border-destructive aria-invalid:focus-visible:ring-destructive/20 sm:text-sm',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
