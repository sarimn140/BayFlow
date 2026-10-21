# BayFlow design system

One visual language for every screen: the landing page's. It follows GarageBox
(garagebox.io and its product app) for fonts, palette, radii and shadows, copying
**values only**: no GarageBox name, logo, photos, illustrations or code. The landing page
(`app/(public)/page.tsx`) and the booking flow (`components/booking/*`) are the reference
screens.

The system has three layers. Build every screen from them, in this order:

1. **Tokens** in `src/app/globals.css`: colours, radii, shadows and fonts. Screens use the
   Tailwind utilities generated from them (`bg-card`, `text-helper`, `rounded-2xl`,
   `shadow-dropdown`, …). Never a hex value.
2. **Primitives** in `src/components/ui/*`: shadcn/Radix components already restyled.
   Use them as they are; don't restyle them per page.
3. **Shared layout components** in `src/components/layout/*`: `PageHeader`, `StatCard`,
   `DataTableCard`, `TableSearch`, `DetailLayout`, `StickyActionBar`, `Timeline`, `EmptyState`,
   `FormSection`. Pages compose these instead of re-inventing them.

> Page engineers: follow this file literally. If a recipe here doesn't cover your case,
> copy the closest one and keep its sizes, colours and radii.

---

## 1. Principles

1. **Light and airy.** White cards on a pale blue canvas, hairline borders, soft warm
   shadows. No navy bars, no grey slabs.
2. **Rounded.** Buttons and chips are pills, fields 12px, cards 20px, dialogs 24px. Nothing
   square except the insides of a table.
3. **One family, heavy headings.** Fira Sans everywhere: titles 800, card titles 600, body 400.
   A handwritten word (Edu NSW ACT Foundation) at most once per page, in a hero or greeting.
4. **Colour has a job.** Brand blue = the action (one primary per view). Green = success.
   Orange = attention ("action needed"). Phase hues = booking status only. Everything else
   is neutral stone.
5. **Accessible by default.** Text ≥ 4.5 : 1, control edges and focus ≥ 3 : 1, 12px minimum
   text, 40px touch targets (48px for technicians on the floor; 24px is only the WCAG floor for
   dense desktop rows), visible focus everywhere.

---

## 2. Tokens

The app is light-only for now (D93, `forcedTheme="light"`); every token also has a valid
dark value in `.dark`. `src/app/theme-tokens.test.ts` fails a screen that uses a hex class,
`bg-white` or a grey palette (`gray-*`, `slate-*`, `neutral-*`, `zinc-*`, `stone-*`).

### 2.1 Colour

| Role                     | Utility                                                              | Light value           | Use                                                                                                       |
| ------------------------ | -------------------------------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------- |
| Page (marketing)         | `bg-background`                                                      | `#FFFFFF`             | Landing, booking, auth                                                                                    |
| **Canvas**               | `bg-canvas`                                                          | `#F2F7FE`             | Behind cards on every app screen (the shells set it; don't repeat it)                                     |
| Card                     | `bg-card`                                                            | `#FFFFFF`             | Cards, tables, dialogs, menus                                                                             |
| Paper (inset well)       | `bg-layer`                                                           | `#EDF2FA`             | A tinted well _inside_ a card (totals box, notes). Not for cards                                          |
| Muted                    | `bg-muted`                                                           | `#FAFAF9`             | Table footer, card footer bar, quiet panels                                                               |
| Secondary                | `bg-secondary`                                                       | `#F4F4F3`             | Neutral chips, icon tiles, secondary buttons                                                              |
| Hover surface            | `bg-accent` / `bg-layer-hover` / `bg-nav-hover`                      | `#EAEEF3`             | Menu item and nav hover                                                                                   |
| Text                     | `text-foreground`                                                    | `#1C1917`             | Titles, values, body                                                                                      |
| Text, secondary          | `text-muted-foreground`                                              | `#44403C`             | Descriptions, table secondary lines, labels in lists                                                      |
| Text, small / meta       | `text-helper`                                                        | `#736C67`             | Captions, timestamps, hints, table headers (≥ 4.59 on every light surface above except the hover surface) |
| Decorative only          | `text-subtle-foreground`                                             | `#A8A29E`             | Quiet icons, separators. **Never text** (2.5 : 1)                                                         |
| Border                   | `border-border` (default)                                            | `#D9D9D9`             | Cards, dividers                                                                                           |
| Border, faint            | `border-border-faint`                                                | `#ECECEC`             | Table row dividers, divider lines inside cards                                                            |
| Border, medium           | `border-border-medium`                                               | `#D6D3D1`             | Outline buttons, filter pills                                                                             |
| Control edge             | `border-input` (= `border-border-strong`)                            | `#8B857F`             | Inputs, selects, checkboxes, radios, switch track (≥ 3 : 1)                                               |
| **Brand blue (primary)** | `bg-primary` = `bg-brand-blue`                                       | `#002CF1`             | The primary button, checked controls, selected day, unread dot                                            |
| Brand blue, hover        | `hover:bg-primary-hover`                                             | `#1D4ED8`             | (Buttons do this themselves)                                                                              |
| Brand blue, text         | `text-brand-blue-ink`                                                | `#002CF1`             | Links, IDs that link, eyebrows, selected labels                                                           |
| Brand blue, tint         | `bg-brand-blue-subtle`                                               | `#E4EBF9`             | Icon tiles, selected pills, row hover (`/40`), info surfaces                                              |
| Active nav               | `bg-sidebar-accent`                                                  | `#BFDBFE`             | The current sidebar item (dark text, blue icon). Sidebar only                                             |
| Green (fill and text)    | `bg-brand-green` + `text-brand-green-foreground`, `text-brand-green` | `#047857`             | "Ready", "Pass", success fills (white on it 5.5 : 1)                                                      |
| Green, accent            | `bg-brand-green-accent`                                              | `#10B981`             | Decoration only: progress bars, dots, illustration accents. Never under text                              |
| Attention (orange)       | `text-cta`, `bg-attention`, `border-attention-border`                | `#BD490A` / `#FFF4E6` | "Action needed" chips and banners. Never a second CTA                                                     |
| Success                  | `bg-success-subtle` `text-success-ink`                               | `#D9F4EB` / `#047857` | Positive notices and chips                                                                                |
| Warning                  | `bg-warning-subtle` `text-warning-ink`                               | `#FCF3D7` / `#854D0E` | Low stock, pending                                                                                        |
| Danger                   | `bg-danger-subtle` `text-danger-ink`                                 | `#FCE1E1` / `#B91C1C` | Errors, rejected, suspended                                                                               |
| Info                     | `bg-info-subtle` `text-info-ink`                                     | `#D6DDFD` / `#1D4ED8` | Read-only notes, tips                                                                                     |
| Destructive              | `text-destructive`, `bg-destructive-strong`                          | `#DA2626` / `#DC2626` | Field errors; the danger button                                                                           |
| Focus ring               | `outline-ring` (automatic)                                           | `#002CF1`             | 2px, 2px outside (fields: blue border + blue halo)                                                        |

Measured contrast (WCAG 2.x): foreground on white 17.5; muted-foreground 10.3; helper 5.16
(white), 4.79 (canvas), 4.59 (paper), 4.94 (muted); white on primary 7.98; blue ink on
blue tint 6.67; dark text on active nav 12.3; white on green 5.48; control edge 3.65
(white) / 3.39 (canvas); focus ring 7.98 (white) / 7.42 (canvas). Every status chip pair
is ≥ 4.6 (table below).

AA corrections against GarageBox's raw values: helper `#78716C` → `#736C67` (theirs fails on
the canvas: 4.46); field borders `#D9D9D9` → `#8B857F` (theirs 1.4 : 1); error text `#DC2626`
→ `#DA2626` (theirs 4.49 on the canvas); green fills `#10B981` → `#047857` (white on theirs
2.5 : 1).

