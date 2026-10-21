import {
  CarBattery,
  CircleDot,
  ClipboardCheck,
  Disc3,
  Droplets,
  Gauge,
  Snowflake,
  Wrench,
  Zap,
} from 'lucide-react'
import { describe, expect, it } from 'vitest'

import { serviceIcon } from './service-icon'

describe('serviceIcon', () => {
  it('gives every spec 11 service a fitting icon', () => {
    expect(serviceIcon('Oil change')).toBe(Droplets)
    expect(serviceIcon('Brake failure')).toBe(CircleDot)
    expect(serviceIcon('Check engine light')).toBe(Gauge)
    expect(serviceIcon('Tire rotation')).toBe(Disc3)
    expect(serviceIcon('General inspection')).toBe(ClipboardCheck)
    expect(serviceIcon('AC service')).toBe(Snowflake)
    expect(serviceIcon('Battery replacement')).toBe(CarBattery)
    expect(serviceIcon('Wheel alignment')).toBe(Disc3)
    expect(serviceIcon('Suspension repair')).toBe(Wrench)
  })

  it('keeps the specific rule ahead of the broad one', () => {
    expect(serviceIcon('AC Gas Top-up & Leak Inspection')).toBe(Snowflake)
    expect(serviceIcon('Computer Diagnostic & OBD Scan')).toBe(Gauge)
    expect(serviceIcon('Engine Tune-Up & Spark Plugs')).toBe(Zap)
    expect(serviceIcon('Front Brake Pads Replacement')).toBe(CircleDot)
    expect(serviceIcon('Periodic Oil & Filter Service')).toBe(Droplets)
    expect(serviceIcon('Wheel Alignment & Balancing')).toBe(Disc3)
  })
})
