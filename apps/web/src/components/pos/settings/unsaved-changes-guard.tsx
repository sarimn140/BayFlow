'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

/** "Shop profile", "Shop profile and Opening hours", "A, B and C". */
function listOf(names: ReadonlyArray<string>): string {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * `UnsavedChangesGuard` (spec 09 §2.10, UX rule R9 "Never lose input"): while any section has
 * unsaved changes, reloading or closing the tab asks first (`beforeunload`), and following an
 * in-app link opens a confirmation instead of leaving. Links that open a new tab are let through.
 */
export function UnsavedChangesGuard({ sections }: { sections: ReadonlyArray<string> }) {
  const router = useRouter()
  const [pendingHref, setPendingHref] = useState<string | null>(null)
  const guarding = sections.length > 0

  useEffect(() => {
    if (!guarding) return

    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      // Older browsers only show the prompt when a return value is set.
      event.returnValue = ''
    }

    // Capture phase on window: runs before Next's <Link> handler, which then never sees the click.
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      if (!(event.target instanceof Element)) return
      const anchor = event.target.closest('a[href]')
      if (!(anchor instanceof HTMLAnchorElement)) return
      if ((anchor.target && anchor.target !== '_self') || anchor.hasAttribute('download')) return
      const url = new URL(anchor.href, window.location.href)
      if (url.origin !== window.location.origin) return
      if (url.pathname === window.location.pathname && url.search === window.location.search) return
      event.preventDefault()
      event.stopPropagation()
      setPendingHref(`${url.pathname}${url.search}${url.hash}`)
    }

    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('click', onClick, true)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('click', onClick, true)
    }
  }, [guarding])

  const leave = () => {
    const href = pendingHref
    setPendingHref(null)
    if (href) router.push(href)
  }

  return (
    <AlertDialog
      open={pendingHref !== null}
      onOpenChange={(open) => {
        if (!open) setPendingHref(null)
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave without saving?</AlertDialogTitle>
          <AlertDialogDescription>
            {sections.length > 0
              ? `You have unsaved changes in ${listOf(sections)}. They'll be lost if you leave this page.`
              : 'Your changes will be lost if you leave this page.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep editing</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={leave}>
            Leave without saving
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
