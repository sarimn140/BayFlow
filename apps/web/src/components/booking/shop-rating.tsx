import { Star } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * A shop's rating, "★ 4.7" (spec 10 P-01/P-02). The star is decoration in the text colour; screen
 * readers hear "4.7 out of 5". Shops without a rating show "New" instead (D56), which the caller
 * renders, since its look depends on where it sits.
 */
export function RatingValue({ rating, className }: { rating: number; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 tabular-nums', className)}>
      <Star className="size-3.5 shrink-0 fill-current" aria-hidden />
      {rating.toFixed(1)}
      <span className="sr-only"> out of 5</span>
    </span>
  )
}
