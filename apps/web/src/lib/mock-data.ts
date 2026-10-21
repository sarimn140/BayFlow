/**
 * Domain mock data store providing persistent, reactive state across all screens
 * following the specifications in .claude/specs/ (02-data-model, 08-booking-state-machine, 10-screens, 11-seed-data).
 */

import { BookingStatus } from './status'

export interface MockShop {
  id: string
  slug: string
  name: string
  city: string
  address: string
  phone: string
  rating: number | null
  slot_duration_minutes: number
  slot_capacity: number
  timezone: string
  is_listed: boolean
  working_hours: { day: string; hours: string; is_closed?: boolean }[]
}

export interface MockService {
  id: string
  shopId: string
  name: string
  description: string
  estimated_duration_minutes: number
  base_price: number | null
  is_active: boolean
}

export interface MockPart {
  id: string
  shopId: string
  sku: string
  name: string
  category: string
  on_hand: number
  reserved: number
  reorder_level: number
  unit_price: number
}

export interface MockPurchaseOrder {
  id: string
  po_number: string
  shopId: string
  supplier: string
  created_at: string
  status: 'ORDERED' | 'PARTIALLY_RECEIVED' | 'RECEIVED'
  items: { part_sku: string; part_name: string; quantity: number; unit_price: number }[]
  total_amount: number
  /**
   * The job the order was raised for (`order-parts` on PP-02, D43); absent for a general restock
   * (PP-04 "New purchase order").
   */
  bookingId?: string
}

export interface MockTeamMember {
  id: string
  shopId: string
  name: string
  email: string
  role: 'OWNER' | 'SERVICE_ADVISOR' | 'TECHNICIAN' | 'PARTS_PERSON' | 'QC_INSPECTOR'
  is_active: boolean
}

export interface MockEstimateItem {
  id: string
  description: string
  type: 'PART' | 'LABOR'
  quantity: number
  unit_price: number
  total: number
}

export interface MockBooking {
  id: string
  reference: string
  shopId: string
  shopSlug: string
  shopName: string
  customerName: string
  customerPhone: string
  customerEmail: string
  vehicleMake: string
  vehicleModel: string
  vehicleYear: number
  licensePlate: string
  /** W4 optional vehicle fields (spec 10 P-03). */
  vehicleColor?: string
  mileageKm?: number
  services: string[]
  /** "Describe the problem" from the wizard (`customer_notes`, ≤ 2,000 characters). */
  customerNotes?: string
  scheduledDate: string
  scheduledTime: string
  status: BookingStatus
  assignedTechnicianId?: string
  assignedTechnicianName?: string
  assignedPartsPersonId?: string
  qcInspectorId?: string
  qcNotes?: string
  qcPassed?: boolean
  inspectionNotes?: string
  estimateItems: MockEstimateItem[]
  estimateTotal: number
  estimateApproved?: boolean
  paidAmount: number
  createdAt: string
  updatedAt: string
}

export const INITIAL_SHOPS: MockShop[] = [
  {
    id: 'shop-lahore-auto-care',
    slug: 'lahore-auto-care',
    name: 'Lahore Auto Care',
    city: 'Lahore',
    address: 'Plot 12, Main Boulevard, Gulberg III',
    phone: '+92 42 35789011',
    rating: 4.7,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '09:00 - 18:00' },
      { day: 'Tuesday', hours: '09:00 - 18:00' },
      { day: 'Wednesday', hours: '09:00 - 18:00' },
      { day: 'Thursday', hours: '09:00 - 18:00' },
      { day: 'Friday', hours: '09:00 - 18:00' },
      { day: 'Saturday', hours: '09:00 - 18:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ],
  },
  {
    id: 'shop-raza-auto-works',
    slug: 'raza-auto-works',
    name: 'Raza Auto Works',
    city: 'Lahore',
    address: 'Plot 8, Commercial Area, DHA Phase 6',
    phone: '+92 42 35891102',
    rating: null,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '10:00 - 19:00' },
      { day: 'Tuesday', hours: '10:00 - 19:00' },
      { day: 'Wednesday', hours: '10:00 - 19:00' },
      { day: 'Thursday', hours: '10:00 - 19:00' },
      { day: 'Friday', hours: '10:00 - 19:00' },
      { day: 'Saturday', hours: '10:00 - 19:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ],
  },
  {
    id: 'shop-clifton-car-clinic',
    slug: 'clifton-car-clinic',
    name: 'Clifton Car Clinic',
    city: 'Karachi',
    address: 'Shop 3, Block 5, Clifton',
    phone: '+92 21 35832011',
    rating: 4.5,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '10:00 - 19:00' },
      { day: 'Tuesday', hours: '10:00 - 19:00' },
      { day: 'Wednesday', hours: '10:00 - 19:00' },
      { day: 'Thursday', hours: '10:00 - 19:00' },
      { day: 'Friday', hours: '10:00 - 19:00' },
      { day: 'Saturday', hours: '10:00 - 19:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ],
  },
  {
    id: 'shop-margalla-motor-works',
    slug: 'margalla-motor-works',
    name: 'Margalla Motor Works',
    city: 'Islamabad',
    address: 'Plot 21, I-9 Markaz',
    phone: '+92 51 4432010',
    rating: 4.6,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '09:00 - 18:00' },
      { day: 'Tuesday', hours: '09:00 - 18:00' },
      { day: 'Wednesday', hours: '09:00 - 18:00' },
      { day: 'Thursday', hours: '09:00 - 18:00' },
      { day: 'Friday', hours: '09:00 - 18:00' },
      { day: 'Saturday', hours: '09:00 - 18:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ],
  },
  {
    id: 'shop-pindi-auto-garage',
    slug: 'pindi-auto-garage',
    name: 'Pindi Auto Garage',
    city: 'Rawalpindi',
    address: 'Shop 14, Murree Road, Satellite Town',
    phone: '+92 51 4851022',
    rating: 4.2,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '09:00 - 18:00' },
      { day: 'Tuesday', hours: '09:00 - 18:00' },
      { day: 'Wednesday', hours: '09:00 - 18:00' },
      { day: 'Thursday', hours: '09:00 - 18:00' },
      { day: 'Friday', hours: '09:00 - 18:00' },
      { day: 'Saturday', hours: '09:00 - 18:00' },
      { day: 'Sunday', hours: '10:00 - 14:00' },
    ],
  },
  {
    id: 'shop-lyallpur-motors',
    slug: 'lyallpur-motors',
    name: 'Lyallpur Motors',
    city: 'Faisalabad',
    address: 'Plot 5, Susan Road, Madina Town',
    phone: '+92 41 8541201',
    rating: 4.4,
    slot_duration_minutes: 60,
    slot_capacity: 2,
    timezone: 'Asia/Karachi',
    is_listed: true,
    working_hours: [
      { day: 'Monday', hours: '09:00 - 18:00' },
      { day: 'Tuesday', hours: '09:00 - 18:00' },
      { day: 'Wednesday', hours: '09:00 - 18:00' },
      { day: 'Thursday', hours: '09:00 - 18:00' },
      { day: 'Friday', hours: '09:00 - 18:00' },
      { day: 'Saturday', hours: '09:00 - 18:00' },
      { day: 'Sunday', hours: 'Closed', is_closed: true },
    ],
  },
]

