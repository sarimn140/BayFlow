import { DEMO_ACCOUNTS, DEMO_PASSWORD, DEMO_SHOP_NAME } from '@/content/demo-accounts'

/**
 * Everything the Help agent knows. It answers only from this list, which is written from the
 * BayFlow product brief and the pages of this site, so it can never wander off-topic or invent
 * features. Add a topic here to teach it something new; no other file needs to change.
 *
 * `keywords` are matched after the same normalising the question gets (lower-case, stop words
 * dropped, plurals and endings trimmed, a few synonyms folded), so plain words are enough. A
 * multi-word keyword counts for more when all its words appear.
 */

export interface HelpLink {
  label: string
  href: string
}

export interface HelpTopic {
  id: string
  title: string
  keywords: ReadonlyArray<string>
  /** Plain text. Blank line = new paragraph; lines starting with "• " are a list; **bold** works. */
  answer: string
  links?: ReadonlyArray<HelpLink>
  /** Questions to offer next, each of which must itself resolve to a topic. */
  followUps?: ReadonlyArray<string>
}

const demoList = DEMO_ACCOUNTS.map((a) => `• **${a.role}**: ${a.email}`).join('\n')

export const HELP_TOPICS: ReadonlyArray<HelpTopic> = [
  {
    id: 'what-is-bayflow',
    title: 'What is BayFlow?',
    keywords: [
      'bayflow',
      'what is bayflow',
      'about',
      'overview',
      'platform',
      'what does it do',
      'multi tenant',
      'auto repair software',
    ],
    answer:
      'BayFlow is a multi-tenant platform for independent auto repair shops. It has three parts that share one backend:\n\n• **Customer portal**: browse workshops, book online, then track the job and approve estimates.\n• **Shop POS**: a role-based dashboard where the Owner, Service Advisor, Technician, QC Inspector and Parts Person each see only their own work.\n• **Backend**: a booking state machine that decides who can move a job to which step.\n\nIt replaces paper job cards, WhatsApp chats and phone calls with one live record of every vehicle.',
    links: [{ label: 'Browse workshops', href: '/book' }],
    followUps: ['How do I book a repair?', 'What are the roles?', 'What problems does BayFlow solve?'],
  },
  {
    id: 'problems-solved',
    title: 'What problems does BayFlow solve?',
    keywords: [
      'problem',
      'solve',
      'benefit',
      'why use',
      'paper job card',
      'visibility',
      'accountability',
      'lost information',
      'whatsapp',
    ],
    answer:
      'Garages usually lose information at every hand-off. BayFlow answers each one:\n\n• **Finding and booking**: a public workshop directory with real slot availability.\n• **Lost information**: the customer’s reported problem, vehicle details and every step stay on one booking.\n• **Disputed estimates**: itemised parts and labour, approved in the app with a timestamp.\n• **Wrong stock**: live inventory per shop; receiving parts updates stock automatically.\n• **Unclear ownership**: every status has exactly one responsible role.\n• **Skipped quality checks**: a mandatory QC stage; a failed check goes back to the technician.\n• **Customer anxiety**: a dashboard with status and notifications instead of “is my car ready?” calls.\n• **Several branches**: each shop has its own team, inventory, slots and bookings.',
    followUps: ['What is the booking lifecycle?', 'How does an owner run many shops?'],
  },
  {
    id: 'how-to-book',
    title: 'How do I book a repair?',
    keywords: [
      'book',
      'booking',
      'make a booking',
      'book a repair',
      'appointment',
      'reserve',
      'how to book',
      'wizard',
      'new booking',
      'schedule a service',
      'appointment for my car',
      'get my car fixed',
      'fix my car',
      'service my car',
    ],
    answer:
      'Booking takes five steps, with no phone call needed:\n\n• **1. Workshop**: pick a shop from the directory.\n• **2. Services**: choose one or more problems or services (oil change, brakes, check engine light, tyre rotation…) and add free-text notes about what you noticed.\n• **3. Date & time**: see that shop’s free slots for a day and pick one.\n• **4. Your details**: your name, email and password, plus the vehicle: registration number, make, model, year, and optionally colour and mileage.\n• **5. Review**: check everything and confirm.\n\nYour booking is created as **Pending** and the shop’s Service Advisor is notified. If your email already has a BayFlow account, it is reused instead of creating a duplicate.',
    links: [{ label: 'Start a booking', href: '/book' }],
    followUps: ['How do I log in as a customer?', 'How do I track my booking?', 'Can I cancel a booking?'],
  },
  {
    id: 'find-shop',
    title: 'Finding a workshop',
    keywords: [
      'find shop',
      'search shop',
      'directory',
      'list of shops',
      'workshop',
      'garage',
      'city',
      'filter',
      'near me',
      'compare shops',
      'rating',
      'opening hours',
    ],
    answer:
      'The workshop directory lists every shop that is taking online bookings. You can search by workshop name, area or street, and filter by city. Each card shows the shop’s photo, city, rating, whether it is open today, a few of its services and a “from” price when the shop lists one.\n\nTap a card to see the full shop page, or press **Book now** to start the booking wizard at that shop.',
    links: [{ label: 'Open the directory', href: '/book' }],
    followUps: ['How do I book a repair?'],
  },
  {
    id: 'services-pricing',
    title: 'Services and prices',
    keywords: [
      'service',
      'services',
      'price',
      'pricing',
      'cost',
      'how much',
      'oil change',
      'brake',
      'check engine',
      'tire',
      'tyre',
      'catalog',
      'fee',
      'charge',
    ],
    answer:
      'Each shop keeps its own service catalogue (name, description, estimated duration and an optional base price). You can pick several services in one booking and describe the problem in your own words.\n\nThe listed price is only a starting point. After the technician inspects your vehicle, you receive an **itemised estimate** (parts and labour) with the total, and nothing proceeds until you approve it. Where a shop sets no base price, the card says “Price after inspection”.',
    followUps: ['How do I approve an estimate?', 'How do I book a repair?'],
  },
  {
    id: 'time-slots',
    title: 'Slots and availability',
    keywords: [
      'slot',
      'time slot',
      'availability',
      'available',
      'date',
      'working hours',
      'double book',
      'capacity',
      'full',
      'reschedule',
      'change time',
      'closed',
    ],
    answer:
      'The slot picker shows only the times that are actually free for the day you choose, based on the shop’s working hours, slot length and how many cars it can take at once. A slot cannot be booked beyond its capacity, so two customers can’t take the same last place.\n\nIf you need a different time, cancel and rebook, or ask the shop’s Service Advisor.',
    followUps: ['Can I cancel a booking?', 'How do I book a repair?'],
  },
  {
    id: 'customer-login',
    title: 'Customer account and login',
    keywords: [
      'customer login',
      'sign in',
      'log in',
      'login',
      'password',
      'account',
      'forgot',
      'email',
      'my account',
      'customer account',
      'sign out',
    ],
    answer:
      'Customers don’t need a separate sign-up. Your account is created when you confirm your first booking, using the email and password you entered in the “Your details” step. To come back, press **Sign in** and use that same email and password.\n\nIf you book again with an email that already exists, the existing account is reused. Staff accounts are different: the shop Owner creates them, nobody can self-register as staff.',
    links: [
      { label: 'Sign in', href: '/login' },
      { label: 'My bookings', href: '/bookings' },
    ],
    followUps: ['How do I track my booking?', 'Are there demo accounts?'],
  },
  {
    id: 'demo-accounts',
    title: 'Demo accounts',
    keywords: [
      'demo',
      'demo account',
      'test account',
      'test login',
      'credentials',
      'try it',
      'sample login',
      'seed',
      'seeded',
      'password for',
    ],
    answer: `You can try every role with the seeded **${DEMO_SHOP_NAME}** team. On the Sign in page, pick an account and the form fills in for you. The shared demo password is **${DEMO_PASSWORD}**.\n\n${demoList}\n\nTo try the full customer journey as a new person, book through the wizard with any fresh email.`,
    links: [{ label: 'Go to Sign in', href: '/login' }],
    followUps: ['What are the roles?', 'What is the booking lifecycle?'],
  },
  {
    id: 'register-owner',
    title: 'Register a shop (Owner)',
    keywords: [
      'register',
      'sign up',
      'signup',
      'create shop',
      'new shop',
      'add shop',
      'open a shop',
      'become owner',
      'owner account',
      'get started',
      'list my garage',
    ],
    answer:
      'Shop owners create an account on the **Register** page, then set up their first shop: name, address, city, phone, working hours and slot duration or capacity (a logo is optional). After that you can add your team, build your service catalogue and start taking bookings.\n\nOne owner account can create more shops later; each one has its own team, services, slots and inventory.',
    links: [{ label: 'Register', href: '/register' }],
    followUps: ['How do I add team members?', 'How does an owner run many shops?'],
  },
  {
    id: 'track-booking',
    title: 'Tracking a booking',
    keywords: [
      'track',
      'status',
      'where is my car',
      'where is my vehicle',
      'car status',
      'my bookings',
      'progress',
      'timeline',
      'update',
      'dashboard',
      'reference',
      'booking reference',
      'follow',
    ],
    answer:
      'Sign in and open **My bookings**. Each booking shows a live status timeline, a short reference you can copy, and highlights anything that needs you, such as “Estimate awaiting your approval”. You also get a notification at the key steps, so there is no need to phone the garage.\n\nWhen the vehicle is ready, the booking shows a ready-for-pick-up message.',
    links: [{ label: 'My bookings', href: '/bookings' }],
    followUps: ['What do the booking statuses mean?', 'How do I approve an estimate?'],
  },
  {
    id: 'estimate-approval',
    title: 'Approving or rejecting an estimate',
    keywords: [
      'estimate',
      'approve estimate',
      'accept',
      'reject',
      'decline',
      'approval',
      'quote',
      'parts and labour',
      'itemised',
      'awaiting customer',
      'agree',
    ],
    answer:
      'After inspecting your vehicle, the technician lists the parts, quantities, costs and labour. The Service Advisor reviews it (and may adjust it), then sends it to you.\n\nSign in, open the booking and you will see the itemised estimate with a total. Press **Accept** to let the work go ahead, or **Reject** if you don’t agree. Your decision is recorded with a timestamp, so there are no later disputes about price.\n\nIf you reject, the Service Advisor is told and can revise the estimate with the technician or cancel the booking.',
    links: [{ label: 'My bookings', href: '/bookings' }],
    followUps: ['What happens after I approve?', 'Can I cancel a booking?'],
  },
  {
    id: 'after-approval',
    title: 'What happens after approval',
    keywords: [
      'after approve',
      'after accepted',
      'next step',
      'then what',
      'parts ordered',
      'waiting for parts',
      'repair start',
      'in repair',
    ],
    answer:
      'Once you approve, the Service Advisor assigns a **Parts Person**. They check stock: if everything is on the shelf the job goes straight to parts-ready, otherwise they raise a purchase order and the job waits in “parts ordered” until the parts arrive (a partial delivery keeps it there).\n\nWhen parts are allocated, the job returns to the same technician for the **repair**, then goes to **quality control**, and finally the Service Advisor tells you it is ready for pick-up.',
    followUps: ['What is the booking lifecycle?', 'How does quality control work?'],
  },
  {
    id: 'cancel-booking',
    title: 'Cancelling a booking',
    keywords: [
      'cancel',
      'cancellation',
      'cancel booking',
      'withdraw',
      'refund',
      'no longer need',
      'call off',
    ],
    answer:
      'A booking can be cancelled by the customer or the Service Advisor **before the repair starts** (before it reaches “In repair”). If parts had already been reserved for it, they are released back to stock.\n\nThe Service Advisor can also decline a pending booking instead of confirming it. I don’t have any information about refunds on this site, so please check with the shop directly.',
    followUps: ['How do I track my booking?'],
  },
  {
    id: 'pickup',
    title: 'Ready for pick-up',
    keywords: [
      'pickup',
      'pick up',
      'ready',
      'collect',
      'complete',
      'completed',
      'finished',
      'collect car',
      'handover',
      'is my car ready',
      'car ready',
    ],
    answer:
      'When quality control passes, the Service Advisor sends you a “Your vehicle is ready for pick-up” notification and the booking page shows a ready-for-pick-up message. Collect the car from the shop and the booking is marked **Completed**.',
    links: [{ label: 'My bookings', href: '/bookings' }],
  },
  {
    id: 'lifecycle',
    title: 'The booking lifecycle',
    keywords: [
      'lifecycle',
      'workflow',
      'booking statuses',
      'state machine',
      'steps',
      'stages',
      'process',
      'how does it work',
      'pending',
      'confirmed',
      'assigned',
      'inspecting',
    ],
    answer:
      'Every booking moves through a fixed set of statuses, and each status has exactly one responsible role:\n\n• **Pending**: Service Advisor confirms or declines.\n• **Confirmed → Assigned**: Service Advisor assigns a technician.\n• **Inspecting**: Technician inspects the vehicle and builds the estimate.\n• **Estimate review**: Service Advisor reviews and sends it.\n• **Awaiting customer**: the customer accepts or rejects.\n• **Estimate approved → Parts pending → Parts ordered → Parts ready**: Service Advisor and Parts Person.\n• **In repair**: Technician does the work.\n• **QC pending → QC in progress**: any QC Inspector tests it.\n• **Ready for pick-up**: Service Advisor tells the customer.\n• **Completed**: the car is collected.\n\nInvalid jumps are rejected by the system, and every change is logged with who, when and why.',
    followUps: ['How does quality control work?', 'What happens if an estimate is rejected?'],
  },
  {
    id: 'estimate-rejected',
    title: 'If an estimate is rejected',
    keywords: [
      'estimate rejected',
      'rejected',
      'too expensive',
      'disagree',
      'revise estimate',
      'new estimate',
      'change estimate',
    ],
    answer:
      'When a customer rejects an estimate, the Service Advisor is notified straight away. They can work with the technician to revise the estimate and send a new one, or cancel the booking. Each edit before sending is counted as a revision, so there is a clear history.',
    followUps: ['How do I approve an estimate?', 'Can I cancel a booking?'],
  },
  {
    id: 'roles',
    title: 'Roles and permissions',
    keywords: [
      'role',
      'roles',
      'permission',
      'who can',
      'access',
      'staff',
      'user types',
      'team roles',
      'responsibilities',
    ],
    answer:
      'BayFlow has six roles, and each only sees the work that is theirs:\n\n• **Customer**: browses shops, books, tracks bookings, approves or rejects estimates, confirms pick-up.\n• **Owner**: registers, creates shops, adds team members, sees everything in their shops.\n• **Service Advisor**: front desk. Confirms bookings, assigns technicians, reviews and sends estimates, assigns the parts person, notifies customers.\n• **Technician**: sees only jobs assigned to them, inspects, adds parts and labour, repairs.\n• **Parts Person**: stock, purchase orders, receiving and allocating parts.\n• **QC Inspector**: picks jobs from the shared QC queue, passes them or raises an issue.\n\nRoles are per shop, so someone can be a Technician in one shop and a Service Advisor in another.',
    followUps: ['What does a Technician see?', 'How does an owner run many shops?'],
  },
  {
    id: 'owner',
    title: 'Owner dashboard',
    keywords: [
      'owner',
      'owner dashboard',
      'overview',
      'owner can',
      'shop owner',
      'manage shop',
      'settings',
      'shop settings',
    ],
    answer:
      'The Owner can do everything inside their own shops: an overview of bookings by status, the team list, an inventory summary, services and settings. Owners can also open any role’s view for support. Staff accounts are created by the Owner, never by self sign-up.',
    links: [{ label: 'Open the POS', href: '/pos' }],
    followUps: ['How do I add team members?', 'How does an owner run many shops?'],
  },
  {
    id: 'service-advisor',
    title: 'Service Advisor view',
    keywords: [
      'service advisor',
      'advisor',
      'front desk',
      'confirm booking',
      'assign technician',
      'send estimate',
      'bookings queue',
      'notify customer',
    ],
    answer:
      'The Service Advisor runs the front desk. Their dashboard has the shop’s bookings list with status filters, where they confirm or decline new bookings, assign a technician, review and edit estimates before sending them to the customer, assign a parts person, notify the customer when the car is ready, and close the booking. A notification bell alerts them to new bookings and customer decisions.',
    followUps: ['What is the booking lifecycle?', 'What does a Technician see?'],
  },
  {
    id: 'technician',
    title: 'Technician view',
    keywords: [
      'technician',
      'mechanic',
      'my jobs',
      'technician view',
      'what technician sees',
      'inspect',
      'inspection',
      'add parts',
      'labour',
      'labor',
      'job card',
      'assigned jobs',
    ],
    answer:
      'A Technician sees only the bookings assigned to them. For each job they can read the booking and vehicle details, inspect the car, add estimate line items (part, quantity, unit cost) plus labour, submit it to the Service Advisor, then later start the repair, send the job to QC, and see any QC issues sent back.',
    followUps: ['How does quality control work?', 'What is the booking lifecycle?'],
  },
  {
    id: 'parts-person',
    title: 'Parts Person view',
    keywords: [
      'parts person',
      'parts',
      'procurement',
      'stock',
      'receive',
      'allocate',
      'missing parts',
      'parts queue',
      'reserved',
    ],
    answer:
      'The Parts Person sees the inventory table (SKU, name, quantity, reorder level, cost) and the jobs waiting for parts, with required versus available quantities. They can create purchase orders for missing parts, mark an order received (stock goes up), and allocate parts to a booking (stock is deducted). Cancelling a booking returns its reserved parts to stock.',
    followUps: ['How do inventory and purchase orders work?'],
  },
  {
    id: 'inventory-po',
    title: 'Inventory and purchase orders',
    keywords: [
      'inventory',
      'purchase order',
      'purchase orders',
      'po',
      'order parts',
      'reorder',
      'sku',
      'received',
      'partially received',
      'supplier',
      'shortage',
    ],
    answer:
      'Each shop keeps its own parts catalogue with quantity on hand. Required parts are compared with stock automatically so shortages show up at estimate time. Purchase orders carry items and a status: **Ordered**, **Partially received** or **Received**.\n\nReceiving increases inventory; allocating parts to a booking decreases it and links them to that job; cancelling returns reserved parts.',
    followUps: ['What does the Parts Person see?'],
  },
  {
    id: 'quality-control',
    title: 'How quality control works',
    keywords: [
      'qc',
      'quality',
      'quality control',
      'inspector',
      'qc queue',
      'qc fail',
      'failed qc',
      'road test',
      'issue',
      'pick a job',
      'sign off',
    ],
    answer:
      'After the repair, the job lands in a **shared QC queue**. Any QC Inspector in that shop can pick it (the first to pick locks it, so two people can’t take the same job). They test the vehicle with a checklist and notes, then either:\n\n• **Pass**: the job becomes ready for pick-up.\n• **Fail**: they raise an issue with a title and description. The job returns to the same technician, who fixes it and resubmits. This can repeat until QC passes.\n\nQC is mandatory, so nothing skips the check.',
    followUps: ['What does a Technician see?', 'What is the booking lifecycle?'],
  },
  {
    id: 'multi-shop',
    title: 'Many shops and data separation',
    keywords: [
      'multiple shops',
      'many shops',
      'owner many shops',
      'owner multiple shops',
      'branch',
      'branches',
      'second shop',
      'shop switcher',
      'switch shop',
      'multi tenant',
      'tenant',
      'isolation',
      'separate data',
      'privacy',
      'security',
      'other shop',
    ],
    answer:
      'One owner account can create and run many shops. Each shop is a separate tenant with its own team, services, slots, inventory and bookings, and a **shop switcher** in the POS header moves between them.\n\nData is separated per shop: a staff member of one shop can never read or change another shop’s data, even by guessing IDs. Customers are global accounts and can book at any shop, but only ever see their own bookings.',
    links: [{ label: 'Open the POS', href: '/pos' }],
    followUps: ['What are the roles?', 'How do I add team members?'],
  },
  {
    id: 'team',
    title: 'Adding team members',
    keywords: [
      'team',
      'add member',
      'add staff',
      'add technician',
      'invite',
      'deactivate',
      'remove staff',
      'employee',
      'second technician',
      'hire',
    ],
    answer:
      'In the POS, open **Team → Add member**, enter their details and choose a role (Service Advisor, Technician, QC Inspector or Parts Person). The new member signs in with the credentials you create. You can also edit a member’s role or deactivate them later. Each shop has its own separate team.',
    links: [{ label: 'Open the POS', href: '/pos' }],
    followUps: ['What are the roles?'],
  },
  {
    id: 'notifications',
    title: 'Notifications',
    keywords: [
      'notification',
      'notifications',
      'bell',
      'alert',
      'unread',
      'notify',
      'email',
      'reminder',
      'reminders',
    ],
    answer:
      'The bell icon in the header shows your unread notifications. People are notified at the key moments:\n\n• New booking created → the shop’s Service Advisors\n• Technician assigned → that technician\n• Estimate submitted → the Service Advisor\n• Estimate sent → the customer\n• Estimate accepted or rejected → the Service Advisor\n• Parts needed or ready → the Parts Person or technician\n• Sent to QC, or QC failed → the QC queue or technician\n• Vehicle ready → the customer',
    followUps: ['How do I track my booking?'],
  },
  {
    id: 'calling',
    title: 'In-app calling',
    keywords: [
      'call',
      'calling',
      'voice',
      'ring',
      'missed call',
      'call log',
      'call advisor',
      'call service advisor',
      'call shop',
      'call customer',
      'phone call',
      'talk to',
      'speak to',
    ],
    answer:
      'On a booking page, the customer and the shop’s Service Advisor can call each other directly from the browser, without sharing phone numbers. An incoming call pops up with accept and decline, and calls move through ringing, connected, ended or missed. Every call is logged against the booking (who, when, how long, outcome). A missed call can hand over to the AI Front Desk.',
    followUps: ['What is the AI Front Desk?'],
  },
  {
    id: 'ai-front-desk',
    title: 'AI Front Desk',
    keywords: [
      'ai',
      'front desk',
      'ai front desk',
      'voice agent',
      'unanswered call',
      'call summary',
      'callback',
    ],
    answer:
      'If a customer calls and no Service Advisor picks up in time, the **AI Front Desk** answers. It greets the caller, identifies them by name, phone, email or booking reference, looks up their booking and answers from real data: current status, appointment time, pending estimate, ready for pick-up. It never invents information; if it can’t answer, it says so and promises a callback.\n\nAfterwards it writes a summary and creates a task for the Service Advisor, such as “Call back Ahmed about the estimate”, shown in the calls section of the SA dashboard.',
    followUps: ['How does in-app calling work?'],
  },
  {
    id: 'worked-example',
    title: 'A worked example',
    keywords: [
      'example',
      'worked example',
      'ahmed',
      'honda civic',
      'lahore auto care',
      'walkthrough',
      'scenario',
      'demo flow',
      'full flow',
    ],
    answer:
      'Ahmed’s 2016 Honda Civic has its check-engine light on. He books at Lahore Auto Care, choosing “Check engine light” and “Oil change”. The Service Advisor confirms and assigns Imran (Technician), who finds a faulty ignition coil and submits an estimate. The advisor adjusts the labour and sends it; Ahmed logs in and approves. Usman (Parts) orders the missing coil, receives it, and allocates the parts. Imran repairs the car and sends it to QC; Sara (QC) finds a minor oil leak and fails it, Imran fixes it, and Sara passes it. Bilal (Service Advisor) tells Ahmed it’s ready, and Ahmed collects the car: **Completed**.',
    followUps: ['What is the booking lifecycle?', 'Are there demo accounts?'],
  },
  {
    id: 'platform-admin',
    title: 'Platform admin',
    keywords: [
      'admin',
      'platform admin',
      'super admin',
      'audit',
      'audit log',
      'suspend',
      'suspended',
      'users directory',
      'all shops',
    ],
    answer:
      'The platform admin console is for BayFlow’s own administrators. It shows platform-wide overview figures, directories of shops, users and bookings, and an audit log of actions. Admins can also suspend a shop. This area isn’t available to customers or shop staff.',
    links: [{ label: 'Admin console', href: '/admin' }],
  },
  {
    id: 'features',
    title: 'Features',
    keywords: [
      'feature',
      'features',
      'capability',
      'packaged services',
      'vehicle inspections',
      'appointment scheduling',
      'service reminders',
      'what can bayflow do',
      'reports',
      'profit',
    ],
    answer:
      'The landing page highlights these capabilities:\n\n• **Workflow**: assign tasks, schedule jobs and track progress in real time.\n• **Estimates**: send professional estimates in seconds and get approvals faster.\n• **Inventory**: know exactly what is in stock, from parts to tyres.\n• **Vehicle inspections**: digital inspection reports customers can see.\n• **Packaged services**: bundle common repairs into packages.\n• **Procurement**: order the right parts on time and manage suppliers.\n• **Appointment scheduling and service reminders**: notifications that prompt action.',
    followUps: ['What is the booking lifecycle?', 'How do inventory and purchase orders work?'],
  },
  {
    id: 'demo-request',
    title: 'Book a demo',
    keywords: [
      'book a demo',
      'request demo',
      'schedule demo',
      'sales',
      'pricing plan',
      'talk to sales',
      'trial',
      'demo call',
    ],
    answer:
      'On the home page, press **Book a Demo** and fill in your name, email, phone, garage name and country. Our team will contact you. For sales questions you can also use **Contact Sales** in the Features menu.',
    links: [{ label: 'Home page', href: '/' }],
  },
  {
    id: 'contact-support',
    title: 'Contact and support',
    keywords: [
      'contact',
      'contact us',
      'help center',
      'customer support',
      'whatsapp',
      'phone number',
      'email support',
      'chat support',
      'speak to human',
      'office hours',
    ],
    answer:
      'You can reach the team from the site footer: call or WhatsApp **+92 312 5699996**, or email the support address listed there. Live chat support runs Monday to Friday, 10 am to 7 pm PKT. For anything about a specific repair, open your booking and call the shop’s Service Advisor from there.',
    links: [{ label: 'Home page', href: '/' }],
  },
  {
    id: 'theme',
    title: 'Dark and light theme',
    keywords: [
      'dark',
      'dark mode',
      'light mode',
      'theme',
      'night mode',
      'colour',
      'color scheme',
      'appearance',
      'switch theme',
    ],
    answer:
      'Use the round **sun / moon button** in the top bar (on every page, including sign in and the POS) to switch between the light and dark themes. The first visit follows your device setting, and BayFlow remembers your choice next time.',
  },
  {
    id: 'mobile',
    title: 'Using BayFlow on a phone',
    keywords: [
      'mobile',
      'phone',
      'responsive',
      'app',
      'android',
      'ios',
      'tablet',
      'small screen',
    ],
    answer:
      'BayFlow is fully responsive, so booking, tracking and approving estimates all work in your phone’s browser. There is no separate app to install.',
  },
  {
    id: 'payments',
    title: 'Payments',
    keywords: [
      'payment',
      'pay',
      'online payment',
      'pay online',
      'invoice',
      'card',
      'credit card',
      'bill',
      'checkout',
      'receipt',
    ],
    answer:
      'This version of BayFlow focuses on itemised estimates and in-app approval. I don’t have any information about online payment or invoices on this site, so please settle payment with the shop when you collect your vehicle.',
    followUps: ['How do I approve an estimate?'],
  },
  {
    id: 'help-agent',
    title: 'What can this assistant do?',
    keywords: [
      'what can you do',
      'help',
      'who are you',
      'your name',
      'assistant',
      'how to use',
      'what can i ask',
      'topics',
    ],
    answer:
      'I’m the BayFlow Help assistant. I can explain how to book a repair, track a job, approve estimates, and how each role (Owner, Service Advisor, Technician, Parts, QC) works in the shop POS, and I can point you to the right page. I only answer questions about this website and its content.',
    followUps: ['How do I book a repair?', 'What are the roles?', 'What is the booking lifecycle?'],
  },
]

/** Topics offered as one-tap questions when the chat opens. */
export const STARTER_QUESTIONS: ReadonlyArray<string> = [
  'How do I book a repair?',
  'How do I approve an estimate?',
  'What are the roles?',
  'Are there demo accounts?',
  'How do I switch to dark mode?',
]

export const WELCOME_TEXT =
  'Hi! I’m the BayFlow Help assistant. Ask me anything about this website: booking a repair, tracking a job, estimates, or how the shop dashboards work.'

export const OFF_TOPIC_TEXT =
  'I can only help with BayFlow and this website, so I can’t answer that one. Try asking about booking, estimates, the shop roles, or your account.'

export const UNKNOWN_TEXT =
  'I couldn’t find that specific detail on this site. Here are some things I can help with:'
