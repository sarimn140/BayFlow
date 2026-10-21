import { Suspense } from 'react'

import { AiCallsPage } from '@/features/calls/ai-calls-page'

/** B-04 · AI calls & tasks (spec 05 §6.5, §9.6) for the Service Advisor and the Owner. */
export default function CallsPage() {
  return (
    <Suspense>
      <AiCallsPage />
    </Suspense>
  )
}