const LAHORE_SERVICES: MockService[] = [
  {
    id: 'srv-oil-change',
    shopId: 'shop-lahore-auto-care',
    name: 'Periodic Oil & Filter Service',
    description:
      'Includes full synthetic 5W-30 motor oil change, genuine oil filter replacement, and 24-point safety check.',
    estimated_duration_minutes: 60,
    base_price: 4500,
    is_active: true,
  },
  {
    id: 'srv-brake-pads',
    shopId: 'shop-lahore-auto-care',
    name: 'Front Brake Pads Replacement',
    description:
      'Inspection and replacement of front brake pads, caliper lubrication, and rotor surface inspection.',
    estimated_duration_minutes: 90,
    base_price: 8500,
    is_active: true,
  },
  {
    id: 'srv-computer-scan',
    shopId: 'shop-lahore-auto-care',
    name: 'Computer Diagnostic & OBD Scan',
    description:
      'Full ECU health scan, reading check engine fault codes, sensor live data evaluation and diagnostic report.',
    estimated_duration_minutes: 45,
    base_price: 3000,
    is_active: true,
  },
  {
    id: 'srv-ac-service',
    shopId: 'shop-lahore-auto-care',
    name: 'AC Gas Top-up & Leak Inspection',
    description:
      'Refrigerant pressure check, vacuum leak test, compressor performance evaluation, and evaporator cleaning.',
    estimated_duration_minutes: 60,
    base_price: 6000,
    is_active: true,
  },
  {
    id: 'srv-alignment',
    shopId: 'shop-lahore-auto-care',
    name: 'Wheel Alignment & Balancing',
    description:
      '4-wheel computerized laser alignment and dynamic tire balancing for smooth steering.',
    estimated_duration_minutes: 45,
    base_price: 2500,
    is_active: true,
  },
  {
    id: 'srv-tune-up',
    shopId: 'shop-lahore-auto-care',
    name: 'Engine Tune-Up & Spark Plugs',
    description:
      'Throttle body cleaning, spark plug inspection/replacement, air filter clean, fuel injector treatment.',
    estimated_duration_minutes: 90,
    base_price: 7500,
    is_active: true,
  },
]

/**
 * Spec 11 "Service catalogue" for the other five shops: the same nine services (Raza Auto Works,
 * the newer branch, offers seven), with each shop's starting price. `null` is "Price after
 * inspection"; a missing price means the shop doesn't offer it. Lahore Auto Care keeps the
 * services above, which the mock bookings and the POS screens refer to.
 */
const CATALOGUE_SHOPS = [
  'shop-raza-auto-works',
  'shop-clifton-car-clinic',
  'shop-margalla-motor-works',
  'shop-pindi-auto-garage',
  'shop-lyallpur-motors',
] as const

const CATALOGUE: ReadonlyArray<{
  key: string
  name: string
  description: string
  minutes: number
  /** In CATALOGUE_SHOPS order. */
  prices: ReadonlyArray<number | null | undefined>
}> = [
  {
    key: 'oil-change',
    name: 'Oil change',
    description:
      'Drain and refill engine oil, replace the oil filter, top up fluids. Oil and filter are quoted on the estimate.',
    minutes: 45,
    prices: [1100, 1100, 1150, 950, 900],
  },
  {
    key: 'brake-failure',
    name: 'Brake failure',
    description: 'Diagnose and repair brake problems: pads, discs, fluid, lines and handbrake.',
    minutes: 120,
    prices: [2750, 2750, 2900, 2400, 2250],
  },
  {
    key: 'check-engine-light',
    name: 'Check engine light',
    description: 'OBD-II scan, fault-code reading, sensor checks and a road test.',
    minutes: 60,
    prices: [2200, 2200, 2300, 1900, 1800],
  },
  {
    key: 'tire-rotation',
    name: 'Tire rotation',
    description: 'Rotate tires, set pressures and check tread depth.',
    minutes: 30,
    prices: [900, 900, 900, 750, 700],
  },
  {
    key: 'general-inspection',
    name: 'General inspection',
    description: '40-point check: brakes, suspension, fluids, lights, battery and tires.',
    minutes: 60,
    prices: [1650, 1650, 1750, 1450, 1350],
  },
  {
    key: 'ac-service',
    name: 'AC service',
    description: 'Leak test, gas recharge, cabin filter check and condenser cleaning.',
    minutes: 90,
    prices: [undefined, 4950, 5200, 4300, 4050],
  },
  {
    key: 'battery-replacement',
    name: 'Battery replacement',
    description:
      'Battery and charging-system test; fit a new battery (battery quoted on the estimate).',
    minutes: 30,
    prices: [550, 550, 600, 500, 450],
  },
  {
    key: 'wheel-alignment',
    name: 'Wheel alignment',
    description: 'Computerised four-wheel alignment and steering check.',
    minutes: 45,
    prices: [2200, 2200, 2300, 1900, 1800],
  },
  {
    key: 'suspension-repair',
    name: 'Suspension repair',
    description:
      'Diagnose knocks and vibration; replace links, bushes or shocks. Priced after inspection.',
    minutes: 180,
    prices: [undefined, null, null, null, null],
  },
]

export const INITIAL_SERVICES: MockService[] = [
  ...LAHORE_SERVICES,
  ...CATALOGUE_SHOPS.flatMap((shopId, column) =>
    CATALOGUE.flatMap((service) => {
      const price = service.prices[column]
      if (price === undefined) return []
      return [
        {
          id: `srv-${shopId.slice('shop-'.length)}-${service.key}`,
          shopId,
          name: service.name,
          description: service.description,
          estimated_duration_minutes: service.minutes,
          base_price: price,
          is_active: true,
        },
      ]
    }),
  ),
]

/**
 * Spec 11 "Inventory": every shop has the same 16-part catalogue (SKU, name, unit cost, reorder
 * level); only the quantities differ. Lahore Auto Care keeps its parts below, which its bookings,
 * estimates and the POS screens refer to. The other five shops get the spec's catalogue with their
 * "Other shops — opening quantities" (Raza Auto Works after BF-SEED11 used 1 oil filter and 2
 * engine oils: 8 → 7 and 10 → 8). Nothing is reserved: no open job there holds parts.
 */
