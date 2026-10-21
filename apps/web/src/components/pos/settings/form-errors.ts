/**
 * Field errors appear when a form is submitted (spec 09 §5.4) and then follow the field's current
 * value: a flagged field shows its error while it is still wrong and clears as soon as it is fixed.
 * Errors are worked out from the values on every render, never kept in state, so they can't go
 * stale.
 */
export function shownErrors<F extends string>(
  errors: Partial<Record<F, string>>,
  flagged: ReadonlySet<F>,
): Partial<Record<F, string>> {
  const shown: Partial<Record<F, string>> = {}
  for (const field of flagged) if (errors[field]) shown[field] = errors[field]
  return shown
}

/** The fields of `order` that have an error, in form order (the first one gets focus). */
export function fieldsWithErrors<F extends string>(
  errors: Partial<Record<F, string>>,
  order: ReadonlyArray<F>,
): F[] {
  return order.filter((field) => errors[field])
}
