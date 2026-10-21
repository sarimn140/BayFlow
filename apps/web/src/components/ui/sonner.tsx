'use client'

import { useTheme } from 'next-themes'
import { Toaster as Sonner, type ToasterProps } from 'sonner'
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from 'lucide-react'

// A 36px pill (Button `sm`) with a 44px hit area, the label at 14px, the blue focus ring.
const TOAST_BUTTON =
  'relative! h-9! rounded-full! border! px-4! text-sm! font-medium! transition-colors! duration-150! after:absolute after:-inset-1 focus-visible:shadow-none! focus-visible:outline-2! focus-visible:outline-offset-2! focus-visible:outline-ring! focus-visible:outline-solid!'

// Follows the light / dark theme (D93); the colours themselves come from the tokens below.
const Toaster = ({ ...props }: ToasterProps) => {
  const { forcedTheme, resolvedTheme } = useTheme()

  return (
    <Sonner
      theme={(forcedTheme ?? resolvedTheme) === 'dark' ? 'dark' : 'light'}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          '--normal-bg': 'var(--popover)',
          '--normal-text': 'var(--popover-foreground)',
          '--normal-border': 'var(--border)',
          '--border-radius': 'var(--radius-2xl)',
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: 'cn-toast',
          // The app's pill buttons (DESIGN.md "Buttons"): the action is the small primary, cancel
          // the small outline. Sonner injects its own button CSS outside Tailwind's layers, which
          // beats any layered utility, so these need `!`.
          actionButton: `${TOAST_BUTTON} border-transparent! bg-primary! text-primary-foreground! hover:bg-primary-hover!`,
          cancelButton: `${TOAST_BUTTON} border-border-medium! bg-card! text-foreground! hover:bg-secondary!`,
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
