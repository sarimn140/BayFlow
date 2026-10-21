import type { Metadata, Viewport } from 'next'
import { Caveat, JetBrains_Mono, Plus_Jakarta_Sans, Sora } from 'next/font/google'

import { ScreenNavigator } from '@/components/dev/screen-navigator'
import { HelpAgent } from '@/components/help/help-agent'
import { SkipLink } from '@/components/layout/skip-link'
import { cn } from '@/lib/utils'

import './globals.css'
import { Providers } from './providers'

// Self-hosted by next/font: the browser never calls Google (spec 09 §3.6). The CSS variables are
// mapped to `font-heading` / `font-sans` / `font-handwriting` / `font-mono` in globals.css.
// Sora is the display face (headings, page titles, the landing hero): geometric and confident.
// Plus Jakarta Sans is the body face: friendly, crisp at small sizes. Both are variable fonts.
const sora = Sora({
  subsets: ['latin'],
  variable: '--font-display',
  display: 'swap',
})
const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
})
// The handwritten accent word (at most one per page, in a hero or greeting). Variable 400–700.
const caveat = Caveat({
  subsets: ['latin'],
  variable: '--font-script',
  display: 'swap',
})
const jetBrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    default: 'BayFlow · Multi-Tenant Auto Repair Shop Management Platform',
    template: '%s · BayFlow',
  },
  description:
    'BayFlow runs an auto repair shop on one shared workflow: online booking, inspection estimates customers approve from their phone, parts, repair and quality checks, with every role on the same live job.',
  applicationName: 'BayFlow',
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#e8ecf4' },
    { media: '(prefers-color-scheme: dark)', color: '#23262c' },
  ],
  colorScheme: 'light dark',
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    // next-themes sets `class="dark"` and `color-scheme` on <html> before React hydrates (D93).
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(sora.variable, plusJakartaSans.variable, caveat.variable, jetBrainsMono.variable)}
    >
      {/* Browser extensions (e.g. Grammarly's data-gr-ext-installed) add attributes to <body> before
          React hydrates; this accepts the DOM's attributes for this one element only. */}
      <body
        suppressHydrationWarning
        className="flex min-h-dvh flex-col bg-background text-foreground antialiased"
      >
        <SkipLink />
        <Providers>
          {children}
          {/* Site-only Help assistant: a floating button on every page */}
          <HelpAgent />
        </Providers>
        {/* Design review helper, never shipped to production */}
        {process.env.NODE_ENV !== 'production' && <ScreenNavigator />}
      </body>
    </html>
  )
}