const PART_CATALOGUE: ReadonlyArray<{
  sku: string
  name: string
  category: string
  unitCost: number
  reorderLevel: number
  /** On hand, in CATALOGUE_SHOPS order. */
  onHand: readonly [number, number, number, number, number]
}> = [
  {
    sku: 'FLT-OIL-01',
    name: 'Oil filter',
    category: 'Filters',
    unitCost: 900,
    reorderLevel: 3,
    onHand: [7, 12, 10, 6, 9],
  },
  {
    sku: 'OIL-4L-01',
    name: 'Engine oil 4 L',
    category: 'Fluids',
    unitCost: 5200,
    reorderLevel: 3,
    onHand: [8, 9, 12, 5, 7],
  },
  {
    sku: 'IGN-COIL-01',
    name: 'Ignition coil',
    category: 'Ignition',
    unitCost: 6500,
    reorderLevel: 2,
    onHand: [2, 1, 3, 0, 2],
  },
  {
    sku: 'SPK-PLG-IR',
    name: 'Spark plug (iridium)',
    category: 'Ignition',
    unitCost: 1800,
    reorderLevel: 6,
    onHand: [12, 16, 8, 4, 12],
  },
  {
    sku: 'FLT-AIR-01',
    name: 'Air filter',
    category: 'Filters',
    unitCost: 1600,
    reorderLevel: 3,
    onHand: [5, 6, 4, 2, 6],
  },
  {
    sku: 'FLT-CAB-01',
    name: 'Cabin AC filter',
    category: 'Filters',
    unitCost: 1400,
    reorderLevel: 3,
    onHand: [4, 5, 3, 0, 4],
  },
  {
    sku: 'BRK-PAD-F',
    name: 'Front brake pads (set)',
    category: 'Brakes',
    unitCost: 6800,
    reorderLevel: 2,
    onHand: [4, 3, 5, 2, 3],
  },
  {
    sku: 'BRK-DSC-F',
    name: 'Front brake disc',
    category: 'Brakes',
    unitCost: 7500,
    reorderLevel: 2,
    onHand: [2, 4, 2, 0, 2],
  },
  {
    sku: 'BRK-FLD-D4',
    name: 'Brake fluid DOT 4 (1 L)',
    category: 'Fluids',
    unitCost: 1500,
    reorderLevel: 4,
    onHand: [6, 8, 6, 3, 5],
  },
  {
    sku: 'CLT-1L',
    name: 'Coolant (1 L)',
    category: 'Fluids',
    unitCost: 1200,
    reorderLevel: 5,
    onHand: [10, 15, 10, 6, 8],
  },
  {
    sku: 'WPR-PAIR',
    name: 'Wiper blades (pair)',
    category: 'Body',
    unitCost: 2200,
    reorderLevel: 2,
    onHand: [3, 6, 2, 1, 4],
  },
  {
    sku: 'BAT-45AH',
    name: 'Battery 12V 45Ah',
    category: 'Electrical',
    unitCost: 18500,
    reorderLevel: 2,
    onHand: [2, 4, 3, 1, 2],
  },
  {
    sku: 'AC-R134A',
    name: 'AC gas R134a (can)',
    category: 'AC',
    unitCost: 3000,
    reorderLevel: 2,
    onHand: [0, 8, 6, 3, 5],
  },
  {
    sku: 'SUS-STB-LNK',
    name: 'Front stabilizer link',
    category: 'Suspension',
    unitCost: 4500,
    reorderLevel: 2,
    onHand: [4, 4, 4, 2, 4],
  },
  {
    sku: 'TIR-185-65-R15',
    name: 'Tire 185/65 R15',
    category: 'Tires',
    unitCost: 16000,
    reorderLevel: 4,
    onHand: [8, 8, 4, 4, 12],
  },
  {
    sku: 'BLB-H4',
    name: 'Headlight bulb H4',
    category: 'Electrical',
    unitCost: 900,
    reorderLevel: 4,
    onHand: [10, 12, 8, 4, 10],
  },
]

const LAHORE_PARTS: MockPart[] = [
  {
    id: 'part-of-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'OF-TY-01',
    name: 'Oil Filter Cartridge (Toyota/Honda)',
    category: 'Filters',
    on_hand: 10,
    reserved: 0,
    reorder_level: 5,
    unit_price: 1500,
  },
  {
    id: 'part-oil-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'OIL-SYN-4L',
    name: 'Engine Oil 5W-30 Full Synthetic 4L',
    category: 'Fluids',
    on_hand: 8,
    reserved: 0,
    reorder_level: 4,
    unit_price: 6800,
  },
  {
    id: 'part-bp-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'BP-FR-02',
    name: 'Semi-Metallic Front Brake Pads Set',
    category: 'Brakes',
    on_hand: 4,
    reserved: 1,
    reorder_level: 2,
    unit_price: 5500,
  },
  {
    id: 'part-br-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'BR-VENT-01',
    name: 'Vented Brake Rotors Pair (Civic/Corolla)',
    category: 'Brakes',
    on_hand: 2,
    reserved: 0,
    reorder_level: 1,
    unit_price: 12000,
  },
  {
    id: 'part-sp-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'SP-IRID-04',
    name: 'Iridium Spark Plugs Set of 4',
    category: 'Ignition',
    on_hand: 6,
    reserved: 0,
    reorder_level: 3,
    unit_price: 4200,
  },
  {
    id: 'part-af-01',
    shopId: 'shop-lahore-auto-care',
    sku: 'AF-CAB-01',
    name: 'Cabin Air Filter Anti-Bacterial',
    category: 'Filters',
    on_hand: 7,
    reserved: 0,
    reorder_level: 3,
    unit_price: 1800,
  },
]

export const INITIAL_PARTS: MockPart[] = [
  ...LAHORE_PARTS,
  ...CATALOGUE_SHOPS.flatMap((shopId, column) =>
    PART_CATALOGUE.map((part) => ({
      id: `part-${shopId.slice('shop-'.length)}-${part.sku.toLowerCase()}`,
      shopId,
      sku: part.sku,
      name: part.name,
      category: part.category,
      on_hand: part.onHand[column]!,
      reserved: 0,
      reorder_level: part.reorderLevel,
      unit_price: part.unitCost,
    })),
  ),
]

export const INITIAL_PURCHASE_ORDERS: MockPurchaseOrder[] = [
  {
    id: 'po-1001',
    po_number: 'PO-2026-001',
    shopId: 'shop-lahore-auto-care',
    supplier: 'Pak Auto Spares Distributors',
    created_at: '2026-10-05T09:00:00Z',
    status: 'RECEIVED',
    items: [
      { part_sku: 'OF-TY-01', part_name: 'Oil Filter Cartridge', quantity: 15, unit_price: 1200 },
      {
        part_sku: 'BP-FR-02',
        part_name: 'Semi-Metallic Front Brake Pads Set',
        quantity: 6,
        unit_price: 4500,
      },
    ],
    total_amount: 45000,
  },
  {
    id: 'po-1002',
    po_number: 'PO-2026-002',
    shopId: 'shop-lahore-auto-care',
    supplier: 'Atlas Automotive Imports',
    created_at: '2026-10-08T14:30:00Z',
    status: 'ORDERED',
    items: [
      {
        part_sku: 'BR-VENT-01',
        part_name: 'Vented Brake Rotors Pair',
        quantity: 4,
        unit_price: 10500,
      },
      {
        part_sku: 'SP-IRID-04',
        part_name: 'Iridium Spark Plugs Set of 4',
        quantity: 8,
        unit_price: 3600,
      },
    ],
    total_amount: 70800,
  },
]

