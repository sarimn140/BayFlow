'use client'

import { useSyncExternalStore } from 'react'

import { readSeedSnapshot } from '@/lib/mock-data'

function subscribe(callback: () => void) {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener('bf:store-update', callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener('bf:store-update', callback)
    window.removeEventListener('storage', callback)
  }
}

/**
 * Subscribes a component to the mock store. `getter` must read through the `@/lib/mock-data`
 * getters: they return the same object or array until the stored data changes, as
 * useSyncExternalStore requires. While React hydrates server HTML the snapshot is the seed data
 * (what the server rendered); React then re-renders once with the data stored in this browser.
 */
export function useMockStore<T>(getter: () => T): T {
  return useSyncExternalStore(subscribe, getter, () => readSeedSnapshot(getter))
}

const subscribeNever = () => () => {}

/**
 * False while React hydrates server HTML (`useMockStore` then still returns the seed data), true
 * once this browser's stored data is in use. Effects that act on stored data, such as the
 * role-home redirects, wait for it so they never act on the seed user.
 */
export function useMockStoreReady(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  )
}
