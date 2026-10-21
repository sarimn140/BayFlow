import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'
import type { ReactNode } from 'react'

import { AuthShowcase } from '@/components/auth/auth-showcase'
import { Logo } from '@/components/layout/logo'
import { ThemeToggle } from '@/components/theme/theme-toggle'
import { Button } from '@/components/ui/button'

/**
 * `(auth)` shell (spec 09 §2.3, spec 10 P-04/P-05), in the landing page's light language: the
 * brand panel on the left from `lg` (its story follows the page), and the form column with a way
 * back to the site. Phones and tablets get one centred column under the logo. The column is 36rem
 * wide; a page that marks its root `data-auth-width="narrow"` (log-in) gets 30rem, so the top bar
 * always lines up with the card below it.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-1 flex-col bg-background lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,11fr)_minmax(0,12fr)]">
      <AuthShowcase />
      <main
        id="main"
        tabIndex={-1}
        className="relative isolate flex min-w-0 flex-1 flex-col px-4 outline-none sm:px-8 lg:px-10"
      >
        {/* Without the brand panel (below lg): the landing's grid paper and blue glow up top */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[30rem] overflow-hidden [mask-image:linear-gradient(to_bottom,black_30%,transparent)] lg:hidden"
        >
          <div className="bg-grid-pattern absolute inset-0" />
          <div className="absolute -top-56 left-1/2 aspect-square w-[44rem] -translate-x-1/2 rounded-full bg-brand-blue/8 blur-3xl" />
        </div>
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col has-data-[auth-width=narrow]:max-w-[30rem]">
          <div className="flex h-16 shrink-0 items-center">
            <Link
              href="/"
              aria-label="BayFlow home"
              className="flex min-h-10 items-center rounded-lg outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring focus-visible:outline-solid lg:hidden"
            >
              <Logo size="sm" />
            </Link>
            <Button asChild variant="ghost" className="-ml-4 hidden lg:inline-flex">
              <Link href="/">
                <ArrowLeft data-icon="inline-start" aria-hidden="true" />
                Back to website
              </Link>
            </Button>
            <ThemeToggle className="ml-auto" />
          </div>
          <div className="flex flex-1 flex-col pt-2 pb-12 sm:pt-6 lg:justify-center lg:pt-2 lg:pb-16">
            {children}
          </div>
        </div>
      </main>
    </div>
  )
}
