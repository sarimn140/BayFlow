import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Web unit tests (spec 12 §3.8): Vitest + React Testing Library + jsdom, no network calls.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Vite 8 resolves the `@/*` alias from tsconfig.json natively (no vite-tsconfig-paths).
    tsconfigPaths: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', '*.test.ts'],
    css: false,
  },
})