### 2.2 Booking status chips (spec 09 §3.3)

One hue per phase, soft fill + 1px border + dark ink. The same hue and icon for every role
(staff and customers see different _words_, never different colours). Brand blue is never a
status colour; intake uses the blue-violet "primary soft" tint, which is not the button blue.

| Phase             | Statuses                                              | Badge variant       | Fill / ink / border               | Ink on fill |
| ----------------- | ----------------------------------------------------- | ------------------- | --------------------------------- | ----------- |
| Intake            | PENDING, CONFIRMED                                    | `intake`            | `#D6DDFD` / `#1D4ED8` / `#ADBBFA` | 4.98        |
| Inspection        | ASSIGNED, INSPECTING                                  | `inspection`        | `#ECE5FE` / `#6D28D9` / `#DACBFC` | 5.82        |
| Estimate          | ESTIMATE_REVIEW, AWAITING_CUSTOMER, ESTIMATE_APPROVED | `estimate`          | `#FCF3D7` / `#854D0E` / `#F8E7B0` | 6.18        |
| Estimate rejected | ESTIMATE_REJECTED                                     | `estimate-rejected` | `#FCE1E1` / `#B91C1C` / `#FAC3C3` | 5.24        |
| Parts             | PARTS_PENDING, PARTS_ORDERED, PARTS_READY             | `parts`             | `#D7F3F8` / `#0E7490` / `#AFE8F1` | 4.61        |
| Repair & QC       | IN_REPAIR, QC_PENDING, QC_IN_PROGRESS                 | `repair-qc`         | `#F9E1FC` / `#A21CAF` / `#F3C4FA` | 5.18        |
| Hand-over         | READY_FOR_PICKUP, COMPLETED                           | `handover`          | `#D9F4EB` / `#047857` / `#B3E9D7` | 4.72        |
| Closed            | CANCELLED                                             | `closed`            | `#E9E8E7` / `#44403C` / `#D6D3D1` | 8.39        |

Always render a booking status with `StatusBadge` (never a hand-made chip):

```tsx
<StatusBadge status={booking.status} audience="staff" />            // lists, tables (24px)
<StatusBadge status={booking.status} audience="customer" size="md" /> // beside a page title (28px)
```

The phase tokens (`bg-status-parts-bg`, `text-status-parts-fg`, `border-status-parts-border`,
…) may also tint an icon tile or a timeline node of that phase. `chart-1` … `chart-5` are the
phase inks for charts (intake, inspection, estimate, parts, repair & QC).

### 2.3 Type

| Family         | Utility            | Font                    | Use                                                 |
| -------------- | ------------------ | ----------------------- | --------------------------------------------------- |
| Sans (default) | `font-sans`        | Fira Sans 400–900       | Everything. `h1`–`h6` get it automatically          |
| Heading        | `font-heading`     | Fira Sans (same family) | Kept so older code compiles; adds nothing now       |
| Handwritten    | `font-handwriting` | Edu NSW ACT Foundation  | Only through `<Handwritten>` (§6.12)                |
| Mono           | `font-mono`        | JetBrains Mono          | Booking refs, plates, VINs, SKUs, PO numbers, codes |

Headings default to 800 (`h1`, `h2`), 700 (`h3`–`h5`), 600 (`h6`); a weight class on the
element wins. No letter-spacing on body text.

**Scale for app screens** (copy the classes):

| Role                     | Classes                                                                                            | Size       |
| ------------------------ | -------------------------------------------------------------------------------------------------- | ---------- |
| Page title (`h1`)        | `text-3xl sm:text-4xl leading-tight font-extrabold tracking-tight` — use `PageHeader`              | 30 / 36px  |
| Hero / greeting title    | `text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight`                                   | up to 48px |
| Section title (`h2`)     | `text-xl font-bold` (big sections) or `text-lg font-semibold` (card titles; `CardTitle` does this) | 20 / 18px  |
| Sub-section (`h3`)       | `text-base font-semibold`                                                                          | 16px       |
| Body (reading)           | `text-base text-muted-foreground` (descriptions, notes)                                            | 16px       |
| Body (UI, tables, lists) | `text-sm` (`text-foreground` for the main line)                                                    | 14px       |
| Label                    | `text-sm font-medium` (`Label` / `FieldLabel` do this)                                             | 14px       |
| Small / meta (minimum)   | `text-xs text-helper`                                                                              | 12px       |
| Eyebrow                  | `text-sm font-semibold text-brand-blue-ink`                                                        | 14px       |
| KPI value                | `text-3xl font-extrabold tracking-tight tabular-nums`                                              | 30px       |
| Money                    | `formatPKR(…)` + `tabular-nums`, right-aligned in tables                                           | —          |

