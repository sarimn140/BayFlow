/** First focusable element on every page (spec 09 §4.1); every shell renders `<main id="main">`. */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-md focus:outline-2 focus:outline-offset-2"
    >
      Skip to main content
    </a>
  )
}
