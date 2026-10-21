/**
 * Cover photos for shop cards, the shop page and the booking summary. The API has no shop photo
 * yet (E-08 carries `logo_url` only), so a shop gets one of these by slug: the six seeded shops
 * have a fixed pick and any other shop gets a stable one from the same set.
 *
 * Every cover is an original BayFlow illustration (soft-UI style, drawn in code), so there is
 * nothing to license or credit. `source` names the artwork's role.
 */

export interface ShopPhoto {
  src: string
  /** Width and height of the file, so `next/image` reserves the space (no layout shift). */
  width: number
  height: number
  alt: string
  source: string
}

const PHOTOS = {
  engineBay: {
    src: '/shops/engine-bay.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of an engine block with four cylinder caps, belt pulleys and a battery',
    source: 'bayflow-illustration',
  },
  brakeService: {
    src: '/shops/brake-service.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of a drilled brake disc with an orange caliper and a pad-thickness readout',
    source: 'bayflow-illustration',
  },
  diagnostics: {
    src: '/shops/diagnostics.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of a diagnostics screen showing a live engine waveform and trouble code',
    source: 'bayflow-illustration',
  },
  engineInspection: {
    src: '/shops/engine-inspection.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of a magnifying glass over meshing gears with an inspection report badge',
    source: 'bayflow-illustration',
  },
  underLift: {
    src: '/shops/under-lift.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of a car raised on a two-post lift for an under-body inspection',
    source: 'bayflow-illustration',
  },
  drivetrain: {
    src: '/shops/drivetrain.webp',
    width: 1600,
    height: 1064,
    alt: 'Illustration of a drivetrain shaft with blue and orange gears and a wheel',
    source: 'bayflow-illustration',
  },
} satisfies Record<string, ShopPhoto>

export const SHOP_PHOTOS: ReadonlyArray<ShopPhoto> = Object.values(PHOTOS)

/** The seeded shops (spec 11) each get a photo that suits them. */
const BY_SLUG: Record<string, ShopPhoto> = {
  'lahore-auto-care': PHOTOS.engineBay,
  'raza-auto-works': PHOTOS.brakeService,
  'clifton-car-clinic': PHOTOS.diagnostics,
  'margalla-motor-works': PHOTOS.engineInspection,
  'pindi-auto-garage': PHOTOS.underLift,
  'lyallpur-motors': PHOTOS.drivetrain,
}

/** A shop's cover photo: its own pick, or a stable one chosen from its slug. */
export function shopPhoto(slug: string): ShopPhoto {
  const own = BY_SLUG[slug]
  if (own) return own
  let hash = 0
  for (const char of slug) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return SHOP_PHOTOS[hash % SHOP_PHOTOS.length]!
}