Never: `text-[10px]`, `text-[11px]`, uppercase labels with wide tracking
(`uppercase tracking-wider`, `tracking-[0.32px]`), `font-bold` on 12px text as a way to
"make it visible". The legacy Carbon utilities (`type-heading-04`, `type-body-01`, …) still
compile but are not to be used in new markup.

### 2.4 Radius (explicit scale)

| Utility        | Size | Use                                                             |
| -------------- | ---- | --------------------------------------------------------------- |
| `rounded-sm`   | 6px  | Tiny marks (`kbd`, swatches)                                    |
| `rounded-md`   | 8px  | Menu items, small selects, plate/SKU tags                       |
| `rounded-lg`   | 12px | **Inputs, selects, textareas**, menus/dropdowns, skeleton lines |
| `rounded-xl`   | 16px | Alerts, popovers, nav items, icon tiles (`size-9`/`size-10`)    |
| `rounded-2xl`  | 20px | **Cards**, table cards, KPI cards, list rows that are cards     |
| `rounded-3xl`  | 24px | **Dialogs**, sheets (open edge), hero bands, empty states       |
| `rounded-full` | pill | **Buttons**, chips/badges, toggles, search field, avatars       |

### 2.5 Shadows (warm stone, GarageBox)

| Utility                            | Value                                         | Use                                    |
| ---------------------------------- | --------------------------------------------- | -------------------------------------- |
| `shadow-xs`                        | `0 1px 2px 0 rgb(120 113 108 / .16)`          | Cards, fields (the "card" shadow)      |
| `shadow-sm`                        | `0 1px 3px …, 0 1px 2px -1px …` (stone 16 %)  | Raised pills, the active segmented tab |
| `shadow-md` / `shadow-lg`          | `0 8px 16px 0 …` / `0 12px 24px -4px …`       | Hover lift of a clickable card         |
| `shadow-dropdown` (`shadow-float`) | `0 0 2px 0 …/.24, -20px 20px 40px -4px …/.24` | Menus, popovers, selects (built in)    |
| `shadow-dialog`                    | `-40px 40px 80px -8px rgb(0 0 0 / .24)`       | Dialogs, sheets (built in)             |
| `shadow-glow`                      | `0 8px 16px 0 rgb(0 44 241 / .24)`            | Primary button hover (built in)        |

Don't stack big shadows on cards; a clickable card goes `shadow-xs` → `hover:shadow-md`.

### 2.6 Spacing and layout

- The shells already give every app page: the canvas, `max-w-7xl` (POS, admin) or
  `max-w-5xl` (customer), gutters `px-4 sm:px-6 lg:px-8`, and `py-6 lg:py-8`. Pages render
  content only — no outer padding, no background, no `<main>` (except the three POS pages
  outside a shop, see §3).
- Between page sections: `space-y-6` (big pages `space-y-8`).
- Grids of cards: `gap-4`; two-column layouts: `gap-6 xl:gap-8`.
- Card padding: 24px (`Card` does it; 20px on phones). Rows inside cards: `px-5 py-3.5`.
- Breakpoints: `sm` 640, `md` 768 (below it the sidebar is a sheet and tables stack), `lg`
  1024, `xl` 1280.