/** Glossary §2.3 role tags, as used in the seeded staff e-mails. */
const ROLE_TAG: Record<MockTeamMember['role'], string> = {
  OWNER: 'owner',
  SERVICE_ADVISOR: 'sa',
  TECHNICIAN: 'tech',
  QC_INSPECTOR: 'qc',
  PARTS_PERSON: 'parts',
}

/** A seeded shop's team, e-mails `<role-tag>.<shop-slug>@bayflow.test` (spec 11, glossary §14.2). */
function seedTeam(
  shopId: string,
  members: ReadonlyArray<readonly [id: string, name: string, role: MockTeamMember['role']]>,
): MockTeamMember[] {
  const slug = shopId.slice('shop-'.length)
  return members.map(([id, name, role]) => ({
    id,
    shopId,
    name,
    email: `${ROLE_TAG[role]}.${slug}@bayflow.test`,
    role,
    is_active: true,
  }))
}

export const INITIAL_TEAM: MockTeamMember[] = [
  {
    id: 'usr-fatima',
    shopId: 'shop-lahore-auto-care',
    name: 'Fatima Raza',
    email: 'fatima.owner@bayflow.test',
    role: 'OWNER',
    is_active: true,
  },
  {
    id: 'usr-bilal',
    shopId: 'shop-lahore-auto-care',
    name: 'Bilal',
    email: 'bilal.sa@bayflow.test',
    role: 'SERVICE_ADVISOR',
    is_active: true,
  },
  {
    id: 'usr-imran',
    shopId: 'shop-lahore-auto-care',
    name: 'Imran',
    email: 'imran.tech@bayflow.test',
    role: 'TECHNICIAN',
    is_active: true,
  },
  {
    id: 'usr-hamza',
    shopId: 'shop-lahore-auto-care',
    name: 'Hamza',
    email: 'hamza.tech@bayflow.test',
    role: 'TECHNICIAN',
    is_active: true,
  },
  {
    id: 'usr-sara',
    shopId: 'shop-lahore-auto-care',
    name: 'Sara',
    email: 'sara.qc@bayflow.test',
    role: 'QC_INSPECTOR',
    is_active: true,
  },
  {
    id: 'usr-hina',
    shopId: 'shop-lahore-auto-care',
    name: 'Hina',
    email: 'hina.qc@bayflow.test',
    role: 'QC_INSPECTOR',
    is_active: true,
  },
  {
    id: 'usr-usman',
    shopId: 'shop-lahore-auto-care',
    name: 'Usman',
    email: 'usman.parts@bayflow.test',
    role: 'PARTS_PERSON',
    is_active: true,
  },
  {
    // Glossary §14: Fatima also owns Raza Auto Works (shop switcher, O-07 summary).
    id: 'mbr-fatima-raza-auto-works',
    shopId: 'shop-raza-auto-works',
    name: 'Fatima Raza',
    email: 'fatima.owner@bayflow.test',
    role: 'OWNER',
    is_active: true,
  },
  // Spec 11 "Staff and owners": every other shop has its own team, e-mails
  // `<role-tag>.<shop-slug>@bayflow.test` (Raza Auto Works has no `owner.` account: Fatima owns it).
  ...seedTeam('shop-raza-auto-works', [
    ['usr-adeel', 'Adeel Anwar', 'SERVICE_ADVISOR'],
    ['usr-naveed', 'Naveed Akhtar', 'TECHNICIAN'],
    ['usr-rabia', 'Rabia Saeed', 'QC_INSPECTOR'],
    ['usr-faisal', 'Faisal Javed', 'PARTS_PERSON'],
  ]),
  ...seedTeam('shop-clifton-car-clinic', [
    ['usr-owner-clifton', 'Asif Memon', 'OWNER'],
    ['usr-sadia', 'Sadia Qureshi', 'SERVICE_ADVISOR'],
    ['usr-junaid', 'Junaid Baloch', 'TECHNICIAN'],
    ['usr-mehwish', 'Mehwish Siddiqui', 'QC_INSPECTOR'],
    ['usr-rizwan', 'Rizwan Shaikh', 'PARTS_PERSON'],
  ]),
  ...seedTeam('shop-margalla-motor-works', [
    ['usr-owner-margalla', 'Nida Abbasi', 'OWNER'],
    ['usr-waqas', 'Waqas Kiani', 'SERVICE_ADVISOR'],
    ['usr-zubair', 'Zubair Satti', 'TECHNICIAN'],
    ['usr-amna', 'Amna Rehman', 'QC_INSPECTOR'],
    ['usr-fahad', 'Fahad Mirza', 'PARTS_PERSON'],
  ]),
  ...seedTeam('shop-pindi-auto-garage', [
    ['usr-owner-pindi', 'Tariq Mehmood', 'OWNER'],
    ['usr-saima', 'Saima Bashir', 'SERVICE_ADVISOR'],
    ['usr-arshad', 'Arshad Hussain', 'TECHNICIAN'],
    ['usr-kiran', 'Kiran Aslam', 'QC_INSPECTOR'],
    ['usr-shoaib', 'Shoaib Haider', 'PARTS_PERSON'],
  ]),
  ...seedTeam('shop-lyallpur-motors', [
    ['usr-owner-lyallpur', 'Khalid Chaudhry', 'OWNER'],
    ['usr-mariam', 'Mariam Yousaf', 'SERVICE_ADVISOR'],
    ['usr-asad', 'Asad Latif', 'TECHNICIAN'],
    ['usr-huma', 'Huma Zafar', 'QC_INSPECTOR'],
    ['usr-danish', 'Danish Saleem', 'PARTS_PERSON'],
  ]),
]

