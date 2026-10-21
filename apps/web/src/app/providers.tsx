'use client'

import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { ThemeProvider } from 'next-themes'
import type { ReactNode } from 'react'

import { OfflineBanner } from '@/components/feedback/offline-banner'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useIsMobile } from '@/hooks/use-mobile'
import { getQueryClient } from '@/lib/api/query-client'

export interface ProvidersProps {
  children: ReactNode
}

/** Client-side providers mounted once in the root layout (spec 09 §2.7). */
export function Providers({ children }: ProvidersProps) {
  // Not useState: there is no Suspense boundary above this component (TanStack's App Router guide).
  const queryClient = getQueryClient()
  const isMobile = useIsMobile()

  return (
    // Light / Dark switch (ThemeToggle in every header). Follows the device until the visitor
    // picks one; the choice is remembered. `theme-fade` softens the colour change.
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <OfflineBanner />
          {children}
          {/* Toasts: bottom-right on desktop, top-centre below md, at most 3 (spec 09 §4.9). */}
          <Toaster position={isMobile ? 'top-center' : 'bottom-right'} visibleToasts={3} />
        </TooltipProvider>
        {/* Rendered only when NODE_ENV === 'development'; a no-op in production builds. */}
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </ThemeProvider>
  )
}