- **Respond to the space, not the screen.** From `md` the shop sidebar takes 256px, so a 1024px
  screen leaves a 704px page and a 768px tablet only 464px. Anything that sits side by side inside
  the page (a title and its actions, a main column and an aside, a table and its stacked list)
  switches on its own width: a container query (`@container/name` + `@xl/name:…`, as the overview
  and queue cards do) or an intrinsic wrap (`flex-wrap` with a `flex-basis`, as `PageHeader` does)
  — never `md:` / `lg:` alone. A query container sizes as if it were empty, so it must never be
  shrink-to-fit (give it `w-full`, or keep it a block in the page's stack).
- Touch targets: 40px for every control a finger uses: the default (42px) and `lg` buttons, the
  toolbar controls (§5 `DataTableCard`), tabs, the table search; 48px for technicians. The `sm`
  and `icon-sm` sizes are for dense desktop rows; where they must be tapped, extend the hit area
  with `relative after:absolute after:-inset-1` (as the table-search clear button does).
- Motion: `transition-colors duration-150` for hovers; overlays fade/zoom 150–200ms. Nothing
  bounces; nothing loops (except the landing marquee).

### 2.7 Focus

The primitives draw it for you: a 2px brand-blue ring 2px outside the element (inset on
sidebar items), and for fields a blue border plus a blue halo. For a hand-made interactive
element (a card that is a link, a custom pill, a tile button) copy exactly:

```
outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring
```

`focus-visible:outline-solid` is **required** whenever `outline-none` (or `outline-hidden`) is
on the element: in Tailwind 4 those set the outline style to `none`, and `outline-2` alone
then draws nothing.

---

## 3. App shell (already built — don't rebuild it)

| Area     | Files                                                                                              | What you get                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| -------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POS      | `app/(pos)/pos/layout.tsx`, `components/layout/pos-header.tsx`                                     | 64px white translucent bar: sidebar toggle (a member's shop pages), logo, **shop switcher pill** (All shops summary for owners of 2+ shops, **the person's own shops only**, Create shop last; switching takes their role in that shop), the person's **role in this shop** (a chip, not a switch: no role or account switching, D52; demo accounts are on the login page), bell, account menu. A shop the person is not in is never named ("Choose a shop"; "No shop yet" without any)                                                                     |
| POS shop | `app/(pos)/pos/shops/[shopId]/layout.tsx`, `shop-scope.tsx`, `section-gate.tsx`, `pos-sidebar.tsx` | **Members only (D20)**: anyone who is not an active member of the shop (other shops' staff, customers, admins without a membership) gets the 404 view "We couldn't find that shop" with no sidebar, the same as for a shop that doesn't exist. Members get the 256px white sidebar of their role in this shop (`lib/pos-access.ts`, active = `#BFDBFE`; a 64px icon rail via the bar toggle, ⌘B or the rail; a sheet below `md`), then `SectionGate`: suspended shop (D96), then another role's section → `ForbiddenState`, judged by the membership's role |
| Admin    | `components/admin/admin-shell.tsx`                                                                 | Same bar with a dark "Platform admin" pill, admin sidebar, gate, skeleton                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Customer | `app/(customer)/layout.tsx`                                                                        | Public header + canvas, `max-w-5xl`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Public   | `app/(public)/layout.tsx`                                                                          | Public header/footer; `.marketing` pages own their full-bleed sections                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

The POS hub (`/pos`), new shop (`/pos/shops/new`) and all-shops summary (`/pos/summary`) have
no sidebar and render their own landmark:

```tsx
<main id="main" tabIndex={-1} className="flex-1 outline-none">
  <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">…</div>
</main>
```

The shop, admin and customer content landmarks clip horizontal overflow (`overflow-x-clip`)
as a safety net, but a page must still never be wider than the phone: wide tables scroll
inside `Table`, long words truncate (`min-w-0` + `truncate` in flex rows). Add
`overflow-x-clip` to your own `<main>` on the three pages above.

---

## 4. Primitives (`components/ui`)

| Component                                                                            | Look                                                                                                                                                                                                                                                             | Notes                                                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Button`                                                                             | Pill, 14px medium. `default` blue + glow on hover; `outline` white + stone border; `destructive-outline` white + stone border + danger-ink label, pink on hover; `secondary` stone fill; `ghost` clear; `destructive` red; `link` blue text; `cta` orange (rare) | Sizes: `sm` 36, **`default` 42**, `lg` 48, `xs` 28; `icon` 40, `icon-sm` 32, `icon-xs` 24, `icon-lg` 48. Put icons as children; they size themselves. Pressed = `scale` 98 %: a stretched link needs `active:scale-none` (§6.14) |
| `Input`, `Textarea`, `NativeSelect`, `SelectTrigger`, `InputGroup`                   | 42px, `rounded-lg`, white, 1px `border-input`, `shadow-xs`; focus = blue border + blue halo; invalid = red border + red halo; 16px text on phones                                                                                                                | Set `aria-invalid` for errors. `size="sm"` (36px) exists on selects                                                                                                                                                              |
| `Label`, `FieldLabel`                                                                | 14px medium, foreground                                                                                                                                                                                                                                          | `FieldDescription` 14px muted; `FieldError` 14px red                                                                                                                                                                             |
| `Field`, `FieldGroup`, `FieldSet`, `FieldLegend`                                     | 8px label→control gap; 20px between fields; legend = 20px bold section title                                                                                                                                                                                     | `Field orientation="responsive"` for label-left layouts                                                                                                                                                                          |
| `Checkbox`, `RadioGroupItem`                                                         | 16px, stone edge, checked = blue                                                                                                                                                                                                                                 | Checkbox corner 5px                                                                                                                                                                                                              |
| `Switch`                                                                             | 24×44 pill, stone track, blue when on                                                                                                                                                                                                                            | `size="sm"` 20×36                                                                                                                                                                                                                |
| `Card`                                                                               | White, `rounded-2xl`, border, `shadow-xs`, 24px padding                                                                                                                                                                                                          | `size="sm"` = 16px padding. `CardTitle` 18px semibold                                                                                                                                                                            |
| `Table`                                                                              | Flush; header band `bg-layer/60` with 14px helper labels; 48px rows; faint dividers; blue hover tint; no zebra                                                                                                                                                   | Container is `relative` + scrolls horizontally. Put it in `DataTableCard`                                                                                                                                                        |
| `Badge`                                                                              | 24px pill, 12px medium, soft fill + border                                                                                                                                                                                                                       | Variants: `success`, `warning`, `info`, `neutral`, `brand`, `destructive`, `attention`, `secondary`, `outline`, phase variants                                                                                                   |
| `StatusBadge`                                                                        | Booking status chip (see §2.2)                                                                                                                                                                                                                                   | `size="md"` beside titles                                                                                                                                                                                                        |
| `Tabs`                                                                               | `TabsList` default = segmented pill on `bg-secondary`, 48px, so each trigger is a 40px target; `variant="line"` = underline tabs (blue indicator, 48px)                                                                                                          | Segmented for views/filters; line for sections of a record                                                                                                                                                                       |
| `ToggleGroup` / `Toggle`                                                             | Filter pills; on = blue tint + blue ink                                                                                                                                                                                                                          | `variant="outline" size="sm"` in toolbars                                                                                                                                                                                        |
| `Dialog`, `AlertDialog`                                                              | `rounded-3xl`, white, dialog shadow, navy 40 % blurred scrim, close button top-right; never taller than the screen (`100dvh − 2rem`, scrolls inside)                                                                                                             | Default `sm:max-w-lg`. `AlertDialogMedia` sits beside the title from `sm` in its own icon-wide column. Focus goes back to the opener on close (§6.10)                                                                            |
| `Sheet`                                                                              | White panel, `rounded-*-3xl` on the open edge; scrolls inside when taller than the screen                                                                                                                                                                        | Right side: full width and square on phones, 448px (`sm:max-w-md`) from `sm` — no `w-full` overrides. Focus goes back to the opener on close (§6.10)                                                                             |
| `DropdownMenu`, `Select` content, `Popover`, `Command`, `Tooltip`                    | Translucent white + blur, `rounded-lg` (popover `rounded-xl`), dropdown shadow, 36px items with 8px corners; tooltip dark `rounded-md`                                                                                                                           | Menu icons are muted automatically                                                                                                                                                                                               |
| `Alert`                                                                              | `rounded-xl`, soft tint + border; title and icon in the ink, body in foreground                                                                                                                                                                                  | Variants: `default`, `info`, `success`, `warning`, `destructive`                                                                                                                                                                 |
| `Empty`                                                                              | Centered, dashed `rounded-3xl` (add `border bg-card`), blue icon tile                                                                                                                                                                                            | Prefer `EmptyState`                                                                                                                                                                                                              |
| `Skeleton`                                                                           | `rounded-lg`, stone `#E7E5E4`, pulse                                                                                                                                                                                                                             | Shape it like the content (`rounded-2xl` for cards, `rounded-full` for pills)                                                                                                                                                    |
| `Calendar`                                                                           | Circular days; selected = blue; today = blue tint; disabled days are faded text                                                                                                                                                                                  | —                                                                                                                                                                                                                                |
| `Accordion`, `Progress`, `Avatar`, `Breadcrumb`, `Pagination`, `Separator`, `Sonner` | Restyled to match (progress = blue on blue-15 %, toasts `rounded-2xl`; a toast's `action` is the small blue pill, its `cancel` the small outline pill, both 36px)                                                                                                | Toasts: `toast.success('Saved')` from `sonner`; errors stay inline too                                                                                                                                                           |

---

## 5. Shared layout components (`components/layout`)

### `PageHeader`

```tsx
import { PageHeader } from '@/components/layout/page-header'

<PageHeader
  eyebrow="Service advisor"                    // optional, small blue line
  title="Bookings"                              // the page's only <h1> (ReactNode)
  description="Confirm intakes, assign technicians and send estimates."
  actions={<Button><Plus /> New walk-in</Button>}  // one primary at most; others outline/ghost
/>

// It goes first in the page's `space-y-6` stack and adds 8px below itself. The actions sit on
// the right only when the header has room for them beside a 24rem title block; otherwise they
// wrap below the description (a tablet with the sidebar open). Always pass them as `actions` —
// don't put PageHeader in a flex row of your own, and don't add `md:`/`lg:` overrides.

// Detail page: back link + status chip beside the title
<PageHeader
  back={{ href: `${base}/bookings`, label: 'Bookings' }}
  title={<span className="font-mono">{booking.reference}</span>}
  badges={<StatusBadge status={booking.status} audience="staff" size="md" />}
  description={`${booking.customerName} · ${booking.licensePlate}`}
  actions={<><Button variant="outline">Call customer</Button><Button>Send estimate</Button></>}
/>
```

### `StatCard` (KPI)

```tsx
import { StatCard } from '@/components/layout/stat-card'

;<div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
  <StatCard
    label="Needs action"
    value={2}
    icon={Clock}
    tone="warning"
    hint="Intake, estimates and pick-up calls"
    href={`${base}/bookings?filter=needs_action`}
  />
  <StatCard
    label="In progress"
    value={3}
    icon={Wrench}
    tone="brand"
    hint="Diagnosis, repairs and QC"
  />
  <StatCard label="Ready for pick-up" value={1} icon={CarFront} tone="success" />
  <StatCard label="Revenue today" value={formatPKR(48500)} icon={Banknote} />
</div>
```

`tone`: `default` (stone tile) · `brand` · `success` · `warning` · `danger` (warning/danger
also colour the value). With `href` the whole card is a link (hover lift + focus ring).

### `DataTableCard` and `TableSearch`

```tsx
import { DataTableCard, TableSearch } from '@/components/layout/data-table-card'

;<DataTableCard
  className="@container/list"
  toolbar={
    <>
      <TableSearch
        value={query}
        onValueChange={setQuery}
        label="Search bookings"
        placeholder="Reference, plate or customer"
      />
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={filter}
        onValueChange={(v) => setFilter(v || 'all')}
        aria-label="Filter bookings"
      >
        <ToggleGroupItem value="all">All</ToggleGroupItem>
        <ToggleGroupItem value="needs_action">Needs action</ToggleGroupItem>
        <ToggleGroupItem value="in_progress">In progress</ToggleGroupItem>
      </ToggleGroup>
      <p className="text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
        <span className="font-semibold text-foreground tabular-nums">{rows.length}</span> bookings
      </p>
    </>
  }
  footer={pager /* optional: "1–20 of 312" + outline icon-sm arrows; admin-ui `usePaged` */}
>
  {rows.length === 0 ? (
    <EmptyState
      variant="inline"
      icon={SearchX}
      title="No bookings match"
      description="Try another reference or plate."
      action={
        <Button variant="outline" onClick={reset}>
          Clear filters
        </Button>
      }
    />
  ) : (
    <>
      {/* a narrow card (phones, a tablet with the sidebar open): stacked rows */}
      <ul className="divide-y divide-border-faint @3xl/list:hidden">…see §6.3…</ul>
      {/* a card 768px wide and up: the table */}
      <div className="hidden @3xl/list:block">
        <Table>…</Table>
      </div>
    </>
  )}
</DataTableCard>
```

Props: `title?`, `description?`, `actions?` (title row), `toolbar?`, `footer?`, `children`.

- **The toolbar sizes its controls**: the search, filter pills (`ToggleGroup`, any size), selects
  (`NativeSelect`, `SelectTrigger`) and `sm`/default buttons in `toolbar` are all 40px tall, so
  the row lines up and meets the touch-target minimum. Don't set heights on them.
- `TableSearch`: a 40px pill, capped at 100 characters (spec 09 §2.10; `maxLength` to change it),
  with its own clear button (the browser's is hidden). Other props (`id`, `name`,
  `aria-describedby`, `onKeyDown`, …) go to the `<input>`; `className` goes to the pill.

### `DetailLayout` and `StickyActionBar`

```tsx
import { DetailLayout, StickyActionBar } from '@/components/layout/detail-layout'

;<DetailLayout aside={<>{/* status + next action card, customer card, vehicle card */}</>}>
  {/* main sections: concern, inspection, estimate, activity */}
</DetailLayout>
```

- **Two columns when the layout itself is 58rem (928px) wide**: a container query, so the main
  column keeps about 550px: from a 1280px screen with the sidebar open, from 1024px without it
  (the customer portal). Narrower, one column. Don't override it (`lg:grid-cols-…`,
  `xl:grid-cols-…`, a `className` on the grid): it is right at every width.
- **Order**: in one column the aside comes **first** (status and next action before the details);
  `asideFirstOnMobile={false}` puts it after the main column. That is the DOM order, so on phones
  and tablets reading and focus order are exactly what is seen (no `order-*`); in two columns the
  grid places the aside on the right and it is still read first, as one complete column (the
  status and next action, then the record).
- **Sticky aside**: in two columns it sticks under the app bar, but only while it fits on the
  screen; a taller aside (two long cards on a short laptop) scrolls with the page, so its end is
  never out of reach.
- **Content for one mode only** (a card in the aside in two columns, in the main column in one):
  render it twice, with `detailLayoutOnly.twoColumns` and `detailLayoutOnly.oneColumn` (exported
  with `DetailLayout`); never `lg:hidden` / `max-lg:hidden`, the layout switches on its own width.
- A detail page's loading skeleton renders `DetailLayout` too (with `Skeleton` children), so it
  switches at the same width as the page.

`StickyActionBar` pins its buttons to the bottom of the screen and renders inline from
`pinnedUntil` up: `md` (default, phones), `lg` or `xl` (tablets too, for a page whose actions only
move beside the content on a large screen; hide it there with `lg:hidden` / `xl:hidden`). It
spans the page gutter while pinned and takes `div` props (`role="region"`, `aria-label`).

### `Timeline`

```tsx
import { Timeline } from '@/components/layout/timeline'

;<Timeline
  aria-label="Booking activity"
  items={events.map((e) => ({
    id: e.id,
    title: e.title, // "Estimate sent to customer"
    description: `${e.actorName} · ${e.actorRole}`,
    time: <time dateTime={e.at}>{formatDateTime(e.at, shop.timezone)}</time>,
    icon: FileText,
    tone: 'brand', // default | brand | success | warning | danger
  }))}
/>
```

Newest first. Use the phase's tone for status changes (`success` for approved/passed,
`danger` for rejected/failed).

### `EmptyState`

```tsx
import { EmptyState } from '@/components/layout/empty-state'

// first use — one action
<EmptyState icon={Tags} title="No services yet"
            description="Add the services customers can book." action={<Button><Plus /> Add service</Button>} />
// no results — clear filters
<EmptyState variant="inline" icon={SearchX} title="No parts match"
            description="Try another SKU or name." action={<Button variant="outline">Clear filters</Button>} />
// all done — no action
<EmptyState tone="success" icon={CheckCheck} title="Queue is clear" description="Nothing is waiting for QC." />
```

`variant="card"` (default) is a dashed card for the canvas; `inline` sits inside another card.
`tone`: `brand` (default), `success`, `neutral`.

### `FormSection`

```tsx
import { FormSection } from '@/components/layout/form-section'

;<FormSection
  title="Workshop profile"
  description="Shown on your public page and on estimates."
  footer={
    <>
      <Button variant="outline">Cancel</Button>
      <Button type="submit">Save changes</Button>
    </>
  }
>
  <FieldGroup className="grid gap-5 sm:grid-cols-2">
    <Field>
      <FieldLabel htmlFor="name">Workshop name</FieldLabel>
      <Input id="name" />
    </Field>
    <Field>
      <FieldLabel htmlFor="phone">Phone</FieldLabel>
      <Input id="phone" type="tel" />
    </Field>
  </FieldGroup>
</FormSection>
```

Title and description on the left from `lg`, the fields in a card on the right, footer bar on
`bg-muted`. Stack several with `space-y-8`, and separate them with nothing else.

### Others

- `AccountMenu` (`account-menu.tsx`): the avatar menu used by the shells. Pages don't use it.
- `Handwritten` (`components/booking/booking-hero.tsx`): the accent word, see §6.12.

---

## 6. Patterns (copy-paste recipes)

### 6.1 A list page

```tsx
<div className="space-y-6">
  <PageHeader eyebrow="Parts" title="Inventory" description="…" actions={<Button><Plus /> Add part</Button>} />
  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{/* StatCards, optional */}</div>
  <DataTableCard toolbar={…}>…</DataTableCard>
</div>
```

### 6.2 Cards with a title row

```tsx
<Card>
  <CardHeader>
    <CardTitle>Workshop team</CardTitle>
    <CardDescription>7 members</CardDescription>
    <CardAction>
      <Button variant="ghost" size="sm">
        Manage
      </Button>
    </CardAction>
  </CardHeader>
  <CardContent>…</CardContent>
</Card>
```

A card whose body is a flush list (rows touch the edges):

```tsx
<Card className="gap-0 py-0">
  <CardHeader className="border-b pt-(--card-spacing)">
    <CardTitle>Active bookings</CardTitle>
    <CardAction><Button asChild variant="ghost" size="sm"><Link href={…}>View all</Link></Button></CardAction>
  </CardHeader>
  <ul className="divide-y divide-border-faint">
    <li>
      <Link href={…} className="flex items-center justify-between gap-4 px-5 py-3.5 transition-colors hover:bg-brand-blue-subtle/40 sm:px-6">
        <div className="min-w-0 space-y-0.5">
          <p className="font-mono text-sm font-semibold text-brand-blue-ink">BF-2026-001</p>
          <p className="truncate text-sm font-medium text-foreground">Ayesha Khan · Honda Civic</p>
          <p className="truncate text-xs text-helper">Oil & filter, front brake pads</p>
        </div>
        <StatusBadge status="IN_REPAIR" audience="staff" />
      </Link>
    </li>
  </ul>
</Card>
```

Never put `p-5` / `p-4` on `CardContent` or `CardHeader` — the card already pads them.

### 6.3 Data table rows

```tsx
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Reference</TableHead>
      <TableHead>Customer</TableHead>
      <TableHead>Status</TableHead>
      <TableHead className="text-right">Estimate</TableHead>
      <TableHead className="w-0"><span className="sr-only">Open</span></TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {rows.map((b) => (
      <TableRow key={b.id}>
        <TableCell>
          <Link href={…} className="font-mono font-semibold text-brand-blue-ink hover:underline">{b.reference}</Link>
          <p className="text-xs text-helper">{b.scheduledTime} · {b.scheduledDate}</p>
        </TableCell>
        <TableCell>
          <p className="font-medium">{b.customerName}</p>
          <p className="font-mono text-xs text-helper">{b.licensePlate}</p>
        </TableCell>
        <TableCell><StatusBadge status={b.status} audience="staff" /></TableCell>
        <TableCell className="text-right font-medium tabular-nums">{formatPKR(b.estimateTotal)}</TableCell>
        <TableCell><Button asChild variant="outline" size="sm"><Link href={…}>Open</Link></Button></TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

Rules: sentence-case headers (the primitive styles them), money right-aligned
`tabular-nums`, IDs/plates `font-mono`, one action column at the end, no zebra, no `<table>`
by hand. A narrow card gets the stacked list instead (the `@3xl/list:hidden` list from §6.2 +
a `hidden @3xl/list:block` table, on a `@container/list` card, §5), never a 7-column table
squeezed into 390px or into a tablet beside the sidebar.

### 6.4 Chips

- Booking status: `StatusBadge` only.
- Other states: `<Badge variant="success">Active</Badge>`, `warning` (Low stock), `destructive`
  (Suspended), `neutral` (Unlisted), `info`, `brand` (role names: `<Badge variant="brand">Technician</Badge>`),
  `attention` (Action needed — only in the viewer's own queue).
- Counts: `<Badge variant="secondary" className="tabular-nums">5</Badge>`.
- Line types in estimates: `<Badge variant="neutral">Labour</Badge>` / `<Badge variant="info">Part</Badge>`.

### 6.5 Detail page

```tsx
<div className="space-y-6">
  <PageHeader back={…} title={…} badges={<StatusBadge … size="md" />} actions={…} />
  <DetailLayout
    aside={
      <>
        <Card>
          <CardHeader>
            <CardTitle>Next step</CardTitle>
            <CardDescription>Send the estimate so the customer can approve it.</CardDescription>
          </CardHeader>
          <CardContent><Button className="w-full">Send estimate</Button></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Customer</CardTitle></CardHeader>
          <CardContent>
            <dl className="divide-y divide-border-faint text-sm">
              <div className="flex items-start justify-between gap-4 py-2.5">
                <dt className="text-muted-foreground">Name</dt>
                <dd className="text-right font-medium text-foreground">Tariq Jamil</dd>
              </div>
              …
            </dl>
          </CardContent>
        </Card>
      </>
    }
  >
    <Card>…estimate table (flush: `className="gap-0 py-0"` + `Table`)…</Card>
    <Card><CardHeader><CardTitle>Activity</CardTitle></CardHeader><CardContent><Timeline items={…} /></CardContent></Card>
  </DetailLayout>
</div>
```

Totals: a paper well inside the card —
`<div className="rounded-xl bg-layer p-4"><div className="flex justify-between text-sm">…</div><div className="mt-2 flex justify-between text-lg font-bold tabular-nums">…</div></div>`.

### 6.6 Activity timeline

`Timeline` (§5). One line of meta per event; condense noise (show the last 10, "Show all"
ghost button).

### 6.7 Forms

- Settings and long forms: `FormSection` per topic.
- Create flows that are a page (`/pos/shops/new`): one centred column
  `mx-auto max-w-2xl space-y-6`, a `Card` per section with `CardHeader` (title +
  description) and a `FieldGroup` in `CardContent`, the submit button at the end
  (`size="lg"`, full width on phones: `className="w-full sm:w-auto"`).
- Short create/edit (a service, a team member, a stock adjustment): a right `Sheet`
  (`SheetContent className="sm:max-w-md"`) or a `Dialog`.
- Fields: `Field` → `FieldLabel` → control → `FieldDescription` → `FieldError`. Mark errors
  with `aria-invalid` and `<Field data-invalid>`. Labels are sentence case, no colons.
- Toggles that save immediately: `Field orientation="horizontal"` with `FieldContent`
  (`FieldTitle` + `FieldDescription`) and a `Switch`.

### 6.8 Empty states

`EmptyState` (§5): first use (one action), no results (Clear filters), all done (success tone,
no action). One short sentence; never "No data".

### 6.9 Loading

Skeletons shaped like the page, never a spinner for a page:

```tsx
<div className="space-y-6" aria-busy="true">
  <div className="space-y-3">
    <Skeleton className="h-4 w-28 rounded-full" />
    <Skeleton className="h-10 w-72" />
  </div>
  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
    {[0, 1, 2, 3].map((i) => (
      <Skeleton key={i} className="h-32 rounded-2xl" />
    ))}
  </div>
  <Skeleton className="h-96 rounded-2xl" />
  <span className="sr-only">Loading…</span>
</div>
```

Spinners only inside buttons while saving: `<Button disabled><Spinner /> Saving…</Button>`.

### 6.10 Dialogs and sheets

- `Dialog` for short decisions and small forms (≤ 5 fields); `AlertDialog` for destructive
  confirmations (the confirm button is `variant="destructive"`; the button that opens it on the
  page is `variant="destructive-outline"`, §6.15).
- Right `Sheet` for record previews (an audit entry, a parts request, a team member). It is full
  width on phones and 448px from `sm` by itself: no `w-full` / `data-[side=right]:w-full`
  overrides (a wider form may set `sm:max-w-xl`).
- None is ever taller than the screen: dialogs and alert dialogs scroll inside
  (`max-h-[calc(100dvh-2rem)]`), sheets too. Don't add your own `max-h` / `overflow`.
- Footer: secondary first, primary last: `<DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button>Save</Button></DialogFooter>`.

**Focus return (WCAG 2.4.3).** When a dialog, alert dialog or sheet closes, focus goes back to
what opened it. Radix only does that for its own `…Trigger`, so `DialogContent`,
`AlertDialogContent` and `SheetContent` also remember the element that had focus when they opened
(a menu item counts as its menu's trigger) and focus it again on close. Nothing to do for the
common case — a button with `onClick={() => setOpen(true)}`, a row, a menu item. Two cases are
yours:

```tsx
// 1. Focus belongs somewhere else after the action (the opener is gone, or the outcome matters
//    more): take over with onCloseAutoFocus and call preventDefault().
<DialogContent
  onCloseAutoFocus={(event) => {
    if (!confirmed.current) return // cancelled: the opener gets focus back by itself
    event.preventDefault()
    nextStepHeadingRef.current?.focus() // the new "Next step", the success notice, …
  }}
>
// 2. A page that focuses its own outcome while the dialog closes (a notice with
//    `ref={focusOnMount}`) needs nothing: focus that has already moved is left alone.
```

Keep Radix's own `id` on a menu trigger (don't pass `id` to `DropdownMenuTrigger`'s child): the
menu points at it to say which button opened it. For another Radix overlay opened from state,
spread `useFocusReturn(onOpenAutoFocus, onCloseAutoFocus)` (`components/ui/use-focus-return.ts`)
onto its content.

### 6.11 Sticky mobile actions

On phones the page's main decision sits at the bottom of the screen:

```tsx
<StickyActionBar>
  <Button variant="outline">Decline</Button>
  <Button>Approve · {formatPKR(total)}</Button>
</StickyActionBar>
```

Below `md` by default. A page whose actions stay out of reach on a tablet (one column until `lg`
or `xl`) pins them longer with `pinnedUntil="lg"` / `"xl"` and hides the bar where the actions
show beside the content (`lg:hidden` / `xl:hidden`). Give it `role="region"` and an `aria-label`
("Job actions") when it holds more than one button.

Technician screens: job actions `size="lg"` (48px) and inspection toggles `h-12`.

### 6.12 Page hero and the handwritten word

At most one hero band per page, only on a home/greeting page or a confirmation, and at most
one handwritten word per page — never in data views (tables, forms, detail pages).

```tsx
import { Handwritten } from '@/components/booking/booking-hero'

;<section className="bg-hero rounded-3xl border border-border px-6 py-8 sm:px-8 sm:py-10">
  <p className="text-sm font-semibold text-brand-blue-ink">Saturday, 10 October</p>
  <h1 className="mt-1 text-3xl font-extrabold tracking-tight sm:text-4xl">
    Good morning, <Handwritten>Fatima</Handwritten>
  </h1>
  <p className="mt-2 max-w-2xl text-base text-muted-foreground">3 jobs on the floor, 2 need you.</p>
</section>
```

`bg-hero` = white + grid paper fading out + a soft blue glow (no extra divs needed).

### 6.13 Notices

`<Alert variant="info"><Info /><AlertTitle>Read-only</AlertTitle><AlertDescription>…</AlertDescription></Alert>`
— `info` for read-only/tips, `warning` for things to check, `destructive` for failures,
`success` after a completed action that stays on screen. An "action needed" banner inside a
card: `rounded-xl border border-attention-border bg-attention px-4 py-3 text-sm text-foreground`
with the label in `font-semibold text-cta`.

### 6.14 Stretched links (a whole card that opens a record)

The card is `relative`; the link inside it covers the card with its `::after`. Add
`active:scale-none`: a pressed `Button` shrinks with `scale`, and any `scale` (even 100 %) makes
the button the containing block of its own `::after`, so between press and release the overlay
would shrink to the button and a tap on the card would open nothing.

```tsx
<Card className="relative">
  …
  <Button asChild variant="outline" className="after:absolute after:inset-0 active:scale-none">
    <Link href={href}>
      View booking<span className="sr-only"> {booking.reference}</span>
    </Link>
  </Button>
</Card>
```

The `link` variant already uses `active:scale-none`. Keep one focusable element per card (the
link), and its focus ring visible.

### 6.15 Destructive actions on the page

A destructive action that is not the final decision (Cancel booking, Suspend shop, Deactivate) is
`variant="destructive-outline"`: white pill, stone border, danger-ink label (6.5 : 1), pink fill on
hover (5.2 : 1). It comes last in its group and opens an `AlertDialog` whose confirm button is the
solid `destructive`. Don't hand-roll it (`variant="outline"` + `text-danger-ink …`).

---

## 7. Do / don't

**Do**

- Compose pages from `PageHeader`, `StatCard`, `DataTableCard`, `DetailLayout`,
  `Timeline`, `EmptyState`, `FormSection` and the `ui` primitives.
- Use one primary (blue) button per view; secondary actions `outline`, tertiary `ghost`/`link`.
- Use tokens for every colour (§2.1); phase colours only via `StatusBadge` and the phase tokens.
- Keep text at 12px or more; small text in `text-helper`; descriptions in
  `text-muted-foreground`.
- Format money with `formatPKR` + `tabular-nums`; dates with `lib/format`; IDs and plates in
  `font-mono`.
- Check 1440px, 1024px and 768px with the sidebar open, and 390px: no horizontal page scroll,
  touch targets ≥ 40px (48px for technicians).
- Make side-by-side layouts respond to their own width (§2.6): container queries or an intrinsic
  wrap. `PageHeader`, `DetailLayout` and `DataTableCard`'s toolbar already do.
- Use `variant="destructive-outline"` for destructive actions on the page (§6.15).

**Don't**

- No square Carbon fields (bottom-rule inputs, `rounded-none`), no grey tiles, no `bg-layer`
  as a card (it is a tinted well now).
- No navy bars or navy surfaces (`bg-brand-navy` belongs to the auth panel only), no orange
  bars, no 3px coloured side bars.
- No `text-[10px]` / `text-[11px]`, no `uppercase tracking-wider` labels, no
  `tracking-[0.32px]`.
- No hex classes, `bg-white`, grey palettes (test-enforced) — and no raw hues either
  (`bg-blue-50`, `text-emerald-600`, `bg-amber-50`, `hover:bg-blue-700`): use the semantic
  tokens.
- No `text-subtle-foreground` for text (2.5 : 1).
- No white text on `#10B981`: green fills are `bg-brand-green text-brand-green-foreground`.
- No orange button next to the blue primary; `cta` is the "action needed" ink only.
- No hand-made status chips, no hand-made `<table>` (the `Table` container keeps `sr-only`
  text from widening the page on phones), no zebra rows, no `bg-muted` table headers.
- No `p-4`/`p-5` on `CardHeader`/`CardContent`, no `rounded-full` on boxes that hold
  paragraphs (pills are for one-line controls and chips).
- No second handwritten word, and none in data views.
- No `outline-none … focus-visible:outline-2` without `focus-visible:outline-solid` (it hides
  the focus ring, §2.7).
- No local overrides of the shared layout: `DetailLayout` columns (`lg:`/`xl:grid-cols-…`),
  `PageHeader` rows (`[&>div:last-child]:…`, wrapping it in your own flex row), sheet widths
  (`data-[side=right]:w-full`), dialog heights, toolbar control heights. If the shared component
  is wrong, report it.
- No `lg:hidden` / `max-lg:hidden` / `order-*` to move content inside a `DetailLayout` (§5).
- No role or account switcher in the app (D52); people switch accounts on the login page.
- No shop data, not even its name, for someone who is not a member of that shop (D20): the shop
  layout already shows them the 404 view.

---

## 8. Page checklist

1. One `<h1>` (via `PageHeader` or a hero), sentence case.
2. Only tokens, primitives and shared layout components; no Carbon leftovers (§7).
3. Every interactive element reachable by keyboard with the blue focus ring visible.
4. Empty, loading and error states designed (`EmptyState`, skeleton, `Alert`).
5. Screenshots at 1440 × 900, 1024 × 768 and 768 × 1024 (sidebar open) and 390 × 844 look like
   the landing page's product.
6. `pnpm exec prettier --write <files>`, `pnpm lint`, `pnpm typecheck`, `pnpm test` pass.
