'use client'

import { CircleCheck, EyeOff, TriangleAlert } from 'lucide-react'
import Link from 'next/link'
import { toast } from 'sonner'

import { FormSection } from '@/components/layout/form-section'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Field, FieldContent, FieldDescription, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'
import { saveShop, type MockShop } from '@/lib/mock-data'

export interface ListingSectionProps {
  shop: MockShop
  /** Active services of the shop (D64: a listed shop needs one to be bookable). */
  activeServices: number
  servicesHref: string
  publicHref: string
}

/**
 * O-04 §2 Directory: the `is_listed` switch. It is a single toggle, so it saves as soon as it is
 * switched (DESIGN.md §6.7) and says what customers see now (D64).
 */
export function ListingSection({
  shop,
  activeServices,
  servicesHref,
  publicHref,
}: ListingSectionProps) {
  const toggle = (listed: boolean) => {
    saveShop({ ...shop, is_listed: listed })
    toast.success(
      listed
        ? `${shop.name} is listed in the shop directory`
        : `${shop.name} is hidden from the shop directory`,
    )
  }

  return (
    <FormSection
      title="Directory listing"
      description="Customers find shops on BayFlow's booking page. Your shop shows there once it's listed and has at least one active service."
    >
      <div className="space-y-5">
        <Field orientation="horizontal">
          <FieldContent>
            <FieldLabel htmlFor="shop-listed">List {shop.name} in the directory</FieldLabel>
            <FieldDescription>
              Saved as soon as you switch it. Bookings already made carry on either way.
            </FieldDescription>
          </FieldContent>
          <Switch id="shop-listed" checked={shop.is_listed} onCheckedChange={toggle} />
        </Field>

        {!shop.is_listed ? (
          <Alert role="note">
            <EyeOff aria-hidden="true" />
            <AlertTitle>Hidden from customers</AlertTitle>
            <AlertDescription>
              Your public page and online booking are off until you list the shop again.
            </AlertDescription>
          </Alert>
        ) : activeServices === 0 ? (
          <Alert variant="warning" role="note">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>Listed, but customers can&apos;t book yet</AlertTitle>
            <AlertDescription>
              <p>
                Online booking needs at least one active service.{' '}
                <Link href={servicesHref}>Add or turn on a service</Link>.
              </p>
            </AlertDescription>
          </Alert>
        ) : (
          <Alert variant="success" role="note">
            <CircleCheck aria-hidden="true" />
            <AlertTitle>Customers can find and book you</AlertTitle>
            <AlertDescription>
              <p>
                {activeServices === 1
                  ? '1 active service is'
                  : `${activeServices.toLocaleString('en')} active services are`}{' '}
                bookable online.{' '}
                <Link href={publicHref} target="_blank" rel="noreferrer">
                  View your public page
                  <span className="sr-only"> (opens in a new tab)</span>
                </Link>
              </p>
            </AlertDescription>
          </Alert>
        )}
      </div>
    </FormSection>
  )
}
