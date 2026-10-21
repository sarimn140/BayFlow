'use client'

import { useRef } from 'react'

type AutoFocusHandler = (event: Event) => void

/**
 * Where focus goes back to: the element that had it when the overlay opened, or — when that was
 * an item of a menu (which closes as the dialog opens) — the menu's trigger.
 */
function returnTarget(active: Element | null): HTMLElement | null {
  if (!(active instanceof HTMLElement) || active === document.body) return null
  const triggerId = active.closest('[role="menu"]')?.getAttribute('aria-labelledby')
  return (triggerId ? document.getElementById(triggerId) : null) ?? active
}

/**
 * Focus return for overlays opened from state (WCAG 2.4.3, DESIGN.md §6.10). Radix gives focus
 * back only to a `DialogTrigger`; a dialog opened with `open` from a button, a table row or a menu
 * item would leave focus on `<body>` when it closes. These handlers remember what had focus when
 * the overlay opened and focus it again on close — unless the page's own handler dealt with it
 * (called `preventDefault()` or moved focus), or that element is gone (focus it yourself then).
 *
 * `DialogContent`, `AlertDialogContent` and `SheetContent` already use it, around the page's own
 * `onOpenAutoFocus` / `onCloseAutoFocus`; reach for it only for another Radix overlay.
 */
export function useFocusReturn(
  onOpenAutoFocus?: AutoFocusHandler,
  onCloseAutoFocus?: AutoFocusHandler,
): { onOpenAutoFocus: AutoFocusHandler; onCloseAutoFocus: AutoFocusHandler } {
  const opener = useRef<HTMLElement | null>(null)
  return {
    onOpenAutoFocus: (event) => {
      // Radix calls this before it moves focus in, so the opener still has it.
      opener.current = returnTarget(document.activeElement)
      onOpenAutoFocus?.(event)
    },
    onCloseAutoFocus: (event) => {
      onCloseAutoFocus?.(event)
      const target = opener.current
      opener.current = null
      if (event.defaultPrevented || !target?.isConnected) return
      // Only when focus would be lost: the page may have placed it already (a confirmation).
      const active = document.activeElement
      if (active && active !== document.body) return
      event.preventDefault()
      target.focus()
    },
  }
}
