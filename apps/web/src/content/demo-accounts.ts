/**
 * Demo accounts shown on the login page (D52, glossary §14, spec 09 §4.12). Picking one only
 * fills the login form; they are never used to log in automatically or to bypass auth.
 */

export const DEMO_PASSWORD = 'BayFlow@2026'

export const DEMO_SHOP_NAME = 'Lahore Auto Care'

export interface DemoAccount {
  role: string
  name: string
  email: string
  note?: string
}

/** Glossary §14.1: the Lahore Auto Care team and the seeded customer Ayesha. */
export const DEMO_ACCOUNTS: ReadonlyArray<DemoAccount> = [
  {
    role: 'Owner',
    name: 'Fatima Raza',
    email: 'fatima.owner@bayflow.test',
    note: 'also owns Raza Auto Works (shop switcher)',
  },
  { role: 'Service Advisor', name: 'Bilal', email: 'bilal.sa@bayflow.test' },
  { role: 'Technician', name: 'Imran', email: 'imran.tech@bayflow.test' },
  {
    role: 'Technician',
    name: 'Hamza',
    email: 'hamza.tech@bayflow.test',
    note: 'second technician',
  },
  { role: 'QC Inspector', name: 'Sara', email: 'sara.qc@bayflow.test' },
  { role: 'QC Inspector', name: 'Hina', email: 'hina.qc@bayflow.test', note: 'second inspector' },
  { role: 'Parts Person', name: 'Usman', email: 'usman.parts@bayflow.test' },
  {
    role: 'Platform Admin',
    name: 'Areeba Hashmi',
    email: 'admin@bayflow.test',
    note: 'BayFlow super admin console',
  },
  {
    role: 'Customer',
    name: 'Ayesha Khan',
    email: 'ayesha.customer@bayflow.test',
    note: 'has sample bookings',
  },
]

export const DEMO_AHMED_NOTE =
  "Ahmed (the worked example) isn't seeded — book through the wizard with any new e-mail, e.g. a fresh .test address."
