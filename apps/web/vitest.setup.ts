import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Without Vitest globals, React Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup()
})

// jsdom has no ResizeObserver; Radix measures with it (Switch crashes on render without it).
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
