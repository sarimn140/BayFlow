'use client'

import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'

/** The `BookingReference` copy button (spec 09 §4.3): "Reference copied" on success. */
export function CopyReferenceButton({ reference }: { reference: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(reference)
      setCopied(true)
      toast.success('Reference copied')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(`Couldn't copy. Select ${reference} and copy it instead.`)
    }
  }

  return (
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
  )
}
