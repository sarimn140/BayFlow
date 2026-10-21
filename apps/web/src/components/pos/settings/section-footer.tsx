import { Button } from '@/components/ui/button'

export interface SectionFooterProps {
  /** The section's name for screen readers, e.g. "the shop profile". */
  name: string
  dirty: boolean
  onDiscard: () => void
}

/**
 * A settings section's footer (DESIGN.md `FormSection`): "Unsaved changes" and Discard while the
 * form differs from what is saved, then the section's Save pill (a submit button).
 */
export function SectionFooter({ name, dirty, onDiscard }: SectionFooterProps) {
  return (
    <>
      {dirty ? (
        <p className="mr-auto flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="size-2 shrink-0 rounded-full bg-cta" aria-hidden="true" />
          Unsaved changes
        </p>
      ) : null}
      {dirty ? (
        <Button type="button" variant="ghost" onClick={onDiscard}>
          Discard<span className="sr-only"> changes to {name}</span>
        </Button>
      ) : null}
      <Button type="submit">
        Save changes<span className="sr-only"> to {name}</span>
      </Button>
    </>
  )
}
