import * as React from 'react'
import { cn } from 'cn'

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        'flex field-sizing-content min-h-24 w-full min-w-0 rounded-lg border border-input bg-card px-3.5 py-2.5 text-base leading-6 text-foreground shadow-xs transition-[border-color,box-shadow,background-color] duration-150 ease-out outline-none placeholder:text-helper focus-visible:border-brand-blue focus-visible:ring-4 focus-visible:ring-brand-blue/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:opacity-70 disabled:shadow-none aria-invalid:border-destructive aria-invalid:ring-4 aria-invalid:ring-destructive/15 aria-invalid:focus-visible:border-destructive aria-invalid:focus-visible:ring-destructive/20 sm:text-sm sm:leading-6',
        className,
      )}
      {...props}
    />
  )
}

export { Textarea }