export const INITIAL_BOOKINGS: MockBooking[] = [
  {
    id: 'bk-001',
    reference: 'BF-2026-001',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    customerName: 'Ayesha Khan',
    customerPhone: '+92 300 9876543',
    customerEmail: 'ayesha.customer@bayflow.test',
    vehicleMake: 'Honda',
    vehicleModel: 'Civic Oriel',
    vehicleYear: 2022,
    licensePlate: 'LEA-22-4589',
    services: ['Periodic Oil & Filter Service', 'Front Brake Pads Replacement'],
    scheduledDate: '2026-10-09',
    scheduledTime: '10:00 am',
    status: 'IN_REPAIR',
    assignedTechnicianId: 'usr-imran',
    assignedTechnicianName: 'Imran',
    inspectionNotes:
      'Brake pads worn to 2mm. Disc rotor surface has minor grooves. Oil level low by 0.5L.',
    estimateItems: [
      {
        id: 'est-1',
        description: 'Periodic Oil & Filter Service (Labor)',
        type: 'LABOR',
        quantity: 1,
        unit_price: 1500,
        total: 1500,
      },
      {
        id: 'est-2',
        description: 'Engine Oil 5W-30 Full Synthetic 4L',
        type: 'PART',
        quantity: 1,
        unit_price: 6800,
        total: 6800,
      },
      {
        id: 'est-3',
        description: 'Oil Filter Cartridge',
        type: 'PART',
        quantity: 1,
        unit_price: 1500,
        total: 1500,
      },
      {
        id: 'est-4',
        description: 'Front Brake Pads Set',
        type: 'PART',
        quantity: 1,
        unit_price: 5500,
        total: 5500,
      },
      {
        id: 'est-5',
        description: 'Brake Pads Installation & Bleeding',
        type: 'LABOR',
        quantity: 1,
        unit_price: 2000,
        total: 2000,
      },
    ],
    estimateTotal: 17300,
    estimateApproved: true,
    paidAmount: 0,
    createdAt: '2026-10-09T04:00:00Z',
    updatedAt: '2026-10-09T05:30:00Z',
  },
  {
    id: 'bk-002',
    reference: 'BF-2026-002',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    // Spec 11 BF-SEED02: the estimate waiting for Ayesha on her first login.
    customerName: 'Ayesha Khan',
    customerPhone: '+92 300 9876543',
    customerEmail: 'ayesha.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Corolla Altis Grande',
    vehicleYear: 2021,
    licensePlate: 'LEE-21-9988',
    services: ['AC Gas Top-up & Leak Inspection', 'Computer Diagnostic & OBD Scan'],
    scheduledDate: '2026-10-09',
    scheduledTime: '11:00 am',
    status: 'AWAITING_CUSTOMER',
    assignedTechnicianId: 'usr-hamza',
    assignedTechnicianName: 'Hamza',
    inspectionNotes:
      'AC condenser has minor dirt blockage. Refrigerant low. Fault code P0134 cleared.',
    estimateItems: [
      {
        id: 'est-6',
        description: 'AC Gas Top-up & Vacuum Test',
        type: 'LABOR',
        quantity: 1,
        unit_price: 6000,
        total: 6000,
      },
      {
        id: 'est-7',
        description: 'Cabin Filter Replacement',
        type: 'PART',
        quantity: 1,
        unit_price: 1800,
        total: 1800,
      },
      {
        id: 'est-8',
        description: 'Computer Diagnostic OBD Scan',
        type: 'LABOR',
        quantity: 1,
        unit_price: 3000,
        total: 3000,
      },
    ],
    estimateTotal: 10800,
    estimateApproved: false,
    paidAmount: 0,
    createdAt: '2026-10-09T05:00:00Z',
    updatedAt: '2026-10-09T06:15:00Z',
  },
  {
    id: 'bk-003',
    reference: 'BF-2026-003',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    // Spec 11 BF-SEED05: Nadia's job waiting in the QC queue.
    customerName: 'Nadia Iqbal',
    customerPhone: '+92 300 0000104',
    customerEmail: 'nadia.customer@bayflow.test',
    vehicleMake: 'Kia',
    vehicleModel: 'Sportage AWD',
    vehicleYear: 2023,
    licensePlate: 'ICT-23-1022',
    services: ['Front Brake Pads Replacement'],
    scheduledDate: '2026-10-08',
    scheduledTime: '02:00 pm',
    status: 'QC_PENDING',
    assignedTechnicianId: 'usr-imran',
    assignedTechnicianName: 'Imran',
    inspectionNotes: 'Repair completed. Test drove vehicle. Brakes bedding in nicely.',
    estimateItems: [
      {
        id: 'est-9',
        description: 'Front Brake Pads Set',
        type: 'PART',
        quantity: 1,
        unit_price: 5500,
        total: 5500,
      },
      {
        id: 'est-10',
        description: 'Installation & Rotor Dressing',
        type: 'LABOR',
        quantity: 1,
        unit_price: 2500,
        total: 2500,
      },
    ],
    estimateTotal: 8000,
    estimateApproved: true,
    paidAmount: 0,
    createdAt: '2026-10-08T09:00:00Z',
    updatedAt: '2026-10-08T15:00:00Z',
  },
  {
    id: 'bk-004',
    reference: 'BF-2026-004',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    // Spec 11 BF-SEED01: Zainab's booking waiting for the Service Advisor.
    customerName: 'Zainab Malik',
    customerPhone: '+92 300 0000103',
    customerEmail: 'zainab.customer@bayflow.test',
    vehicleMake: 'Hyundai',
    vehicleModel: 'Tucson GLS',
    vehicleYear: 2022,
    licensePlate: 'LHE-22-3131',
    services: ['Periodic Oil & Filter Service'],
    scheduledDate: '2026-10-10',
    scheduledTime: '09:00 am',
    status: 'CONFIRMED',
    estimateItems: [],
    estimateTotal: 4500,
    paidAmount: 0,
    createdAt: '2026-10-09T02:00:00Z',
    updatedAt: '2026-10-09T03:00:00Z',
  },
  {
    id: 'bk-005',
    reference: 'BF-2026-005',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    // Spec 11 BF-SEED06: Ayesha's car, ready for pick-up.
    customerName: 'Ayesha Khan',
    customerPhone: '+92 300 9876543',
    customerEmail: 'ayesha.customer@bayflow.test',
    vehicleMake: 'Suzuki',
    vehicleModel: 'Swift GLX',
    vehicleYear: 2020,
    licensePlate: 'LEB-20-8800',
    services: ['Wheel Alignment & Balancing'],
    scheduledDate: '2026-10-08',
    scheduledTime: '10:00 am',
    status: 'READY_FOR_PICKUP',
    assignedTechnicianId: 'usr-hamza',
    assignedTechnicianName: 'Hamza',
    qcInspectorId: 'usr-sara',
    qcPassed: true,
    qcNotes:
      'Laser alignment checked within factory camber/caster tolerance. Tire pressures calibrated to 32 PSI.',
    estimateItems: [
      {
        id: 'est-11',
        description: 'Laser Alignment & 4-Wheel Balancing',
        type: 'LABOR',
        quantity: 1,
        unit_price: 2500,
        total: 2500,
      },
    ],
    estimateTotal: 2500,
    estimateApproved: true,
    paidAmount: 0,
    createdAt: '2026-10-08T04:00:00Z',
    updatedAt: '2026-10-08T12:00:00Z',
  },
  {
    id: 'bk-006',
    reference: 'BF-2026-006',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    customerName: 'Ayesha Khan',
    customerPhone: '+92 300 9876543',
    customerEmail: 'ayesha.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Yaris ATIV',
    vehicleYear: 2021,
    licensePlate: 'LEA-21-1234',
    services: ['Periodic Oil & Filter Service', 'Engine Tune-Up & Spark Plugs'],
    scheduledDate: '2026-10-06',
    scheduledTime: '01:00 pm',
    status: 'COMPLETED',
    assignedTechnicianId: 'usr-imran',
    assignedTechnicianName: 'Imran',
    qcInspectorId: 'usr-sara',
    qcPassed: true,
    qcNotes: 'Spark plugs torqued to spec. Engine runs smoothly. Oil pressure normal.',
    estimateItems: [
      {
        id: 'est-12',
        description: 'Engine Oil 5W-30 Full Synthetic 4L',
        type: 'PART',
        quantity: 1,
        unit_price: 6800,
        total: 6800,
      },
      {
        id: 'est-13',
        description: 'Oil Filter Cartridge',
        type: 'PART',
        quantity: 1,
        unit_price: 1500,
        total: 1500,
      },
      {
        id: 'est-14',
        description: 'Iridium Spark Plugs Set of 4',
        type: 'PART',
        quantity: 1,
        unit_price: 4200,
        total: 4200,
      },
      {
        id: 'est-15',
        description: 'Oil Change & Tune-up Labor',
        type: 'LABOR',
        quantity: 1,
        unit_price: 4000,
        total: 4000,
      },
    ],
    estimateTotal: 16500,
    estimateApproved: true,
    paidAmount: 16500,
    createdAt: '2026-10-06T08:00:00Z',
    updatedAt: '2026-10-06T16:00:00Z',
  },
  {
    // Spec 11 BF-SEED08/09: a cancelled booking in Ayesha's history (declined while pending).
    id: 'bk-007',
    reference: 'BF-2026-007',
    shopId: 'shop-lahore-auto-care',
    shopSlug: 'lahore-auto-care',
    shopName: 'Lahore Auto Care',
    customerName: 'Ayesha Khan',
    customerPhone: '+92 300 9876543',
    customerEmail: 'ayesha.customer@bayflow.test',
    vehicleMake: 'Suzuki',
    vehicleModel: 'Swift GLX',
    vehicleYear: 2020,
    licensePlate: 'LEB-20-8800',
    services: ['Computer Diagnostic & OBD Scan'],
    customerNotes: 'Car won’t start on cold mornings; the battery light flickers.',
    scheduledDate: '2026-10-05',
    scheduledTime: '11:00 am',
    status: 'CANCELLED',
    estimateItems: [],
    estimateTotal: 0,
    paidAmount: 0,
    createdAt: '2026-10-03T04:10:00Z',
    updatedAt: '2026-10-03T05:30:00Z',
  },
  // Spec 11 "Scripts — other shops": each shop's own bookings, so its Service Advisor finds a
  // pending one (Raza Auto Works also a completed one; Lyallpur Motors only a completed one).
  {
    id: 'bk-008',
    reference: 'BF-2026-008',
    shopId: 'shop-raza-auto-works',
    shopSlug: 'raza-auto-works',
    shopName: 'Raza Auto Works',
    customerName: 'Kamran Shah',
    customerPhone: '+92 300 0000102',
    customerEmail: 'kamran.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Hilux Revo',
    vehicleYear: 2020,
    licensePlate: 'LES-8842',
    vehicleColor: 'Black',
    mileageKm: 88000,
    services: ['Oil change', 'General inspection'],
    customerNotes: 'Due for the 90,000 km service.',
    scheduledDate: '2026-10-12',
    scheduledTime: '12:00 pm',
    status: 'PENDING',
    estimateItems: [],
    estimateTotal: 0,
    paidAmount: 0,
    createdAt: '2026-10-09T12:30:00Z',
    updatedAt: '2026-10-09T12:30:00Z',
  },
  {
    id: 'bk-009',
    reference: 'BF-2026-009',
    shopId: 'shop-raza-auto-works',
    shopSlug: 'raza-auto-works',
    shopName: 'Raza Auto Works',
    customerName: 'Kamran Shah',
    customerPhone: '+92 300 0000102',
    customerEmail: 'kamran.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Hilux Revo',
    vehicleYear: 2020,
    licensePlate: 'LES-8842',
    vehicleColor: 'Black',
    mileageKm: 86900,
    services: ['Oil change'],
    scheduledDate: '2026-09-29',
    scheduledTime: '11:00 am',
    status: 'COMPLETED',
    assignedTechnicianId: 'usr-naveed',
    assignedTechnicianName: 'Naveed Akhtar',
    assignedPartsPersonId: 'usr-faisal',
    qcInspectorId: 'usr-rabia',
    qcPassed: true,
    qcNotes: 'Oil level correct, no leaks at the filter or drain plug after a test drive.',
    inspectionNotes: 'Oil dark and below the minimum mark; filter due.',
    estimateItems: [
      {
        id: 'est-16',
        description: 'Oil filter',
        type: 'PART',
        quantity: 1,
        unit_price: 900,
        total: 900,
      },
      {
        id: 'est-17',
        description: 'Engine oil 4 L',
        type: 'PART',
        quantity: 2,
        unit_price: 5200,
        total: 10400,
      },
      {
        id: 'est-18',
        description: 'Oil change',
        type: 'LABOR',
        quantity: 1,
        unit_price: 1100,
        total: 1100,
      },
    ],
    estimateTotal: 12400,
    estimateApproved: true,
    paidAmount: 12400,
    createdAt: '2026-09-28T13:00:00Z',
    updatedAt: '2026-09-29T11:00:00Z',
  },
  {
    id: 'bk-010',
    reference: 'BF-2026-010',
    shopId: 'shop-clifton-car-clinic',
    shopSlug: 'clifton-car-clinic',
    shopName: 'Clifton Car Clinic',
    customerName: 'Omar Farooq',
    customerPhone: '+92 300 0000105',
    customerEmail: 'omar.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Corolla Altis',
    vehicleYear: 2020,
    licensePlate: 'BKR-482',
    vehicleColor: 'Silver',
    mileageKm: 45600,
    services: ['Check engine light'],
    customerNotes: 'Engine light on since the weekend.',
    scheduledDate: '2026-10-12',
    scheduledTime: '03:00 pm',
    status: 'PENDING',
    estimateItems: [],
    estimateTotal: 0,
    paidAmount: 0,
    createdAt: '2026-10-09T16:00:00Z',
    updatedAt: '2026-10-09T16:00:00Z',
  },
  {
    id: 'bk-011',
    reference: 'BF-2026-011',
    shopId: 'shop-margalla-motor-works',
    shopSlug: 'margalla-motor-works',
    shopName: 'Margalla Motor Works',
    customerName: 'Nadia Iqbal',
    customerPhone: '+92 300 0000104',
    customerEmail: 'nadia.customer@bayflow.test',
    vehicleMake: 'Honda',
    vehicleModel: 'BR-V',
    vehicleYear: 2019,
    licensePlate: 'LEK-7731',
    vehicleColor: 'Blue',
    mileageKm: 61000,
    services: ['Brake failure'],
    customerNotes: 'Brake warning light flickers on downhill roads.',
    scheduledDate: '2026-10-14',
    scheduledTime: '11:00 am',
    status: 'PENDING',
    estimateItems: [],
    estimateTotal: 0,
    paidAmount: 0,
    createdAt: '2026-10-09T14:00:00Z',
    updatedAt: '2026-10-09T14:00:00Z',
  },
  {
    id: 'bk-012',
    reference: 'BF-2026-012',
    shopId: 'shop-pindi-auto-garage',
    shopSlug: 'pindi-auto-garage',
    shopName: 'Pindi Auto Garage',
    customerName: 'Omar Farooq',
    customerPhone: '+92 300 0000105',
    customerEmail: 'omar.customer@bayflow.test',
    vehicleMake: 'Suzuki',
    vehicleModel: 'Wagon R',
    vehicleYear: 2019,
    licensePlate: 'BTA-317',
    vehicleColor: 'White',
    mileageKm: 72100,
    services: ['Tire rotation', 'Wheel alignment'],
    customerNotes: 'Car pulls to the right.',
    scheduledDate: '2026-10-12',
    scheduledTime: '12:00 pm',
    status: 'PENDING',
    estimateItems: [],
    estimateTotal: 0,
    paidAmount: 0,
    createdAt: '2026-10-09T13:30:00Z',
    updatedAt: '2026-10-09T13:30:00Z',
  },
  {
    id: 'bk-013',
    reference: 'BF-2026-013',
    shopId: 'shop-lyallpur-motors',
    shopSlug: 'lyallpur-motors',
    shopName: 'Lyallpur Motors',
    customerName: 'Nadia Iqbal',
    customerPhone: '+92 300 0000104',
    customerEmail: 'nadia.customer@bayflow.test',
    vehicleMake: 'Toyota',
    vehicleModel: 'Yaris ATIV',
    vehicleYear: 2021,
    licensePlate: 'LEG-9146',
    vehicleColor: 'Black',
    mileageKm: 35600,
    services: ['Tire rotation'],
    scheduledDate: '2026-09-28',
    scheduledTime: '10:00 am',
    status: 'COMPLETED',
    assignedTechnicianId: 'usr-asad',
    assignedTechnicianName: 'Asad Latif',
    assignedPartsPersonId: 'usr-danish',
    qcInspectorId: 'usr-huma',
    qcPassed: true,
    qcNotes: 'Tires rotated and set to 32 PSI; tread depth fine on all four.',
    inspectionNotes: 'Uneven front wear; rotation due.',
    estimateItems: [
      {
        id: 'est-19',
        description: 'Tire rotation',
        type: 'LABOR',
        quantity: 1,
        unit_price: 700,
        total: 700,
      },
    ],
    estimateTotal: 700,
    estimateApproved: true,
    paidAmount: 700,
    createdAt: '2026-09-26T05:00:00Z',
    updatedAt: '2026-09-28T12:00:00Z',
  },
]

