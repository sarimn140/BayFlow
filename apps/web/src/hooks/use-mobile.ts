import * as React from 'react'

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribe(onChange: () => void) {
  const mql = window.matchMedia(MOBILE_QUERY)
  mql.addEventListener('change', onChange)
  return () => mql.removeEventListener('change', onChange)
}

const getSnapshot = () => window.matchMedia(MOBILE_QUERY).matches

// The server (and the first hydration pass) render the desktop layout.
const getServerSnapshot = () => false

/**
 * BayFlow: rewritten from shadcn's useEffect + setState version, which fails the
 * `react-hooks/set-state-in-effect` rule; `useSyncExternalStore` is React's API for subscribing
 * to an external source such as `matchMedia`. Same contract: `true` below 768 px.
 */
export function useIsMobile() {
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
