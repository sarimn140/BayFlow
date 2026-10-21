import {
  CarBattery,
  CircleDot,
  ClipboardCheck,
  Disc3,
  Droplets,
  Gauge,
  Snowflake,
  Sparkles,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { createElement } from 'react'

// First match wins, so the specific rules come before the broad ones ("AC gas top-up & leak
// inspection" is an AC job, "Brake inspection" a brake job, not a general inspection).
const RULES: ReadonlyArray<[RegExp, LucideIcon]> = [
  [/oil|filter|fluid/i, Droplets],
  [/brake|rotor|disc|pad/i, CircleDot],
  [/diagnos|obd|scan|ecu|check.?engine|engine.?light|warning.?light/i, Gauge],
  [/\bac\b|a\/c|air.?con|cool|gas/i, Snowflake],
  [/batter/i, CarBattery],
  [/tune|spark|plug|ignition|electric/i, Zap],
  [/tyre|tire|wheel|alignment|balanc/i, Disc3],
  [/inspect|check.?up|safety|pre.?purchase/i, ClipboardCheck],
  [/wash|detail|polish|clean/i, Sparkles],
]

/** An icon that suits a service, from words in its name; a wrench otherwise (repairs). */
export function serviceIcon(name: string): LucideIcon {
  return RULES.find(([pattern]) => pattern.test(name))?.[1] ?? Wrench
}

/** The same icon as a decorative element (`aria-hidden`), for lists that render one per row. */
export function ServiceIcon({ name, className }: { name: string; className?: string }) {
  return createElement(serviceIcon(name), { className, 'aria-hidden': true })
}