// State Manager supporting browser persistence
//
// `useMockStore` hands these getters to React's useSyncExternalStore, which needs every read to
// return the *same* object or array (Object.is) until the data really changes. A fresh array per
// read makes React re-render forever (error #185). So:
// - a key's parsed data is cached by its raw localStorage string (the seed constant is returned
//   while nothing is stored);
// - derived lists (one shop's services, bookings, …) are cached per source array and argument;
// - writes never mutate a cached array or a seed constant: they store an updated copy, which
//   changes the raw string, so the next read parses once and derived lists are rebuilt once.
// Writes from other tabs arrive through the `storage` event and are picked up the same way.

const parsedByKey = new Map<string, { raw: string; data: unknown }>()
let seedOnlyReads = 0

export function getStoredData<T>(key: string, fallback: T): T {
  if (seedOnlyReads > 0 || typeof window === 'undefined') return fallback
  try {
    const raw = localStorage.getItem(`bf:${key}`)
    if (!raw) return fallback
    const cached = parsedByKey.get(key)
    if (cached && cached.raw === raw) return cached.data as T
    const data = JSON.parse(raw) as T
    parsedByKey.set(key, { raw, data })
    return data
  } catch {
    return fallback
  }
}

/**
 * Runs `read` against the seed data only, ignoring anything stored in this browser. Used as the
 * server snapshot of `useMockStore`: the server has no localStorage, so the first client render
 * must show the same seed data to match the server HTML (no hydration mismatch).
 */
