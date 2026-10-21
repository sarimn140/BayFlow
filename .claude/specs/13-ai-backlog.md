# 13 — AI Backlog (post-hackathon)

**Status:** Draft
**Priority:** P3, post-hackathon (D4, D36, D59).

> **Nothing in this spec is built during the hackathon except AI-09, the AI Front Desk.** AI-09 is the brief's own bonus feature (brief §8.2). It is decided separately by D58, specified in [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md) and built at priority P2 (roadmap phase PH9, after PH8's in-app calling), only after the core works end to end on the live URL (D36). It is listed here for completeness and as the pattern the other features reuse. Every other feature here is P3 and must not start before the hackathon submission. D4: "The AI backlog (spec 13) is post-hackathon". D59 keeps the backlog out of hackathon scope; AI-09 is the one exception, because D58 decides it.

## Purpose

This spec records the AI features that could make BayFlow more useful after the hackathon. That way the ideas are not lost, and the hackathon architecture keeps the right doors open, without any of them slipping into hackathon scope.

For each feature it records:

- what the feature does;
- what kind of AI it uses;
- which BayFlow tables it needs;
- rough effort and value;
- a suggested phase;
- where we checked, who already sells something similar.

References: "brief §n" is a section of the hackathon brief; "glossary §n" is spec 18; "Dn" is a decision in spec 17; "[Sn]" is a source in §5; "#n" is short for backlog ID AI-nn (#9 = AI-09). `AI-xx` is the backlog's ID prefix (D75); spec 05's AI Front Desk tests use `FD-xx`, so the two never collide.

---

## 1. Principles

1. **AI suggests; humans decide anything involving money or status.**
   - AI may draft estimate lines, messages, purchase orders, prices or checklists. A person in the right role reviews and approves every draft.
   - Booking status changes only through the state machine (spec 08), made by the role that owns the step. The `SYSTEM` actor never performs a core transition (glossary §2.2).
   - Estimates are still accepted only by the customer, in the app, with a timestamp (brief §3).
   - AI output is stored marked as AI-generated, so it can be audited (#41) and measured.
2. **AI tools read data only through the same permission checks as people.** Every AI feature acts as a restricted principal, one of:
   - the customer, who sees only their own bookings;
   - a staff member, who sees what their role may see in their shop (D21);
   - the owner, who sees only their own shops.

   Data is reached through the service layer, or through scoped internal endpoints like the AI Front Desk's (spec 05 §5.1). An LLM never writes SQL, and nothing crosses tenants (D20).
3. **There are two kinds of feature.**
   - **Language, voice and vision** features work from day one: they need a model and the current record, not history.
   - **Prediction** features need months of real, clean data and a baseline to beat. Start with simple rules and statistics. Move to learned models only when each shop has enough history; the threshold is an open question in §6. Until then, present predictions as insights, not decisions. Numbers are computed in SQL; the LLM only writes the words.
4. **Privacy.**
   - Send a model only what the task needs, and mask personal data (phone, e-mail, CNIC, number plate) when the task does not need it.
   - Announce, and get consent for, call recording and transcription.
   - Set retention limits for transcripts and photos.
   - Prefer providers that do not train on API data; the OpenAI API does not by default [S1]. Never send real customer data to free tiers that use it to improve products, such as the Gemini free tier [S2].
   - List the data processors for shop owners.
5. **Cost control.**
   - Use the smallest model that passes the feature's evaluation; cache results; batch reports.
   - Give each shop a monthly AI budget and each feature a cap, enforced as hard limits in the style of spec 05 §11.3.
   - Keep one global switch (`LLM_API_KEY` blank means all AI is off, glossary §12) plus a flag per feature.
   - Show AI usage to owners.
6. **Evaluate before launch.** Each feature gets:
   - a golden test set of inputs with the expected outputs or behaviour;
   - automatic checks that fail on invented data or on another customer's data (#43);
   - human review of a sample;
   - a tracked acceptance rate: how often staff accept, edit or reject suggestions;
   - regression runs whenever a prompt or model changes.

---

## 2. The backlog

**How to read the columns**

| Column | Values |
|---|---|
| **Kind** | Language, Voice, Vision, Prediction or Safety; some features combine two |
| **Effort** | One developer, including evaluation: **S** up to 1 week, **M** 1–3 weeks, **L** more than 3 weeks |
| **Value** | **H**, **M** or **L**: the impact on shop time, revenue or customer trust |

**Phases**

| Phase | When | What goes in it |
|---|---|---|
| **Hackathon** | Now | Only AI-09 (priority P2, roadmap phase PH9, spec 05) |
| **F (Foundations)** | Before or alongside A | The safety features every other AI feature relies on |
| **A (Assist)** | 0–3 months after the hackathon | Language and voice help inside existing screens; works from day one |
| **B (Channels & vision)** | 3–6 months | WhatsApp, outbound calls, Urdu launch, photos, search |
| **C (Prediction)** | 6–12+ months | Forecasts, recommendations and anomaly detection, once real data exists |

**"Already sold by"** is filled in only where a product was named, and each link was opened on 2026-10-09 (§5). "New:" in the data column marks data BayFlow does not store yet.

| ID | Feature | What it does | Kind | Data it needs from BayFlow | Effort | Value | Phase | Already sold by |
|---|---|---|---|---|---|---|---|---|
| **Customer portal** | | | | | | | | |
| AI-01 | Symptom triage | The customer types or says what is wrong. The AI suggests matching services from the shop's catalogue, flags urgency, and writes clean notes for the technician. | Language | `services`, `bookings.customer_notes`, `booking_services`, `vehicles` | M | H | A | myKaarma Service Pre-Diag — https://mykaarma.com/solutions/service-concierge/ |
| AI-02 | Warning-light recognition | From a photo of the dashboard, the AI names the warning light(s), says how urgent it is and suggests a service. | Vision | `services`, `vehicles` (make, model, year). New: photo uploads (file uploads are out of hackathon scope, spec 00). | M | M | B | — |
| AI-03 | Vehicle auto-fill from a photo | A photo of the number plate or registration card fills in the registration number, make, model and year in the booking wizard. Other details on the card (owner name, CNIC) are discarded. | Vision | `vehicles` (`registration_number`, `registration_key`, make, model, year) | S | M | B | — |
| AI-04 | Plain-English shop search | "Brake service in Lahore tomorrow morning" returns matching shops, services and free slots. | Language | `shops` (city, `is_listed`, `rating`), `services`, `shop_working_hours`, `slot_counters` (availability, D37) | M | M | B | — |
| AI-05 | Estimate explainer | Explains each estimate line in plain Urdu or English: why it is needed and what happens if it is postponed. | Language | `estimates`, `estimate_lines`, `parts`, `services`, `vehicles`, `bookings.inspection_notes` | S | H | A | AutoVitals Otto Notes — https://support.autovitals.com/hc/en-us/articles/46171047206164-Otto-Notes-Release-Notes ; Shop-Ware AutoWrite — https://shop-ware.com/features/autowrite/ |
| AI-06 | Customer chat assistant | Web chat, and later WhatsApp (#38). Answers the same questions as the voice agent, with the same tools and guardrails. | Language | The spec 05 internal-endpoint data: `bookings`, `estimates`, `slot_counters`, `tasks`, `shops` | M | H | B | — |
| AI-07 | Ready-time prediction | Predicts when the car will be ready, with a confidence range, for both the customer and the SA. | Prediction | `booking_events` (time spent in each status), `estimate_lines` (labour hours), `purchase_orders` (supplier lead times), `qc_inspections` (fail rate) | L | H | C | — |
| AI-08 | Service reminders | Reminds customers when the next service is due, based on history and mileage. | Prediction | `bookings.mileage_km` (the mileage at each visit, D65), `vehicles.mileage_km` (latest only), `bookings` (`completed_at`), `booking_services`, `estimate_lines` | M | M | C (fixed-interval rule reminders can start in B) | — |
| **Service Advisor** | | | | | | | | |
| AI-09 | AI Front Desk | Answers in-app calls the SAs miss, identifies the caller, answers from booking data, and leaves a summary and a task (see note ²). | Voice | `bookings`, `estimates`, `call_logs`, `ai_call_summaries`, `tasks`, `slot_counters` | L | H | **Hackathon (P2, phase PH9), spec 05, D58** | AutoLeap AIR — https://autoleap.com/air/ ; Shopmonkey Concierge — https://www.shopmonkey.io/product/automotive-marketing/concierge ; GaragePlug Gia — https://www.garageplug.com/gia ; Fullbay Claudia — https://www.fullbay.com/ai-shop-receptionist/ |
| AI-10 | Transcripts and summaries of human calls | With consent, transcribes and summarises calls between an SA and a customer, and attaches them to the booking. | Voice | `call_logs`, `ai_call_summaries` (reused), `bookings`. New: recording or live transcription, plus consent records. | M | M | A | AutoLeap AIR — https://autoleap.com/air/ ; Fullbay — https://www.fullbay.com/ai-shop-receptionist/ (see note ¹) |
| AI-11 | Call scoring and lead scoring | Scores calls against a good-practice checklist and rates how likely each caller is to book. | Language | `call_logs`, `ai_call_summaries`, `bookings` (whether the call led to a booking) | M | M | C (needs call volume) | KUKUI AI Call Insights — https://kukui.com/ai-call-insights |
| AI-12 | Caller briefing | Before the SA answers, shows who is calling, which booking it is, its status and the likely reason for the call. | Language | `call_logs`, `bookings`, `booking_events`, `estimates`, `tasks` | S | H | A | Tekmetric Phones — https://www.tekmetric.com/feature/phones — shows the data without AI |
| AI-13 | Message drafting | Drafts customer messages (estimate sent, delay, car ready) in the customer's language, for the SA to edit and send. | Language | `bookings`, `estimates`, `notifications`. New: a preferred-language field on `users`. | S | M | A | Shop-Ware AutoWrite — https://shop-ware.com/features/autowrite/ |
| AI-14 | Estimate checker | Before the estimate is sent, flags unusual labour, missing companion parts (oil without a filter, for example) and prices below cost. | Language + rules | `estimate_lines`, `parts` (`unit_cost`), the shop's past `estimate_lines` | M | H | A (rules first; learned checks in C) | — |
| AI-15 | Urgency triage of new bookings | Flags safety-critical problems in new `PENDING` bookings so the SA confirms those first. | Language | `bookings.customer_notes`, `booking_services`, `services` | S | H | A | AgentZap — https://agentzap.ai/industries/auto-repair — detects breakdown emergencies |
| AI-16 | Technician suggestion | Suggests a technician based on skills, workload and past results. | Prediction | `shop_memberships`, `bookings` (`technician_user_id`, status), `booking_events` (durations), `qc_inspections` and `qc_issues` (results). New: technician skills. | L | M | C | — |
| AI-17 | Follow-up tasks and daily digest | Creates follow-up tasks (estimates not yet approved, ready cars not collected) and a morning digest for each SA. | Language | `tasks`, `notifications`, `bookings`, `booking_events`, `call_logs` | S | H | A | Shopmonkey Concierge — https://www.shopmonkey.io/product/automotive-marketing/concierge — creates follow-up tasks automatically |
| **Technician** | | | | | | | | |
| AI-18 | Voice-to-estimate | The technician speaks the findings, and the AI drafts estimate lines matched to inventory SKUs, showing live stock. | Voice + Language | `parts` (`sku`, `name`, `unit_cost`, `on_hand`, `reserved`), `estimate_lines`, `services`, `vehicles` | M | H | A | — |
| AI-19 | Diagnostic copilot | From the symptoms, OBD-II codes and make/model/year, suggests likely causes, tests to run and the usual parts. | Language | `vehicles`, `bookings.customer_notes`, `bookings.inspection_notes`, `parts`. New: external repair knowledge. | L | H | B | — |
| AI-20 | Photo inspection | From photos of tyre wear, leaks or worn pads, builds an inspection report with severity for the customer. | Vision | New: inspection photos. `bookings.inspection_notes`, `estimate_lines` (suggested lines). | L | H | B | — |
| AI-21 | "Fixed this before?" search | Finds similar past repairs in this shop: what was found, what was replaced, and whether QC passed first time. | Language | `bookings`, `estimate_lines`, `qc_issues`, `vehicles`, `booking_events`. New: embeddings (see #44). | M | M | B | — |
| AI-22 | Labour-time suggestion | Suggests labour hours for a job from the shop's own history. | Prediction | `estimate_lines` (`LABOUR` quantity), `booking_events` (`START_REPAIR` → `SEND_TO_QC` durations), `services` | M | M | C | — |
| AI-23 | Re-work checklist from a QC issue | Turns a QC issue into a short re-work checklist for the technician. | Language | `qc_issues`, `qc_inspections.checklist`, `estimate_lines` | S | M | A | — |
| **Parts** | | | | | | | | |
| AI-24 | Free text → SKU, with fitment check | Turns "front pads for a 2016 Civic" into the right SKU, and warns if the part may not fit. | Language | `parts`, `vehicles`. New: fitment data from an external catalogue. | M | M | B | — |
| AI-25 | Smart reorder quantities | Suggests how much of each part to reorder, and when. | Prediction | `stock_movements`, `parts.reorder_level`, `purchase_order_items`, `booking_parts` | M | M | C | — |
| AI-26 | Auto-drafted purchase orders | Drafts purchase orders grouped by supplier, comparing price and delivery time. | Language + rules | `booking_parts`, `parts`, `purchase_orders`, `purchase_order_items`. New: supplier price lists. | M | M | B | — |
| AI-27 | Supplier bill scanning | From a photo of a supplier's bill, marks the PO items as received after the Parts Person confirms. | Vision | `purchase_orders`, `purchase_order_items`, `parts`, `stock_movements` (through the existing receive endpoint) | M | M | B | — |
| AI-28 | Margin-based pricing | Suggests part prices that hit a target gross profit. | Prediction | `parts.unit_cost`, `estimate_lines.unit_price`, `estimates` (approved versus rejected) | M | H | C | Shop-Ware AI Parts Matrix — https://shop-ware.com/features/ai-parts-matrix/ |
| AI-29 | Stock anomaly alerts | Flags unusual adjustments, shrinkage and odd consumption patterns. | Prediction | `stock_movements` (`ADJUST`), `booking_parts`, `purchase_order_items` | M | M | C | — |
| **QC** | | | | | | | | |
| AI-30 | Job-specific QC checklist | Builds the QC checklist from the estimate lines; a brake job, for example, gets brake-test items. | Language | `estimate_lines`, `services`, `qc_inspections.checklist` (D46) | S | H | A | — |
| AI-31 | Voice road-test notes | The QC inspector speaks road-test notes, and the AI turns them into a structured issue (title and description). | Voice | `qc_issues`, `qc_inspections` | S | M | A | — |
| AI-32 | Comeback and failure patterns | Finds services and technicians with repeated QC failures or comebacks, for review by a person. | Prediction | `qc_inspections`, `qc_issues`, `bookings` (repeat visits per vehicle), `booking_services`, `vehicles` | M | H | C | — |
| **Owner** | | | | | | | | |
| AI-33 | "Ask your shop" | The owner asks plain-English questions ("How many Civics did we service last month?"), answered through safe, shop-scoped, read-only query tools. | Language | The reporting module's read models over the owner's own shops (spec 01); all core tables, read-only | L | H | B | — |
| AI-34 | Weekly AI report | A weekly report on bottlenecks, QC fail rate, approval rate and a branch comparison. SQL computes the numbers; the LLM writes the words. | Language | `booking_events`, `estimates`, `qc_inspections`, `stock_movements`, `call_logs`, `tasks` | S | H | A | — |
| AI-35 | Capacity and staffing forecast | Forecasts bookings per day and the staff needed for them. | Prediction | `slot_counters`, `bookings`, `booking_events`, `shop_memberships`, `shop_working_hours` | L | M | C | — |
| AI-36 | Leakage alerts | Flags repeated labour cuts, cancellations after parts were reserved, and unusual discounts. | Prediction | `estimates` (changes between versions), `estimate_lines`, `booking_events` (`CANCEL` with `metadata.released`), `stock_movements` | M | H | C (simple rules can start in B) | — |
| AI-37 | Marketing helper | Drafts win-back messages for lapsed customers and replies to reviews. | Language | `bookings` (`completed_at`), `vehicles`, `users`. New: marketing consent and reviews. | S | M | B | — |
| **Channels & safety** | | | | | | | | |
| AI-38 | WhatsApp assistant | The chat assistant (#6) on WhatsApp: status, estimate, reschedule requests and reminders. | Language | The spec 05 tools, `users.phone` (D33). New: a WhatsApp Business API account. | L | H | B | — |
| AI-39 | Urdu / Roman Urdu | Urdu and Roman Urdu for voice and text. Test the models' quality first. | Voice + Language | Nothing new except prompts and evaluation sets. New: a preferred-language field on `users`. | M | H | A (evaluation) → B (launch) | — |
| AI-40 | Outbound AI calls | Calls customers for reminders, to reduce no-shows, to say "your car is ready", and for short surveys. | Voice | `bookings` (`slot_start`, status), `call_logs`, `notifications`. New: consent records. | M | M | B | — |
| AI-41 | AI audit trail with PII masking | Logs every AI action (prompt version, tools called, output, who accepted it), with personal data masked. | Safety | New: an `ai_audit_events` table, linking to `call_logs`, `tasks`, `estimates` | M | H | F | — |
| AI-42 | Human approval for anything involving money | A policy plus a UI pattern: AI output that touches money (prices, discounts, estimate lines, POs) stays a draft until a person approves it. | Safety | `estimates` and `estimate_lines` (the existing `DRAFT` → `SENT` flow), `purchase_orders`, `tasks` | S | H | F | — |
| AI-43 | AI test suite | Scripted conversations and fixtures that fail if the agent invents data or leaks another customer's data. | Safety | Seed fixtures (spec 11), the spec 05 internal endpoints, and the LiveKit test framework with `mock_tools` [S3] | M | H | F (a first version exists in spec 05 §14: tests FD-xx and AG-xx) | — |
| AI-44 | Meaning-based search | Searches notes, QC issues and call transcripts by meaning rather than exact words. | Language | `bookings.customer_notes`, `bookings.inspection_notes`, `qc_issues`, `ai_call_summaries.transcript`. New: embeddings, which would use the `pgvector` extension — check host support at that time. | M | M | B | — |

¹ **Note on AI-10.** The AutoLeap AIR and Fullbay pages checked on 2026-10-09 describe summaries of calls answered *by their AI receptionist*. AutoLeap says "a clean, documented summary of every call"; Fullbay says "a full summary of the call by email". Neither page confirms summaries of calls answered by a person.

² **Note on AI-09.** AI-09 is the only backlog item built during the hackathon (D58, spec 05). Later extensions of the Front Desk stay under AI-09 instead of getting new IDs: a phone line (SIP or PSTN), which must ask for a stronger proof of identity than a name (spec 05 §4.2), and live transfer of an active call from the AI to a human SA (spec 05, Open question 4). Urdu for the Front Desk is part of #39. All of these are P3.

---

## 3. Top picks after the hackathon

> **Foundation built (D103).** AI-41 (audit trail), AI-42 (draft → decision) and AI-43 (grounding guard + golden-set harness) are implemented once in `app.modules.ai` ([modules/ai.md](modules/ai.md)), with the provider port, masking, feature flags and per-shop caps. Each pick below is a thin slice that calls `run_feature`.

Build the Foundations items (#41, #42, #43) alongside the first pick. #43 already exists in a small form for the AI Front Desk (spec 05 §14).

| Rank | Feature | Effort / Value | Why |
|---|---|---|---|
| 1 | **#5 Estimate explainer** | S / H | It tackles one of the brief's named problems: "Disputes over price … no audit trail" (brief §2). It should lift approval rates. It uses data BayFlow already stores well: versioned, structured estimate lines (D39, D40). It works from day one, and the risk is low because the SA reviews before sending. Similar products exist (AutoVitals Otto Notes, Shop-Ware AutoWrite). It is also the natural first use of Urdu (#39). |
| 2 | **#1 Symptom triage** | M / H | It improves the first information the shop gets about a job (brief §2: "no record of what the customer actually reported"). It maps to the shop's own `services` catalogue and fills `customer_notes` with clean text for the technician. It is low risk: it only suggests, and the customer still chooses the services in the wizard. Similar: myKaarma Service Pre-Diag. |
| 3 | **#18 Voice-to-estimate** | M / H | It saves technician time where the brief's pain is biggest (brief §2: "findings and part needs are not recorded; estimates are guesses"). Its output is ordinary estimate lines matched to `parts` SKUs with live stock (D40), so the parts flow and the state machine do not change. A human stays in the loop by design, because the technician still submits the estimate. |
| 4 | **#38 WhatsApp assistant** | L / H | Pakistani customers already live on WhatsApp (brief §2: garages run on "WhatsApp chats"). It answers "is my car ready?" without staff time, which addresses "communication overload". It reuses the AI Front Desk's tools, guardrails and internal-endpoint pattern (spec 05) and `users.phone` (D33). The effort goes into Business API onboarding, message templates and opt-in. |
| 5 | **#34 Weekly owner report** | S / H | It gives the multi-branch owner visibility (brief §2: "owner has no visibility across locations"). SQL computes the numbers from `booking_events`, `estimates` and `qc_inspections`, so no number is invented; the LLM only explains them. It is cheap: one batch call per shop per week. |

---

## 4. Hooks already in the hackathon architecture

These are the hackathon design choices that make the backlog cheap to build later.

| Hook | Where it is | What it makes cheap |
|---|---|---|
| **`booking_events` as clean history** | Spec 08: every transition and operation records who, which role, when, from, to, the action, a note and metadata | #7, #16, #22, #32, #34, #35, #36: time in each status, re-work loops, cancellations with the parts they released |
| **Structured, versioned estimate lines** | D39, D40. `PART` lines reference `parts` (SKU, unit cost); `LABOUR` lines carry hours. Versions are kept as `SUPERSEDED` / `APPROVED` / `REJECTED` with `decided_at`. | #5, #14, #18 (the output format already exists), #28, #36 (labour cuts between versions) |
| **Internal-endpoint pattern and restricted principals** | Spec 05 §5.1 and D58: a service token plus a per-call token (only its hash is stored), scope read from the DB row, an identity gate (403 `IDENTITY_NOT_VERIFIED`), read-only except tasks | #6, #33, #38, #40: the same tools behind a new channel, plus an owner principal for #33 |
| **Provider adapters** | Spec 05: the `CallMediaGateway` port (a name spec 05 proposes for the glossary) and the `AI_PROVIDER` switch (`openai` or `gemini`, glossary §12). Provider-neutral variable names from the brief's sample (`CALL_PROVIDER_*`, `LLM_API_KEY`, `STT_TTS_API_KEY`, brief §9.3). The notifications module already has two channels (in-app and e-mail). | #38 (WhatsApp as another channel), #40 (telephony later), and swapping models per feature |
| **AI is off when `LLM_API_KEY` is blank** | Glossary §12 | Every feature sits behind one kill switch plus its own flag (principle 5) |
| **`tasks`, `AI_TASK_CREATED` and the AI calls & tasks panel** | Spec 05 §6; visible to the SA and Owner (D21, capability `tasks.manage`) | Output from #12, #15 and #17, and the alerts from #36, land in an inbox that already exists, with mark-as-done |
| **Call transcripts and summaries** | `ai_call_summaries` | #10, #11, #44 |
| **`users.phone` and `BF-XXXXXX` booking references** | D33, glossary §1 | #38, #40: looking customers up by phone or reference |
| **Stock ledger** | `stock_movements` (D42) | #25, #29 |
| **QC checklist stored as JSON** | `qc_inspections.checklist` (D46) | #23, #30 |
| **Customer-facing status labels** | Glossary §3 | The same wording in every customer-facing AI answer (#6, #38, #40) |
| **Modular monolith with an event bus** | D3, spec 01 | AI features subscribe to events (e.g. `BookingActionApplied`) without touching any module's internals |

---

## 5. Sources (checked 2026-10-09)

**Platform sources**

| ID | Source | What it confirms |
|---|---|---|
| S1 | OpenAI data controls — https://developers.openai.com/api/docs/guides/your-data | API data is "not used to train or improve OpenAI models" by default (since 2023-03-01); abuse-monitoring logs are kept for up to 30 days |
| S2 | Gemini API pricing — https://ai.google.dev/gemini-api/docs/pricing | Free-tier data is "used to improve our products"; paid-tier data is not |
| S3 | LiveKit Agents test framework — https://docs.livekit.io/agents/start/testing/test-framework/ | `session.run(user_input=…)`, `result.expect…`, `mock_tools`; text-only mode |

**Vendor pages in the table**, each opened on 2026-10-09 and described in a short quote:

| Vendor | What the page says |
|---|---|
| myKaarma | "Service Pre-Diag uses an AI-powered agent to conduct a virtual interview with the customer prior to their appointment." |
| AutoVitals Otto Notes | The support page blocks automated fetching. AutoVitals' launch announcement of 2026-02-10 confirms the product: an "AI-powered technician notes rewrite" that turns technician notes into customer-friendly explanations. https://www.financialcontent.com/article/accwirecq-2026-2-10-autovitals-launches-otto-notes-ai-powered-technician-notes-rewrite-to-increase-approvals |
| Shop-Ware AutoWrite | It "helps your team turn everyday notes into clear, professional, customer-ready communication." |
| AutoLeap AIR | "AIR answers instantly even when your team is busy, after-hours, or closed" … "a clean, documented summary of every call". |
| Shopmonkey Concierge | It "answers when your team can't" … "Automatically create follow-up tasks for calls that need your teams attention." |
| GaragePlug Gia | "Gia answers calls when your team is busy or your shop is closed, books appointments, handles service-status calls, and brings your team in when needed." |
| Fullbay Claudia | It answers calls when the shop can't; "your shop gets a full summary of the call by email." |
| KUKUI AI Call Insights | "Every call is scored against proven best practices", plus a Lead Viability Score. |
| Tekmetric Phones | It "automatically identifies callers and surfaces the customer, vehicle, repair order, and appointment information". No AI is mentioned. |
| AgentZap | It "automatically detects urgent situations like overheating, brake failures, stalling, and strange noises." |
| Shop-Ware AI Parts Matrix | "Simply enter your desired parts GP% and it sets your auto parts pricing to hit the target." |

## Dependencies

- [17-decisions.md](17-decisions.md): D4, D36 (P3) and D59 keep this backlog out of hackathon scope; D58 decides the one exception, AI-09. D3, D20, D21, D33, D39, D40, D42, D46 and D65 provide the hooks and data in §2 and §4. D75 fixes the `AI-xx` ID prefix.
- [18-glossary.md](18-glossary.md): table names, roles, status labels and environment variables.
- [05-calling-and-ai-front-desk.md](05-calling-and-ai-front-desk.md): the only AI feature built now, and the pattern the rest reuse (internal endpoints, guardrails, tasks, tests).
- [08-booking-state-machine.md](08-booking-state-machine.md): AI never bypasses it.
- [01-architecture.md](01-architecture.md), [02-data-model.md](02-data-model.md): module boundaries, the event bus, the reporting module and the tables used in §2.
- [14-roadmap.md](14-roadmap.md): builds AI-09 in phase PH9, after PH8's in-app calling (phase names per D75), and schedules nothing else from this spec, which is priority P3. [16-open-questions-and-risks.md](16-open-questions-and-risks.md).

## Open questions

1. **pgvector.** Does Railway's managed PostgreSQL support the `pgvector` extension at the time #21 and #44 are scheduled? Check then.
2. **WhatsApp.** Choose between the Meta Cloud API and a business solution provider, plan template approval, and check per-conversation costs in Pakistan. Research before #38.
3. **Urdu.** How good are speech and text models at Urdu and Roman Urdu? Build an evaluation set first (#39); the AI Front Desk keeps Urdu off until it is tested (spec 05 §4.8).
4. **Data protection.** What are the obligations for transcripts and photos in Pakistan and other target markets? A legal review is needed before #10, #20 and #40.
5. **Data volume.** How much real data must a shop have before each prediction feature (#7, #8, #11, #16, #22, #25, #28, #29, #32, #35, #36) can be trusted? Define a threshold per feature after about 3 months of production data.
6. **Pricing.** Should BayFlow pass AI costs on to shops, through per-shop budgets or plans?
7. **Production provider.** Which model and provider for production (OpenAI, Anthropic, or the paid Gemini tier)? Compare data-processing terms, region, and latency from Pakistan.
8. **Fitment data.** Where can #24 get fitment data? No open catalogue has been identified yet.

## Proposed glossary additions

None are needed for the hackathon. The names below are **P3-only**: add them to the glossary when the feature is scheduled, not before.

- **Table:** `ai_audit_events` (#41).
- **Column:** a preferred-language column on `users` (#13, #39). Name it in spec 02 when it is scheduled.
- **Phase labels:** F, A, B, C (§2), used only inside this spec. They are not roadmap phases (PH0…PH10, D75) or priorities (P0–P3, D36).
- **Unnamed new data:** everything marked "New:" in §2 (photo uploads, consent records, marketing consent, technician skills, supplier price lists, fitment data, embeddings, reviews, a WhatsApp Business API account) is P3-only and deliberately has no name yet. Name it in spec 02 when the feature is scheduled.

Every other name this spec uses (tables, columns, roles, actions, enums, events, capabilities, variables) is already in the glossary, in spec 02, or in spec 05 §7 for the bonus tables (glossary §8). The one exception is `CallMediaGateway`, which spec 05 lists as a pending glossary proposal. The `AI-xx` feature IDs are recorded in D75.
