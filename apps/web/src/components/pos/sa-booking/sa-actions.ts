import {
  Ban,
  BellRing,
  CalendarCheck,
  CircleCheckBig,
  CircleX,
  FilePen,
  PackageSearch,
  PencilLine,
  Send,
  Undo2,
  UserCheck,
  type LucideIcon,
} from 'lucide-react'

import { CANCELLABLE_STATUSES, type BookingStatus } from '@/lib/status'

/**
 * The booking actions a Service Advisor or Owner takes on SA-02 (spec 10 SA-02; spec 08 T02–T22,
 * O1 and O3; D16: the Owner has every SA action). Reassignment (O4, O5) is P1 and not offered yet.
 */
export type SaActionSlug =
  | 'confirm'
  | 'decline'
  | 'assign-technician'
  | 'edit-estimate'
  | 'send-estimate'
  | 'revise-estimate'
  | 'return-to-technician'
  | 'assign-parts-person'
  | 'notify-ready'
  | 'complete'
  | 'cancel'

export interface SaActionMeta {
  /** Staff label (spec 09 §4.6). */
  label: string
  icon: LucideIcon
  /** The statuses the API lists the action in for an SA or Owner (spec 08 rule table). */
  from: ReadonlyArray<BookingStatus>
  /** Where the button lives: the action bar, or the estimate panel's header (spec 09 §4.6 rule 2). */
  placement: 'bar' | 'estimate'
  /** `decline` and `cancel` come last, after a separator (spec 09 §4.6 rule 3). */
  destructive: boolean
}

export const SA_ACTIONS = {
  confirm: {
    label: 'Confirm booking',
    icon: CalendarCheck,
    from: ['PENDING'],
    placement: 'bar',
    destructive: false,
  },
  'assign-technician': {
    label: 'Assign technician',
    icon: UserCheck,
    from: ['CONFIRMED'],
    placement: 'bar',
    destructive: false,
  },
  'edit-estimate': {
    label: 'Edit estimate',
    icon: PencilLine,
    from: ['ESTIMATE_REVIEW'],
    placement: 'estimate',
    destructive: false,
  },
  'send-estimate': {
    label: 'Send to customer',
    icon: Send,
    from: ['ESTIMATE_REVIEW'],
    placement: 'bar',
    destructive: false,
  },
  'revise-estimate': {
    label: 'Revise estimate',
    icon: FilePen,
    from: ['ESTIMATE_REJECTED'],
    placement: 'bar',
    destructive: false,
  },
  'return-to-technician': {
    label: 'Return to technician',
    icon: Undo2,
    from: ['ESTIMATE_REJECTED'],
    placement: 'bar',
    destructive: false,
  },
  'assign-parts-person': {
    label: 'Assign parts person',
    icon: PackageSearch,
    from: ['ESTIMATE_APPROVED'],
    placement: 'bar',
    destructive: false,
  },
  'notify-ready': {
    label: 'Notify customer',
    icon: BellRing,
    from: ['READY_FOR_PICKUP'],
    placement: 'bar',
    destructive: false,
  },
  complete: {
    label: 'Complete booking',
    icon: CircleCheckBig,
    from: ['READY_FOR_PICKUP'],
    placement: 'bar',
    destructive: false,
  },
  decline: {
    label: 'Decline booking',
    icon: CircleX,
    from: ['PENDING'],
    placement: 'bar',
    destructive: true,
  },
  cancel: {
    label: 'Cancel booking',
    icon: Ban,
    from: CANCELLABLE_STATUSES,
    placement: 'bar',
    destructive: true,
  },
} as const satisfies Record<SaActionSlug, SaActionMeta>

/** The registry order of spec 09 §4.6: bars render their buttons in this order. */
export const SA_ACTION_ORDER = [
  'confirm',
  'assign-technician',
  'edit-estimate',
  'send-estimate',
  'revise-estimate',
  'return-to-technician',
  'assign-parts-person',
  'notify-ready',
  'complete',
  'decline',
  'cancel',
] as const satisfies ReadonlyArray<SaActionSlug>

/**
 * The SA's or Owner's `allowed_actions` for a booking in `status` (spec 08 "`allowed_actions`"):
 * what the API will list once SA-02 reads E-35. Terminal statuses have none, so the page is
 * read-only.
 */
export function saAllowedActions(status: BookingStatus): SaActionSlug[] {
  return SA_ACTION_ORDER.filter((slug) =>
    (SA_ACTIONS[slug].from as ReadonlyArray<BookingStatus>).includes(status),
  )
}

export interface ActionBarPlan {
  /** The one blue button: the first forward action. */
  primary: SaActionSlug | null
  /** Other forward actions, as outline buttons. */
  secondary: SaActionSlug[]
  /** `decline` and `cancel`, last. */
  destructive: SaActionSlug[]
}

/**
 * Spec 09 §4.6 rules 2, 3 and 5: the bar shows its slugs in registry order, the first forward one
 * is the primary, and destructive ones come last. A hint may choose the emphasis (rule 5): once
 * the customer has been told the car is ready, completing the booking is the next step.
 */
export function planActionBar(
  allowed: ReadonlyArray<SaActionSlug>,
  hints: { readyNotified?: boolean } = {},
): ActionBarPlan {
  const bar = allowed.filter((slug) => SA_ACTIONS[slug].placement === 'bar')
  const destructive = bar.filter((slug) => SA_ACTIONS[slug].destructive)
  let forward = bar.filter((slug) => !SA_ACTIONS[slug].destructive)
  if (hints.readyNotified && forward.includes('complete')) {
    forward = ['complete', ...forward.filter((slug) => slug !== 'complete')]
  }
  return { primary: forward[0] ?? null, secondary: forward.slice(1), destructive }
}
