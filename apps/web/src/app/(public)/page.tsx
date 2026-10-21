'use client'

import {
  Cancel01Icon,
  ChartBarLineIcon,
  ShoppingCart01Icon,
  StarIcon,
  Tick02Icon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon, type HugeiconsIconProps } from '@hugeicons/react'
import Image from 'next/image'
import Link from 'next/link'
import { useState } from 'react'

import { CapabilityArt } from '@/components/landing/capability-art'
import { Button } from '@/components/ui/button'

/** Hugeicons (free stroke-rounded set) under the names this page already uses. */
type IconProps = Omit<HugeiconsIconProps, 'icon'>
const BarChart3 = (props: IconProps) => <HugeiconsIcon icon={ChartBarLineIcon} {...props} />
const Check = (props: IconProps) => <HugeiconsIcon icon={Tick02Icon} {...props} />
const ShoppingCart = (props: IconProps) => <HugeiconsIcon icon={ShoppingCart01Icon} {...props} />
const Star = (props: IconProps) => <HugeiconsIcon icon={StarIcon} {...props} />
const X = (props: IconProps) => <HugeiconsIcon icon={Cancel01Icon} {...props} />

export default function LandingPage() {
  const [demoModalOpen, setDemoModalOpen] = useState(false)
  const [demoSubmitted, setDemoSubmitted] = useState(false)
  const [demoForm, setDemoForm] = useState({
    name: '',
    email: '',
    phone: '',
    garageName: '',
    country: 'Pakistan',
  })

  const reviews = [
    {
      name: 'Kamran Sheikh',
      tint: 'blue' as const,
      role: 'Owner, Sheikh Motors · Lahore',
      metric: '2 shops, 1 dashboard',
      photo: '/testimonials/mechanic-1.jpg',
      quote:
        'I run two shops from one login. Every bay, every job, every rupee: I see it live without calling anyone.',
      rating: 5,
    },
    {
      name: 'Bilal Ahmed',
      tint: 'green' as const,
      role: 'Service Advisor, Karachi',
      metric: 'Approvals in minutes',
      photo: '/testimonials/mechanic-2.jpg',
      quote:
        'Customers approve estimates from their phone now. No more waiting on WhatsApp replies before we can start work.',
      rating: 4.9,
    },
    {
      name: 'Imran Ali',
      tint: 'orange' as const,
      role: 'Technician, Islamabad',
      metric: 'No paper job cards',
      photo: '/testimonials/mechanic-3.jpg',
      quote:
        'My screen shows only my jobs. I log the inspection, add photos, and the parts counter already knows what I need.',
      rating: 4.8,
    },
    {
      name: 'Sara Malik',
      tint: 'blue' as const,
      role: 'QC Inspector, Lahore',
      metric: 'Zero missed checks',
      photo: '/testimonials/mechanic-4.jpg',
      quote:
        'Nothing leaves the bay until I sign it off. If a check fails it goes straight back to the technician, with notes.',
      rating: 5,
    },
    {
      name: 'Usman Tariq',
      tint: 'green' as const,
      role: 'Parts Manager, Faisalabad',
      metric: 'Parts ready on time',
      photo: '/testimonials/mechanic-5.jpg',
      quote:
        'Parts requests arrive with the job attached. I issue, track and restock without chasing anyone down the floor.',
      rating: 4.9,
    },
  ]

  const capabilities = [
    {
      title: 'Workflow' as const,
      desc: 'Assign tasks, schedule jobs, and track progress in real time. Keep your team aligned and your shop running like clockwork.',
    },
    {
      title: 'Estimates' as const,
      desc: 'Send professional estimates in seconds. Get approvals faster and get to work sooner.',
    },
    {
      title: 'Inventory' as const,
      desc: "Know exactly what's in stock from parts to tires. Reduce delays and keep your jobs moving.",
    },
    {
      title: 'Vehicle Inspections' as const,
      desc: 'Catch issues early and build trust. Create digital inspection reports your customers can see and understand instantly.',
    },
    {
      title: 'Packaged Services' as const,
      desc: 'Bundle common repairs and maintenance into convenient packages that deliver more value and more revenue.',
    },
    {
      title: 'Procurement' as const,
      desc: 'Order the right parts, on time. Manage suppliers and restock with confidence without chasing paperwork.',
    },
  ]

  return (
    <div className="marketing relative w-full overflow-hidden bg-card text-foreground">
      {/* ========================================================
          1. HERO SECTION (100% PIXEL PERFECT TO GARAGEBOX.IO)
          ======================================================== */}
      <section className="bg-grid-pattern relative w-full pt-10 pb-16 md:pt-16 md:pb-24">
        {/* Soft radial backdrop */}
        <div className="pointer-events-none absolute inset-0 bg-radial-[circle_at_50%_15%] from-blue-50/40 via-transparent to-transparent dark:from-blue-950/40" />
        {/* Halo behind the headline: a faint blue glow, then a white wash that fades the grid out under the copy */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-[-6%] left-1/2 aspect-square w-[min(1100px,140vw)] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(16,71,250,0.09)_0%,rgba(16,71,250,0.04)_35%,transparent_68%)] blur-2xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-[2%] left-1/2 h-[min(560px,90vw)] w-[min(980px,130vw)] -translate-x-1/2 rounded-[50%] bg-[radial-gradient(ellipse_at_center,color-mix(in_srgb,var(--background)_95%,transparent)_0%,color-mix(in_srgb,var(--background)_70%,transparent)_40%,transparent_70%)]"
        />

        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          {/* Heading & Copy */}
          <div className="mx-auto max-w-4xl text-center">
            <h1 className="text-4xl leading-[1.12] font-extrabold tracking-tight text-foreground sm:text-5xl md:text-6xl lg:text-[68px]">
              Auto Repair Garage Management <br className="hidden sm:inline" />
              Software{' '}
              <span className="align-baseline font-handwriting text-5xl font-normal text-brand-green italic sm:text-6xl md:text-7xl lg:text-[76px]">
                in Pakistan
              </span>
            </h1>

            <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed font-normal text-muted-foreground sm:text-lg">
              Take control of your auto repair business with BayFlow, Pakistan&apos;s leading garage
              management software. Simplify job scheduling, invoicing, and inventory control for
              maximum efficiency.
            </p>

            {/* CTAs */}
            <div className="mt-8 flex flex-row items-center justify-center gap-4">
              <button
                type="button"
                onClick={() => setDemoModalOpen(true)}
                className="neu-raised neu-press bg-card text-foreground hover:brightness-105 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-7 py-3 text-sm font-semibold sm:px-8 sm:text-base"
              >
                Book a Demo
              </button>
              <Link
                href="/register"
                className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-7 py-3 text-center text-sm font-semibold sm:px-9 sm:text-base"
              >
                Get Started
              </Link>
            </div>
          </div>

          {/* ========================================================
              HERO ARTWORK (original BayFlow illustration)
              ======================================================== */}
          <div className="relative mx-auto mt-12 flex max-w-[1020px] justify-center md:mt-16">
            {/* Desktop Hero Image */}
            <div className="hidden w-full md:block">
              <Image
                src="/garagebox/hero-desktop.webp"
                alt="BayFlow job card showing a Honda Civic in repair, an itemised estimate and a QC-passed notice"
                width={1020}
                height={580}
                priority
                sizes="(min-width: 1280px) 1020px, (min-width: 768px) 90vw, 100vw"
                className="pointer-events-none h-auto w-full object-contain drop-shadow-md select-none"
              />
            </div>

            {/* Mobile Hero Image */}
            <div className="block w-full max-w-[480px] md:hidden">
              <Image
                src="/garagebox/hero-mobile.webp"
                alt="BayFlow job card showing a Honda Civic in repair, an itemised estimate and a QC-passed notice"
                width={480}
                height={480}
                priority
                sizes="(max-width: 640px) 100vw, 480px"
                className="pointer-events-none h-auto w-full object-contain select-none"
              />
            </div>
          </div>

          {/* ========================================================
              RATING & PLATFORM LOGOS
              ======================================================== */}
          <div className="mt-12 flex flex-col items-center justify-center gap-6 text-center md:mt-16">
            {/* 5-Star Rating */}
            <div className="flex items-center gap-1.5">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  className="size-5 fill-amber-500 text-amber-500 dark:text-amber-400"
                />
              ))}
              <span className="ml-2 text-sm font-bold text-foreground">
                5-Star Rated based on 200+ reviews
              </span>
            </div>

            {/* Platform Review Logos Banner */}
            <div className="mt-6 flex flex-wrap items-center justify-center gap-6 opacity-85 transition-opacity hover:opacity-100 sm:gap-10 md:gap-12">
              <Image
                src="/garagebox/review-google.svg"
                alt="Google Reviews"
                width={41}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
              <Image
                src="/garagebox/review-g2.svg"
                alt="G2 Reviews"
                width={41}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
              <Image
                src="/garagebox/review-clutch.svg"
                alt="Clutch Reviews"
                width={100}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
              <Image
                src="/garagebox/review-trustradius.svg"
                alt="TrustRadius Reviews"
                width={50}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
              <Image
                src="/garagebox/review-trustpilot.svg"
                alt="Trustpilot Reviews"
                width={146}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
              <Image
                src="/garagebox/review-softwaresuggest.svg"
                alt="SoftwareSuggest Reviews"
                width={120}
                height={36}
                className="h-8 w-auto object-contain dark:brightness-0 dark:invert"
              />
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          HERO CAROUSEL / IMAGE GALLERY SECTION
          ======================================================== */}
      <section className="relative w-full overflow-hidden border-t border-border/70 bg-muted/50 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto mb-12 max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              <span className="font-handwriting text-4xl font-normal text-brand-blue-ink italic sm:text-5xl md:text-6xl">
                See BayFlow
              </span>{' '}
              in Action
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
              Swipe through screenshots of the BayFlow dashboard, technician app, and customer
              portal.
            </p>
          </div>

          {/* Carousel */}
          <div className="relative overflow-hidden rounded-2xl border border-border bg-card">
            <div className="aspect-[16/9] w-full">
              <Image
                src="/bayflow/carousel-1.webp"
                alt="BayFlow Dashboard - Shop Overview"
                fill
                priority
                sizes="(max-width: 768px) 100vw, (max-width: 1280px) 90vw, 1200px"
                className="object-cover"
              />
            </div>
            <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 gap-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <button
                  key={i}
                  className={`h-2.5 w-2.5 rounded-full transition-all duration-300 ${
                    i === 1 ? 'w-7 bg-brand-blue' : 'bg-white/50 hover:bg-card'
                  }`}
                  aria-label={`View screenshot ${i}`}
                />
              ))}
            </div>
            <button
              className="absolute top-1/2 left-4 size-10 -translate-y-1/2 rounded-full neu-raised neu-press bg-card text-foreground transition-colors md:left-6"
              aria-label="Previous screenshot"
            >
              <svg className="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
            </button>
            <button
              className="absolute top-1/2 right-4 size-10 -translate-y-1/2 rounded-full neu-raised neu-press bg-card text-foreground transition-colors md:right-6"
              aria-label="Next screenshot"
            >
              <svg className="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </button>
          </div>
        </div>
      </section>

      {/* ========================================================
          2. TESTIMONIALS SECTION — story cards (text + duotone portrait)
          ======================================================== */}
      <section className="relative w-full overflow-hidden border-t border-border/70 bg-muted/50 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              Trusted by{' '}
              <span className="font-handwriting text-4xl font-normal text-brand-blue-ink italic sm:text-5xl md:text-6xl">
                Garages
              </span>
              , Proven by <span className="text-brand-green">Performance</span>
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
              Owners, service advisors, technicians, QC and parts teams run every job on BayFlow,
              from check-in to pick-up, on one shared workflow.
            </p>
          </div>
        </div>

        {/* Auto-scrolling marquee: list rendered twice, track slides -50% and loops. Pauses on hover. */}
        <div className="mt-14 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_4%,#000_96%,transparent)]">
          <div className="reviews-marquee flex w-max gap-6 py-6">
            {[...reviews, ...reviews].map((r, i) => {
              const tone = {
                blue: { card: 'from-brand-blue/10 to-card', duo: 'bg-brand-blue' },
                green: { card: 'from-brand-green/10 to-card', duo: 'bg-brand-green' },
                orange: { card: 'from-brand-orange/10 to-card', duo: 'bg-brand-orange' },
              }[r.tint]
              return (
                <article
                  key={`${r.name}-${i}`}
                  aria-hidden={i >= reviews.length || undefined}
                  className={`flex w-[88vw] max-w-[780px] shrink-0 flex-col-reverse gap-5 rounded-[28px] border border-card bg-gradient-to-br p-5 shadow-[0_10px_40px_-20px_rgba(17,24,39,0.25)] sm:flex-row sm:p-6 ${tone.card}`}
                >
                  <div className="flex flex-1 flex-col justify-between gap-8 p-2 sm:py-4">
                    <div>
                      <blockquote className="text-2xl leading-tight font-semibold tracking-tight text-foreground md:text-[28px]">
                        {r.quote}
                      </blockquote>
                      <div className="mt-6 text-sm">
                        <p className="font-semibold text-foreground">{r.name}</p>
                        <p className="text-helper">{r.role}</p>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-foreground">
                        <Star className="size-4 fill-amber-500 text-amber-500 dark:text-amber-400" />
                        {r.rating.toFixed(1)} · {r.metric}
                      </span>
                    </div>
                  </div>

                  {/* Duotone portrait: grayscale photo screened with brand tint */}
                  <div className="relative aspect-[4/5] w-full overflow-hidden rounded-[20px] sm:w-[46%]">
                    <Image
                      src={r.photo}
                      alt=""
                      fill
                      sizes="(min-width: 640px) 360px, 88vw"
                      className="object-cover contrast-125 grayscale"
                    />
                    <div
                      aria-hidden="true"
                      className={`absolute inset-0 opacity-80 mix-blend-screen ${tone.duo}`}
                    />
                  </div>
                </article>
              )
            })}
          </div>
        </div>
      </section>

      {/* ========================================================
          3. FEATURE 1: STREAMLINE WORKFLOW (Exact SVG)
          ======================================================== */}
      <section id="workflow" className="relative w-full border-t border-border/60 bg-card py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-16">
            {/* Left Content */}
            <div className="space-y-8 lg:col-span-6">
              <div>
                <h2 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
                  <span className="font-handwriting text-4xl font-normal text-foreground italic sm:text-5xl md:text-6xl">
                    Streamline
                  </span>{' '}
                  Workflow, and Control Inventory
                </h2>
              </div>

              {/* Bullet Points */}
              <div className="space-y-6">
                <div className="flex items-start gap-4">
                  <BarChart3 className="mt-0.5 size-6 shrink-0 text-subtle-foreground" />
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Take Control of Your Day
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Estimates, approvals, inspections and job cards in one flow. Assign tasks and
                      track labour in real time.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <ShoppingCart className="mt-0.5 size-6 shrink-0 text-subtle-foreground" />
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Never Run Out, Never Overstock
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Turn parts requests into purchase orders in seconds. Reserve, issue and track
                      every part.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <BarChart3 className="mt-0.5 size-6 shrink-0 text-subtle-foreground" />
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      See Where You Earn, and Where You Don&apos;t
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Visual reports show profit leaks and labour time, so you can decide with data.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  href="/register"
                  className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] inline-block rounded-full px-9 py-3.5 text-sm font-semibold sm:text-base"
                >
                  Get Started
                </Link>
              </div>
            </div>

            {/* Right Graphic: Exact SVG from BayFlow */}
            <div className="flex justify-center lg:col-span-6">
              <div className="relative flex w-full max-w-[514px] justify-center">
                <Image
                  src="/garagebox/feature-workflow.svg"
                  alt="Streamline Workflow, and Control Inventory"
                  width={514}
                  height={512}
                  className="h-auto w-full object-contain drop-shadow-md"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          4. FEATURE 2: DELIVER UNFORGETTABLE EXPERIENCE (Exact SVG)
          ======================================================== */}
      <section className="relative w-full border-t border-border/60 bg-muted/50 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-16">
            {/* Left Graphic: Exact SVG from BayFlow */}
            <div className="order-2 flex justify-center lg:order-1 lg:col-span-6">
              <div className="relative flex w-full max-w-[514px] justify-center">
                <Image
                  src="/garagebox/feature-crm.svg"
                  alt="Deliver an Unforgettable Customer Experience"
                  width={514}
                  height={512}
                  className="h-auto w-full object-contain drop-shadow-md"
                />
              </div>
            </div>

            {/* Right Content */}
            <div className="order-1 space-y-8 lg:order-2 lg:col-span-6">
              <div>
                <h2 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
                  <span className="font-handwriting text-4xl font-normal text-foreground italic sm:text-5xl md:text-6xl">
                    Deliver an
                  </span>{' '}
                  Unforgettable Customer Experience
                </h2>
              </div>

              {/* Bullet Points */}
              <div className="space-y-6">
                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Connect, Capture, Communicate
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Keep customers engaged from first contact to final service. Send real-time
                      updates about appointments, vehicle inspections, and estimates via SMS, Email,
                      or WhatsApp.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Never Miss a Beat with Smart Reminders
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Automate service alerts and document renewal reminders. Help customers stay on
                      top of their maintenance without lifting a finger.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2 0 .68.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2 0-.68.07-1.35.16-2h4.68c.09.65.16 1.32.16 2 0 .68-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2 0-.68-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Book Online in Seconds No Calls Needed
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Let your website do the work. With online booking and custom web forms, your
                      customers can schedule services anytime, from anywhere.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  href="/register"
                  className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] inline-block rounded-full px-9 py-3.5 text-sm font-semibold sm:text-base"
                >
                  Get Started
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          5. FEATURE 3: MAXIMIZE SHOP PRODUCTIVITY (Exact SVG)
          ======================================================== */}
      <section className="relative w-full border-t border-border/60 bg-card py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-12 lg:gap-16">
            {/* Left Content */}
            <div className="space-y-8 lg:col-span-6">
              <div>
                <h2 className="text-3xl leading-tight font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
                  <span className="font-handwriting text-4xl font-normal text-foreground italic sm:text-5xl md:text-6xl">
                    Maximize
                  </span>{' '}
                  Shop Productivity with Technician App
                </h2>
              </div>

              {/* Bullet Points */}
              <div className="space-y-6">
                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Track Time. Drive Results.
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Stay on top of work hours with our intuitive Time Clock feature. Keep your
                      team motivated, accountable, and focused without micromanaging.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-10 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Bring Order to the Chaos
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      Simplify how your team works. With BayFlow, manage tasks, track deadlines, and
                      stay on top of progress all from a single, easy-to-use dashboard.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <svg
                    className="mt-0.5 size-6 shrink-0 fill-current text-subtle-foreground"
                    viewBox="0 0 24 24"
                  >
                    <path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z" />
                  </svg>
                  <div>
                    <h3 className="text-base font-bold text-foreground sm:text-lg">
                      Power Your Team on the Go
                    </h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      With the BayFlow for Techs mobile app (iOS & Android), your technicians stay
                      connected, informed, and engaged wherever they are.
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  href="/register"
                  className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] inline-block rounded-full px-9 py-3.5 text-sm font-semibold sm:text-base"
                >
                  Get Started
                </Link>
              </div>
            </div>

            {/* Right Graphic: Exact SVG from BayFlow */}
            <div className="flex justify-center lg:col-span-6">
              <div className="relative flex w-full max-w-[514px] justify-center">
                <Image
                  src="/garagebox/feature-technician.svg"
                  alt="Maximize Shop Productivity with Technician App"
                  width={514}
                  height={512}
                  className="h-auto w-full object-contain drop-shadow-md"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          6. ALL-IN-ONE CAPABILITIES GRID
          ======================================================== */}
      <section
        id="features-all"
        className="relative w-full border-t border-border/60 bg-muted/50 py-20"
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              Garage Management Software
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
              BayFlow helps you manage service bookings, estimates, job cards, payments,
              inspections, inventory, customer communication, and labor tracking in an all-in-one
              garage management software.
            </p>
          </div>

          {/* Two columns x three rows: copy left, product mock-up right */}
          <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-2">
            {capabilities.map((c) => (
              <div
                key={c.title}
                className="group flex flex-col-reverse overflow-hidden rounded-3xl border border-border bg-card shadow-sm transition-shadow duration-300 hover:shadow-lg sm:min-h-[220px] sm:flex-row"
              >
                <div className="flex flex-1 flex-col justify-center p-7">
                  <h3 className="text-lg font-semibold text-foreground">{c.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-helper">{c.desc}</p>
                </div>
                <div className="h-48 bg-secondary sm:h-auto sm:w-[48%]">
                  <CapabilityArt title={c.title} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========================================================
          7. SUPPORT & ONBOARDING
          "Built for Garages. Backed by Humans."
          ======================================================== */}
      <section
        id="support"
        className="bg-grid-pattern relative w-full border-t border-border/60 bg-card py-20"
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              Built for{' '}
              <span className="font-handwriting text-4xl font-normal text-foreground italic sm:text-5xl md:text-6xl">
                Garages.
              </span>{' '}
              Backed by Humans.
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground sm:text-base">
              From setup to daily operations, we are here to keep your garage running smoothly every
              mile of the way.
            </p>
          </div>

          {/* Feature cards: mini product illustration on a grey panel, copy underneath */}
          <div className="mt-14 grid grid-cols-1 gap-10 md:grid-cols-3 md:gap-8">
            {/* Card 1: Data Migration */}
            <div className="flex flex-col overflow-hidden rounded-3xl border border-border bg-card pb-7 shadow-sm">
              <div className="relative flex aspect-[16/11] flex-col items-center justify-center overflow-hidden bg-secondary p-6">
                <p className="text-2xl font-semibold tracking-tight text-foreground">BayFlow</p>
                {/* Connector tree */}
                <svg
                  aria-hidden="true"
                  viewBox="0 0 300 48"
                  className="mt-2 h-10 w-[78%] text-border-medium"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <path d="M150 0 V20 M30 48 V30 Q30 20 40 20 H260 Q270 20 270 30 V48 M150 20 V48" />
                </svg>
                <div className="flex w-[86%] justify-between">
                  {['Excel', 'Paper', 'Old POS'].map((src) => (
                    <span
                      key={src}
                      className="flex size-14 items-center justify-center rounded-full bg-card text-[11px] font-semibold text-muted-foreground shadow-sm ring-1 ring-border"
                    >
                      {src}
                    </span>
                  ))}
                </div>
                <span className="mt-5 rounded-full border border-border bg-card/70 px-4 py-1 text-xs text-helper">
                  Customers · Vehicles · Invoices
                </span>
              </div>
              <h3 className="mt-6 px-7 text-lg font-semibold text-foreground">Data Migration</h3>
              <p className="mt-2 px-7 text-sm leading-relaxed text-helper">
                We move your customers, vehicles and invoices into BayFlow for you. Nothing left
                behind.
              </p>
              <button
                type="button"
                onClick={() => setDemoModalOpen(true)}
                className="mt-auto self-start px-7 pt-4 text-sm font-semibold text-brand-blue-ink hover:underline"
              >
                Contact us →
              </button>
            </div>

            {/* Card 2: Live Support */}
            <div className="flex flex-col overflow-hidden rounded-3xl border border-border bg-card pb-7 shadow-sm">
              <div className="relative flex aspect-[16/11] flex-col justify-center gap-3 overflow-hidden bg-secondary p-6">
                <div className="max-w-[78%] self-end rounded-2xl rounded-br-md bg-foreground px-4 py-2.5 text-xs text-background shadow-sm">
                  How do I add a second technician?
                </div>
                <div className="flex max-w-[86%] items-end gap-2">
                  <span className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] flex size-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
                    GB
                  </span>
                  <div className="rounded-2xl rounded-bl-md bg-card px-4 py-2.5 text-xs text-muted-foreground shadow-sm ring-1 ring-border">
                    Go to Team → Add member, pick &ldquo;Technician&rdquo;. Done in 30 seconds.
                  </div>
                </div>
                <div
                  className="ml-9 flex w-14 gap-1 rounded-full bg-card px-3 py-2 shadow-sm ring-1 ring-border"
                  aria-hidden="true"
                >
                  {[0, 1, 2].map((d) => (
                    <span key={d} className="size-1.5 rounded-full bg-layer-selected" />
                  ))}
                </div>
                <span className="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full border border-border bg-card/70 px-4 py-1 text-xs whitespace-nowrap text-helper">
                  Mon–Fri · 10 am – 7 pm
                </span>
              </div>
              <h3 className="mt-6 px-7 text-lg font-semibold text-foreground">Live Support</h3>
              <p className="mt-2 px-7 text-sm leading-relaxed text-helper">
                Real people on chat, Monday to Friday, 10 am to 7 pm PKT.
              </p>
              <a
                href="https://wa.me/923125699996"
                target="_blank"
                rel="noopener noreferrer"
                className="mt-auto self-start px-7 pt-4 text-sm font-semibold text-brand-blue-ink hover:underline"
              >
                Chat with us →
              </a>
            </div>

            {/* Card 3: Help Center */}
            <div className="flex flex-col overflow-hidden rounded-3xl border border-border bg-card pb-7 shadow-sm">
              <div className="relative aspect-[16/11] overflow-hidden bg-secondary">
                <div className="absolute inset-y-6 -right-6 left-6 rounded-xl bg-card shadow-sm ring-1 ring-border">
                  <div className="flex items-center gap-2 border-b border-border-faint px-4 py-3 text-xs text-subtle-foreground">
                    <span aria-hidden="true">⌕</span> Search guides…
                  </div>
                  {[
                    'Create your first job card',
                    'Send an estimate for approval',
                    'Set up parts inventory',
                  ].map((g) => (
                    <div
                      key={g}
                      className="flex items-center gap-3 border-b border-border-faint px-4 py-2.5 text-xs text-muted-foreground"
                    >
                      <span className="size-5 shrink-0 rounded-md bg-secondary" />
                      {g}
                    </div>
                  ))}
                  <div className="flex items-center gap-3 px-4 py-2.5">
                    <span className="size-5 shrink-0 rounded-md bg-secondary" />
                    <span className="h-2 w-32 rounded-full bg-secondary" />
                  </div>
                </div>
              </div>
              <h3 className="mt-6 px-7 text-lg font-semibold text-foreground">Help Center</h3>
              <p className="mt-2 px-7 text-sm leading-relaxed text-helper">
                Step-by-step guides for every feature, from first job card to monthly reports.
              </p>
              <a
                href="#help-center"
                className="mt-auto self-start px-7 pt-4 text-sm font-semibold text-brand-blue-ink hover:underline"
              >
                Browse guides →
              </a>
            </div>
          </div>

          <div className="mt-12 flex flex-row items-center justify-center gap-4">
            <button
              type="button"
              onClick={() => setDemoModalOpen(true)}
              className="neu-raised neu-press bg-card text-foreground hover:brightness-105 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-7 py-3 text-sm font-semibold sm:px-8 sm:text-base"
            >
              Book a Demo
            </button>
            <Link
              href="/register"
              className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-7 py-3 text-center text-sm font-semibold sm:px-9 sm:text-base"
            >
              Get Started
            </Link>
          </div>
        </div>
      </section>

      {/* ========================================================
          8. EXPERIENCE MOBILE APP BANNER
          ======================================================== */}
      <section className="relative w-full bg-card py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="relative grid overflow-hidden rounded-[32px] bg-secondary lg:grid-cols-12">
            {/* Left: headline, CTA pinned to the bottom */}
            <div className="flex flex-col justify-between gap-12 p-8 sm:p-12 lg:col-span-7 lg:min-h-[460px] lg:p-14">
              <div>
                <h2 className="max-w-xl text-4xl leading-[1.08] font-semibold tracking-tight text-foreground sm:text-5xl">
                  Run your whole garage from your pocket.
                </h2>
                <p className="mt-5 max-w-md text-base leading-relaxed text-muted-foreground">
                  Jobs, inspections, estimates and invoices on one app, so your team can work from
                  the bay floor.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
                <Link
                  href="/register"
                  className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] rounded-full px-6 py-3 text-sm font-semibold"
                >
                  Get Started
                </Link>
              </div>
            </div>

            {/* Right: phone rises from the bottom edge and is cropped by the card */}
            <div className="relative flex h-[340px] justify-center lg:col-span-5 lg:h-auto">
              <Image
                src="/garagebox/mobile-mockup.png"
                alt="BayFlow mobile app"
                width={350}
                height={596}
                sizes="(max-width: 1024px) 260px, 320px"
                className="absolute top-8 w-[260px] drop-shadow-2xl lg:top-20 lg:w-[320px]"
              />
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          BOOK A DEMO MODAL
          ======================================================== */}
      {demoModalOpen && (
        <div className="fixed inset-0 z-50 flex animate-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm duration-200 fade-in">
          <div className="relative w-full max-w-lg rounded-3xl border border-border bg-card p-6 shadow-2xl sm:p-8">
            <button
              type="button"
              onClick={() => {
                setDemoModalOpen(false)
                setDemoSubmitted(false)
              }}
              className="absolute top-5 right-5 rounded-full p-2 text-subtle-foreground transition-colors hover:bg-secondary hover:text-foreground"
              aria-label="Close"
            >
              <X className="size-5" />
            </button>

            {demoSubmitted ? (
              <div className="py-6 text-center">
                <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400">
                  <Check className="size-8 stroke-[3]" />
                </div>
                <h3 className="text-2xl font-bold text-foreground">Demo Request Received!</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Thank you! Our garage software specialist will reach out to you within 2 business
                  hours on WhatsApp/Phone.
                </p>
                <div className="mt-6">
                  <Button
                    onClick={() => {
                      setDemoModalOpen(false)
                      setDemoSubmitted(false)
                    }}
                    className="rounded-full bg-brand-blue px-8"
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-xs font-bold tracking-wider text-brand-blue-ink uppercase">
                  Free Live Walkthrough
                </p>
                <h3 className="mt-1 text-2xl font-bold text-foreground">
                  Book a Personalized Demo
                </h3>
                <p className="mt-1 text-xs text-helper">
                  See how BayFlow helps auto garages schedule jobs, track parts, and increase profit
                  by 40%.
                </p>

                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    setDemoSubmitted(true)
                  }}
                  className="mt-6 space-y-4"
                >
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground">
                      Full Name *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Tariq Mehmood"
                      value={demoForm.name}
                      onChange={(e) => setDemoForm({ ...demoForm, name: e.target.value })}
                      className="w-full rounded-xl border border-border-medium px-3.5 py-2.5 text-sm outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-xs font-bold text-muted-foreground">
                        Phone / WhatsApp *
                      </label>
                      <input
                        type="tel"
                        required
                        placeholder="+92 300 1234567"
                        value={demoForm.phone}
                        onChange={(e) => setDemoForm({ ...demoForm, phone: e.target.value })}
                        className="w-full rounded-xl border border-border-medium px-3.5 py-2.5 text-sm outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-bold text-muted-foreground">
                        Work Email
                      </label>
                      <input
                        type="email"
                        placeholder="tariq@garage.com"
                        value={demoForm.email}
                        onChange={(e) => setDemoForm({ ...demoForm, email: e.target.value })}
                        className="w-full rounded-xl border border-border-medium px-3.5 py-2.5 text-sm outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground">
                      Garage / Workshop Name *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Apex Auto Care Lahore"
                      value={demoForm.garageName}
                      onChange={(e) => setDemoForm({ ...demoForm, garageName: e.target.value })}
                      className="w-full rounded-xl border border-border-medium px-3.5 py-2.5 text-sm outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue"
                    />
                  </div>

                  <div className="pt-2">
                    <button
                      type="submit"
                      className="neu-primary neu-press bg-brand-blue text-white hover:brightness-110 active:scale-[0.98] transition-[filter,transform,box-shadow] w-full rounded-full py-3 text-sm font-bold"
                    >
                      Confirm Demo Request
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
