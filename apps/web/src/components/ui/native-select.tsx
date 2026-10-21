import * as React from 'react'
import { cn } from 'cn'
import { ChevronDownIcon } from 'lucide-react'

type NativeSelectProps = Omit<React.ComponentProps<'select'>, 'size'> & {
  size?: 'sm' | 'default'
}

function NativeSelect({ className, size = 'default', ...props }: NativeSelectProps) {
  return (
    <div
      className={cn(
        'group/native-select relative w-fit has-[select:disabled]:opacity-60',
        className,
      )}
      data-slot="native-select-wrapper"
      data-size={size}
    >
      <select
        data-slot="native-select"
        data-size={size}
        className="h-10.5 w-full min-w-0 cursor-pointer appearance-none rounded-lg border border-input bg-card pr-10 pl-3.5 text-base text-foreground shadow-xs transition-[border-color,box-shadow,background-color] duration-150 ease-out outline-none select-none placeholder:text-helper focus-visible:border-brand-blue focus-visible:ring-4 focus-visible:ring-brand-blue/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none aria-invalid:border-destructive aria-invalid:ring-4 aria-invalid:ring-destructive/15 data-[size=sm]:h-9 data-[size=sm]:rounded-md sm:text-sm"
        {...props}
      />
      <ChevronDownIcon
        className="pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2 text-muted-foreground select-none"
        aria-hidden="true"
        data-slot="native-select-icon"
      />
    </div>
  )
}

function NativeSelectOption({ className, ...props }: React.ComponentProps<'option'>) {
  return (
    <option
      data-slot="native-select-option"
      className={cn('bg-[Canvas] text-[CanvasText]', className)}
      {...props}
    />
  )
}

function NativeSelectOptGroup({ className, ...props }: React.ComponentProps<'optgroup'>) {
  return (
    <optgroup
      data-slot="native-select-optgroup"
      className={cn('bg-[Canvas] text-[CanvasText]', className)}
      {...props}
    />
  )
}

export { NativeSelect, NativeSelectOptGroup, NativeSelectOption }
