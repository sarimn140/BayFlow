import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * D93: screens take colours from theme tokens only, so they follow the light / dark theme. Raw hex
 * classes, solid `bg-white` and the neutral grey palettes would stay light in dark mode.
 */

/** `src/` (this file lives in `src/app`). */
const SRC = path.resolve(import.meta.dirname, '..')

/** Surfaces that are dark in both themes keep fixed colours (none since the app bars went light). */
const FIXED_SURFACES = new Set<string>([])

function screenFiles(dir = SRC): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    const rel = path.relative(SRC, full).split(path.sep).join('/')
    if (entry.isDirectory()) return rel === 'components/ui' ? [] : screenFiles(full)
    if (!entry.name.endsWith('.tsx') || entry.name.endsWith('.test.tsx')) return []
    return FIXED_SURFACES.has(rel) ? [] : [rel]
  })
}

/**
 * A colour utility (any variant prefix) that bypasses the tokens: an arbitrary hex value, solid
 * white as a surface, or a step of the grey palettes. `text-white` on a fill and faint `white/NN`
 * overlays on dark surfaces are fine.
 */
const RAW_COLOUR =
  /(?<![\w-])(?:[\w-]+:)*(?:bg|text|border|ring|divide|from|via|to|fill|stroke|outline|shadow|decoration|caret|accent)-(?:\[#[0-9a-f]{3,8}\]|(?:neutral|gray|slate|zinc|stone)-\d{2,3})|(?<![\w-])(?:[\w-]+:)*bg-white(?![\w/-])/gi

describe('theme tokens (D93)', () => {
  const files = screenFiles()

  it('finds the screens', () => {
    expect(files.length).toBeGreaterThan(30)
    expect(files).toContain('app/(auth)/login/page.tsx')
  })

  it.each(files)('%s uses theme tokens for colour', (file) => {
    const source = readFileSync(path.join(SRC, file), 'utf8')
    expect(source.match(RAW_COLOUR) ?? []).toEqual([])
  })
})
