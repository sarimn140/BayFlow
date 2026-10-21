'use client'

import {
  BarChart3,
  Bell,
  Box,
  Calendar,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Menu,
  PhoneCall,
  PlusCircle,
  ShoppingBag,
  Warehouse,
  X,
} from 'lucide-react'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'

import { ThemeToggle } from '@/components/theme/theme-toggle'
import { Button } from '@/components/ui/button'

import { Logo } from './logo'
import { SessionActions } from './session-actions'

export function PublicHeader() {
  const [featuresOpen, setFeaturesOpen] = useState(false)
  const [solutionsOpen, setSolutionsOpen] = useState(false)
  const [companyOpen, setCompanyOpen] = useState(false)
  const [resourcesOpen, setResourcesOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const navRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (navRef.current && !navRef.current.contains(event.target as Node)) {
        setFeaturesOpen(false)
        setSolutionsOpen(false)
        setCompanyOpen(false)
        setResourcesOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const featureItems = [
    {
      title: 'Workflow',
      desc: 'Assign tasks, schedule jobs, and track progress in real time. Keep your team aligned and your shop running like clockwork.',
      icon: BarChart3,
      color: 'bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400',
      href: '#workflow',
    },
    {
      title: 'Estimates',
      desc: 'Send professional estimates in seconds. Get approvals faster and get to work sooner.',
      icon: PlusCircle,
      color: 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400',
      href: '#estimates',
    },
    {
      title: 'Inventory',
      desc: "Know exactly what's in stock from parts to tires. Reduce delays and keep your jobs moving.",
      icon: Warehouse,
      color: 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400',
      href: '#inventory',
    },
    {
      title: 'Vehicle Inspections',
      desc: 'Catch issues early and build trust. Create digital inspection reports your customers can see and understand instantly.',
      icon: ClipboardCheck,
      color: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400',
      href: '#inspections',
    },
    {
      title: 'Packaged Services',
      desc: 'Bundle common repairs and maintenance into convenient packages that deliver more value and more revenue.',
      icon: Box,
      color: 'bg-cyan-50 dark:bg-cyan-950/40 text-cyan-600 dark:text-cyan-400',
      href: '#packages',
    },
    {
      title: 'Procurement',
      desc: 'Order the right parts, on time. Manage suppliers and restock with confidence without chasing paperwork.',
      icon: ShoppingBag,
      color: 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400',
      href: '#procurement',
    },
    {
      title: 'Appointment Scheduling',
      desc: 'Notifications to prompt action for upcoming tasks or events.',
      icon: Calendar,
      color: 'bg-teal-50 dark:bg-teal-950/40 text-teal-600 dark:text-teal-400',
      href: '#scheduling',
    },
    {
      title: 'Service Reminders',
      desc: 'Diagnose multiple systems with a single tool.',
      icon: Bell,
      color: 'bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400',
      href: '#reminders',
    },
  ]

  return (
    <header className="marketing sticky top-0 z-50 w-full border-b border-border/80 bg-card/95 backdrop-blur-md">
      <div
        ref={navRef}
        className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8"
      >
        {/* Brand Logo */}
        <Link href="/" aria-label="BayFlow home" className="flex items-center gap-2">
          <Logo size="md" />
        </Link>

        {/* Desktop Nav */}
        <nav aria-label="Main Navigation" className="hidden items-center gap-1 lg:flex xl:gap-2">
          {/* FEATURES DROPDOWN */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setFeaturesOpen(!featuresOpen)
                setSolutionsOpen(false)
                setCompanyOpen(false)
                setResourcesOpen(false)
              }}
              className="inline-flex items-center gap-1 px-3 py-2 text-xs font-normal tracking-wider text-muted-foreground uppercase transition-colors hover:text-brand-blue-ink xl:text-sm"
            >
              Features
              <ChevronDown
                className={`size-4 transition-transform duration-200 ${featuresOpen ? 'rotate-180 text-brand-blue-ink' : ''}`}
              />
            </button>

            {featuresOpen && (
              <div className="absolute top-full left-1/2 z-50 mt-3 w-[680px] -translate-x-1/2 rounded-3xl border border-border bg-card p-6 shadow-2xl transition-all duration-200 xl:w-[760px]">
                <div className="grid grid-cols-2 gap-4 border-b border-border-faint pb-5">
                  {featureItems.map((item) => (
                    <Link
                      key={item.title}
                      href={item.href}
                      onClick={() => setFeaturesOpen(false)}
                      className="group flex items-start gap-3.5 rounded-2xl p-3 transition-colors hover:bg-muted"
                    >
                      <div
                        className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${item.color}`}
                      >
                        <item.icon className="size-5" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-foreground transition-colors group-hover:text-brand-blue-ink">
                          {item.title}
                        </h4>
                        <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-helper">
                          {item.desc}
                        </p>
                      </div>
                    </Link>
                  ))}
                </div>

                <div className="flex items-center justify-between px-2 pt-4 text-xs font-semibold">
                  <a
                    href="tel:+923125699996"
                    className="inline-flex items-center gap-2 text-muted-foreground transition-colors hover:text-brand-blue-ink"
                  >
                    <PhoneCall className="size-3.5 text-brand-blue-ink" />
                    <span>Contact Sales</span>
                  </a>
                  <Link
                    href="#features-all"
                    onClick={() => setFeaturesOpen(false)}
                    className="inline-flex items-center gap-1.5 text-brand-blue-ink hover:underline"
                  >
                    <span>VIEW ALL FEATURES</span>
                    <ChevronRight className="size-4" />
                  </Link>
                </div>
              </div>
            )}
          </div>

          {/* SOLUTIONS DROPDOWN */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setSolutionsOpen(!solutionsOpen)
                setFeaturesOpen(false)
                setCompanyOpen(false)
                setResourcesOpen(false)
              }}
              className="inline-flex items-center gap-1 px-3 py-2 text-xs font-normal tracking-wider text-muted-foreground uppercase transition-colors hover:text-brand-blue-ink xl:text-sm"
            >
              Solutions
              <ChevronDown
                className={`size-4 transition-transform duration-200 ${solutionsOpen ? 'rotate-180 text-brand-blue-ink' : ''}`}
              />
            </button>

            {solutionsOpen && (
              <div className="absolute top-full left-0 z-50 mt-3 w-72 rounded-2xl border border-border bg-card p-3 shadow-xl">
                <div className="space-y-1">
                  {[
                    'Built for Every Type of Shop',
                    'Scalable for Any Size',
                    'Win Trust. Keep Customers.',
                    'From Check-In to Checkout',
                    'Your Parts and Purchasing',
                    'Profit Starts with Clarity',
                  ].map((sol) => (
                    <Link
                      key={sol}
                      href="#solutions"
                      onClick={() => setSolutionsOpen(false)}
                      className="block rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-brand-blue-ink"
                    >
                      {sol}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* COMPANY DROPDOWN */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setCompanyOpen(!companyOpen)
                setFeaturesOpen(false)
                setSolutionsOpen(false)
                setResourcesOpen(false)
              }}
              className="inline-flex items-center gap-1 px-3 py-2 text-xs font-normal tracking-wider text-muted-foreground uppercase transition-colors hover:text-brand-blue-ink xl:text-sm"
            >
              Company
              <ChevronDown
                className={`size-4 transition-transform duration-200 ${companyOpen ? 'rotate-180 text-brand-blue-ink' : ''}`}
              />
            </button>

            {companyOpen && (
              <div className="absolute top-full left-0 z-50 mt-3 w-64 rounded-2xl border border-border bg-card p-3 shadow-xl">
                <div className="space-y-1">
                  {['About Us', 'Contact Us'].map((item) => (
                    <Link
                      key={item}
                      href="#offices"
                      onClick={() => setCompanyOpen(false)}
                      className="block rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-brand-blue-ink"
                    >
                      {item}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* RESOURCES DROPDOWN */}
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setResourcesOpen(!resourcesOpen)
                setFeaturesOpen(false)
                setSolutionsOpen(false)
                setCompanyOpen(false)
              }}
              className="inline-flex items-center gap-1 px-3 py-2 text-xs font-normal tracking-wider text-muted-foreground uppercase transition-colors hover:text-brand-blue-ink xl:text-sm"
            >
              Resources
              <ChevronDown
                className={`size-4 transition-transform duration-200 ${resourcesOpen ? 'rotate-180 text-brand-blue-ink' : ''}`}
              />
            </button>

            {resourcesOpen && (
              <div className="absolute top-full left-0 z-50 mt-3 w-64 rounded-2xl border border-border bg-card p-3 shadow-xl">
                <div className="space-y-1">
                  {['Customer Stories', 'Help Center', 'Blog & Updates'].map((res) => (
                    <Link
                      key={res}
                      href="#support"
                      onClick={() => setResourcesOpen(false)}
                      className="block rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-brand-blue-ink"
                    >
                      {res}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </nav>

        {/* Right Actions: emerald Sign In, or the bell and account menu once signed in */}
        <div className="hidden items-center gap-4 lg:flex">
          <ThemeToggle />
          <SessionActions />
        </div>

        {/* Mobile Hamburger Button */}
        <div className="flex items-center gap-2 lg:hidden">
          <ThemeToggle size="sm" />
          <SessionActions compact />
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="Toggle navigation"
          >
            {mobileMenuOpen ? <X className="size-6" /> : <Menu className="size-6" />}
          </button>
        </div>
      </div>

      {/* Mobile Menu Drawer */}
      {mobileMenuOpen && (
        <div className="border-t border-border bg-card px-4 py-6 shadow-xl lg:hidden">
          <div className="flex flex-col space-y-4">
            <div>
              <p className="mb-2 text-xs font-bold tracking-wider text-subtle-foreground uppercase">
                Features
              </p>
              <div className="grid grid-cols-1 gap-2 pl-2">
                {featureItems.slice(0, 4).map((item) => (
                  <Link
                    key={item.title}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className="flex items-center gap-2 text-sm font-medium text-foreground"
                  >
                    <item.icon className="size-4 text-brand-blue-ink" />
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>
            </div>

            <hr className="border-border-faint" />

            <div className="flex flex-col space-y-2.5 text-sm font-normal text-foreground">
              <Link href="#solutions" onClick={() => setMobileMenuOpen(false)}>
                Solutions
              </Link>
              <Link href="#workflow" onClick={() => setMobileMenuOpen(false)}>
                Workflow
              </Link>
              <Link href="#support" onClick={() => setMobileMenuOpen(false)}>
                Support & Onboarding
              </Link>
            </div>

            <div className="pt-2">
              <Button
                asChild
                className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] w-full rounded-full font-semibold"
              >
                <Link href="/register" onClick={() => setMobileMenuOpen(false)}>
                  Book a Demo / Get Started
                </Link>
              </Button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}
