const BASE = 'https://bayflow.invalid'

/**
 * The `next` destination after login (spec 09 §2.8): followed only when it is a path on this site.
 * Parsing with the URL API applies the browser's own rules (tabs and newlines stripped, `\` read
 * as `/`), so `//evil.example`, `/\evil.example` and `/\t/evil.example` are all refused.
 */
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next?.startsWith('/')) return null
  let url: URL
  try {
    url = new URL(next, BASE)
  } catch {
    return null
  }
  if (url.origin !== BASE) return null
  return `${url.pathname}${url.search}${url.hash}`
}
