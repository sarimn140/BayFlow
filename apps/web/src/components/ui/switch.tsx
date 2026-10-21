'use client'

import * as React from 'react'
import { cn } from 'cn'
import { Switch as SwitchPrimitive } from 'radix-ui'

function Switch({
  className,
  size = 'default',
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
  size?: 'sm' | 'default'
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        // Unchecked track = --input (≥ 3 : 1 on white), checked = brand blue.
        'peer group/switch relative inline-flex shrink-0 items-center rounded-full border-2 border-transparent transition-colors duration-150 outline-none after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid aria-invalid:border-destructive aria-invalid:ring-4 aria-invalid:ring-destructive/15 data-[size=default]:h-6 data-[size=default]:w-11 data-[size=sm]:h-5 data-[size=sm]:w-9 data-checked:bg-primary data-unchecked:bg-input data-disabled:cursor-not-allowed data-disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block rounded-full bg-card shadow-sm ring-0 transition-transform duration-150 group-data-[size=default]/switch:size-5 group-data-[size=sm]/switch:size-4 dark:bg-foreground group-data-[size=default]/switch:data-checked:translate-x-5 group-data-[size=sm]/switch:data-checked:translate-x-4 group-data-[size=default]/switch:data-unchecked:translate-x-0 group-data-[size=sm]/switch:data-unchecked:translate-x-0"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
