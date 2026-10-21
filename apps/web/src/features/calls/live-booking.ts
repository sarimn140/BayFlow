/**
 * The bridge between the mock screens (D102) and the real calls API.
 *
 * Calls are real: they need the API's own booking and shop ids. Until the screens are wired to
 * the API, a mock booking reaches its seeded twin (spec 11) through this table, taken from the
 * mock data's own "Spec 11 BF-SEEDnn" notes and, where a note is missing, the same customer at
 * the same shop. A reference already in the API's format (`BF-XXXXXX`) is used as it is, so the
 * table becomes a no-op once the pages show real bookings.
 */
const SEED_TWIN: Readonly<Record<string, string>> = {
  'BF-2026-001': 'BF-SEED07', // Ayesha · Lahore Auto Care
  'BF-2026-002': 'BF-SEED02', // Ayesha · estimate awaiting approval
  'BF-2026-003': 'BF-SEED05', // Nadia · QC pending
  'BF-2026-004': 'BF-SEED01', // Zainab · pending
  'BF-2026-005': 'BF-SEED06', // Ayesha · ready for pick-up
  'BF-2026-006': 'BF-SEED08', // Ayesha · cancelled
  'BF-2026-007': 'BF-SEED08', // Ayesha · cancelled
  'BF-2026-008': 'BF-SEED10', // Kamran · Raza Auto Works, pending
  'BF-2026-009': 'BF-SEED11', // Kamran · Raza Auto Works, completed
  'BF-2026-010': 'BF-SEED12', // Omar · Clifton Car Clinic
  'BF-2026-011': 'BF-SEED13', // Nadia · Margalla Motor Works
  'BF-2026-012': 'BF-SEED14', // Omar · Pindi Auto Garage
  'BF-2026-013': 'BF-SEED15', // Nadia · Lyallpur Motors
}

const API_REFERENCE = /^BF-[0-9A-HJKMNP-TV-Z]{6}$/

/** The API's reference for a booking shown on screen, or null when it has no live twin. */
export function liveReference(reference: string): string | null {
  if (API_REFERENCE.test(reference)) return reference
  return SEED_TWIN[reference] ?? null
}