export function readSeedSnapshot<T>(read: () => T): T {
  seedOnlyReads += 1
  try {
    return read()
  } finally {
    seedOnlyReads -= 1
  }
}

const derivedBySource = new WeakMap<object, Map<string, unknown>>()

/** `compute(source)`, memoised per source array and `key`, so repeated reads share one result. */
function derive<S extends object, R>(source: S, key: string, compute: (source: S) => R): R {
  let byKey = derivedBySource.get(source)
  if (!byKey) {
    byKey = new Map()
    derivedBySource.set(source, byKey)
  }
  if (!byKey.has(key)) byKey.set(key, compute(source))
  return byKey.get(key) as R
}

export function setStoredData<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(`bf:${key}`, JSON.stringify(value))
    window.dispatchEvent(new CustomEvent('bf:store-update', { detail: { key } }))
  } catch {
    // ignore
  }
}

// Data Accessors & Operations
export function getShops(): MockShop[] {
  return getStoredData('shops', INITIAL_SHOPS)
}

export function getShopBySlug(slug: string): MockShop | undefined {
  const shops = getShops()
  return shops.find((s) => s.slug === slug || s.id === slug)
}

export function getShopById(id: string): MockShop | undefined {
  const shops = getShops()
  return shops.find((s) => s.id === id || s.slug === id)
}

export function saveShop(updated: MockShop): void {
  const shops = [...getShops()]
  const idx = shops.findIndex((s) => s.id === updated.id)
  if (idx >= 0) {
    shops[idx] = updated
  } else {
    shops.push(updated)
  }
  setStoredData('shops', shops)
}

export function getServices(shopId?: string): MockService[] {
  const services = getStoredData('services', INITIAL_SERVICES)
  if (shopId) {
    return derive(services, `shop:${shopId}`, (all) => all.filter((s) => s.shopId === shopId))
  }
  return services
}

export function saveService(service: MockService): void {
  const services = [...getServices()]
  const idx = services.findIndex((s) => s.id === service.id)
  if (idx >= 0) {
    services[idx] = service
  } else {
    services.push(service)
  }
  setStoredData('services', services)
}

export function getBookings(shopId?: string): MockBooking[] {
  const bookings = getStoredData('bookings', INITIAL_BOOKINGS)
  if (shopId) {
    return derive(bookings, `shop:${shopId}`, (all) =>
      all.filter((b) => b.shopId === shopId || b.shopSlug === shopId),
    )
  }
  return bookings
}

export function getBookingById(id: string): MockBooking | undefined {
  const bookings = getBookings()
  return bookings.find((b) => b.id === id || b.reference === id)
}

/** E-mail addresses identify accounts case-insensitively (spec 02: stored lower-case). */
export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase()
}

/** Whether `email` is the account the booking belongs to: its customer (D21). */
export function isBookingCustomer(
  booking: Pick<MockBooking, 'customerEmail'>,
  email: string,
): boolean {
  const viewer = normaliseEmail(email)
  return viewer !== '' && normaliseEmail(booking.customerEmail) === viewer
}

/**
 * E-11 `GET /api/v1/me/bookings`: only the bookings whose customer is `email`, whatever shop
 * they are at (D21 "customer: own bookings"). Staff see only bookings they made as customers.
 */
export function getCustomerBookings(email: string): MockBooking[] {
  const viewer = normaliseEmail(email)
  return derive(getBookings(), `customer:${viewer}`, (all) =>
    all.filter((b) => isBookingCustomer(b, viewer)),
  )
}

