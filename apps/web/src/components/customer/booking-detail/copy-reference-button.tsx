'use client'

import { Check, Copy } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

/**
 * The copy button of `BookingReference` (spec 09 §4.3). A tooltip names it on hover and confirms
 * the copy for 2 s (also on touch, where tooltips don't open on their own); a status region
 * announces it.
 */
export function CopyReferenceButton({ reference }: { reference: string }) {
  const [copied, setCopied] = useState(false)
  const [hovered, setHovered] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(reference)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <Tooltip open={copied || hovered} onOpenChange={setHovered}>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={copy}
            aria-label={`Copy booking reference ${reference}`}
            className="text-muted-foreground hover:text-foreground"
          >
            {copied ? (
              <Check className="text-success-ink" aria-hidden="true" />
            ) : (
              <Copy aria-hidden="true" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copied ? 'Copied' : 'Copy reference'}</TooltipContent>
      </Tooltip>
      <span role="status" className="sr-only">
        {copied ? `Booking reference ${reference} copied` : ''}
      </span>
    </>
  )
}
