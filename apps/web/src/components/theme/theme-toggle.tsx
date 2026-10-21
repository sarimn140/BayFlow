'use client'

import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

const THEMES = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
] as const

export interface ThemeToggleProps {
  /** `nav` sits on the app header and auth panel; `default` on page surfaces. */
  tone?: 'default' | 'nav'
  /** `sm` is the compact button used in the mobile header. */
  size?: 'icon' | 'sm'
  className?: string
}

/**
 * Light / Dark / System picker (D93). The sun and moon swap through the `dark:` variant, so the
 * trigger renders the same on the server and the client; the menu reads `theme` only once open.
 */
export function ThemeToggle({ tone = 'default', size = 'icon', className }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size={size === 'sm' ? 'icon-sm' : 'icon'}
          aria-label="Change colour theme"
          title="Theme"
          className={cn(
            'relative',
            tone === 'nav' ? 'bg-nav text-nav-foreground' : 'text-foreground',
            className,
          )}
        >
          <Sun className="size-[18px] scale-100 rotate-0 transition-transform duration-[240ms] ease-productive dark:scale-0 dark:-rotate-90" />
          <Moon className="absolute size-[18px] scale-0 rotate-90 transition-transform duration-[240ms] ease-productive dark:scale-100 dark:rotate-0" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          {THEMES.map(({ value, label, icon: Icon }) => (
            <DropdownMenuRadioItem key={value} value={value}>
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