/**
 * E-12 `GET /api/v1/me/bookings/{id}`: the booking only when `email` is its customer. Anyone
 * else gets nothing, exactly like an unknown id (404, D20/D21), so a URL never reveals that
 * someone else's booking exists.
 */
export function getCustomerBooking(id: string, email: string): MockBooking | undefined {
  const booking = getBookingById(id)
  return booking && isBookingCustomer(booking, email) ? booking : undefined
}

export function saveBooking(booking: MockBooking): void {
  const bookings = [...getBookings()]
  const idx = bookings.findIndex((b) => b.id === booking.id)
  booking.updatedAt = new Date().toISOString()
  if (idx >= 0) {
    bookings[idx] = booking
  } else {
    bookings.unshift(booking)
  }
  setStoredData('bookings', bookings)
}

/**
 * The parts of one shop (D20: a shop never sees, or borrows, another shop's records; a new shop
 * starts with none), or of every shop when `shopId` is left out.
 */
export function getInventory(shopId?: string): MockPart[] {
  const parts = getStoredData('inventory', INITIAL_PARTS)
  if (shopId) {
    return derive(parts, `shop:${shopId}`, (all) => all.filter((p) => p.shopId === shopId))
  }
  return parts
}

/**
 * Index of the part a key names: its id, or else its SKU. A SKU is unique only inside a shop
 * (`uq_parts_shop_id_sku`, spec 02) and the seeded shops share one catalogue, so a SKU is matched
 * inside `shopId`, or — without a shop — only when exactly one part in the store carries it.
 * Never a part of another shop.
 */
function partIndex(parts: ReadonlyArray<MockPart>, key: string, shopId?: string): number {
  const byId = parts.findIndex((p) => p.id === key)
  if (byId >= 0) return byId
  const bySku = parts.flatMap((p, index) =>
    p.sku === key && (shopId === undefined || p.shopId === shopId) ? [index] : [],
  )
  return bySku.length === 1 ? bySku[0]! : -1
}

/** Creates or updates a part: the same id, or the same SKU in the same shop, is replaced. */
export function savePart(part: MockPart): void {
  const parts = [...getInventory()]
  const byId = parts.findIndex((p) => p.id === part.id)
  const idx =
    byId >= 0 ? byId : parts.findIndex((p) => p.shopId === part.shopId && p.sku === part.sku)
  if (idx >= 0) {
    parts[idx] = part
  } else {
    parts.push(part)
  }
  setStoredData('inventory', parts)
}

/**
 * Adds `quantityDelta` to a part's stock (never below 0). `partId` is the part's id or its SKU;
 * pass `shopId` with a SKU (a purchase order's line) so only that shop's part can change.
 */
export function adjustPartStock(
  partId: string,
  quantityDelta: number,
  shopId?: string,
): MockPart | undefined {
  const parts = [...getInventory()]
  const idx = partIndex(parts, partId, shopId)
  const current = parts[idx]
  if (!current) return undefined
  // A new object: the current one may be part of a snapshot React is still showing.
  const part = { ...current, on_hand: Math.max(0, current.on_hand + quantityDelta) }
  parts[idx] = part
  setStoredData('inventory', parts)
  return part
}

/** One shop's purchase orders (never another shop's), or every shop's without `shopId`. */
export function getPurchaseOrders(shopId?: string): MockPurchaseOrder[] {
  const pos = getStoredData('purchase_orders', INITIAL_PURCHASE_ORDERS)
  if (shopId) {
    return derive(pos, `shop:${shopId}`, (all) => all.filter((p) => p.shopId === shopId))
  }
  return pos
}

/** Creates or updates an order: the same id, or the same number in the same shop, is replaced. */
export function savePurchaseOrder(po: MockPurchaseOrder): void {
  const pos = [...getPurchaseOrders()]
  const byId = pos.findIndex((p) => p.id === po.id)
  const idx =
    byId >= 0 ? byId : pos.findIndex((p) => p.shopId === po.shopId && p.po_number === po.po_number)
  if (idx >= 0) {
    pos[idx] = po
  } else {
    pos.unshift(po)
  }
  setStoredData('purchase_orders', pos)
}

/**
 * One shop's memberships (D20: a shop with no members of its own has none; it never borrows
 * another shop's team), or every membership without `shopId`.
 */
export function getTeamMembers(shopId?: string): MockTeamMember[] {
  const team = getStoredData('team', INITIAL_TEAM)
  if (shopId) {
    return derive(team, `shop:${shopId}`, (all) => all.filter((t) => t.shopId === shopId))
  }
  return team
}

export function saveTeamMember(member: MockTeamMember): void {
  const team = [...getTeamMembers()]
  const idx = team.findIndex((t) => t.id === member.id)
  if (idx >= 0) {
    team[idx] = member
  } else {
    team.push(member)
  }
  setStoredData('team', team)
}

export interface CurrentUserSession {
  name: string
  email: string
  /** The role in the current shop, `CUSTOMER`, or `PLATFORM_ADMIN` for a BayFlow operator (D94). */
  role:
    | 'OWNER'
    | 'SERVICE_ADVISOR'
    | 'TECHNICIAN'
    | 'PARTS_PERSON'
    | 'QC_INSPECTOR'
    | 'CUSTOMER'
    | 'PLATFORM_ADMIN'
  shopId: string
  shopName: string
}

export const DEFAULT_USER: CurrentUserSession = {
  name: 'Fatima Raza',
  email: 'fatima.owner@bayflow.test',
  role: 'OWNER',
  shopId: 'shop-lahore-auto-care',
  shopName: 'Lahore Auto Care',
}

export function getCurrentUser(): CurrentUserSession {
  return getStoredData('current_user', DEFAULT_USER)
}

export function setCurrentUser(user: CurrentUserSession): void {
  setStoredData('current_user', user)
  if (typeof document !== 'undefined') {
    document.cookie = `bf_session=active_${Date.now()}; path=/; max-age=86400`
    // Readable sign-in flag for the header, also when the API's httpOnly `bf_session` is set.
    document.cookie = `bf_signed_in=1; path=/; max-age=86400; SameSite=Lax`
  }
}

/**
 * Saves a wizard booking. `startSession` stands in for D32: an anonymous booking signs the new
 * customer in; a signed-in user books as themselves and keeps their session.
 */
export function createBookingRecord(
  data: Omit<MockBooking, 'id' | 'reference' | 'createdAt' | 'updatedAt'>,
  { startSession }: { startSession: boolean },
): MockBooking {
  const randNum = Math.floor(100 + Math.random() * 900)
  const id = `bk-${Date.now()}`
  const reference = `BF-2026-${randNum}`

  const newBooking: MockBooking = {
    ...data,
    id,
    reference,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }

  saveBooking(newBooking)
  if (!startSession) return newBooking
  // A customer has no membership: booking at a shop gives no access to its POS (D20).
  setCurrentUser({
    name: data.customerName,
    email: normaliseEmail(data.customerEmail),
    role: 'CUSTOMER',
    shopId: '',
    shopName: '',
  })

  return newBooking
}
