# UI redesign notes

- **Theme:** soft-UI (raised / pressed surfaces) in a light and a dark theme. A Light / Dark / System
  switch sits in every header (public, customer, POS, admin, auth). The choice is remembered.
  Tokens live in `apps/web/src/app/globals.css`; `neu-raised`, `neu-surface`, `neu-inset`,
  `neu-primary`, `neu-press` are the soft-UI utilities.
- **Buttons:** `apps/web/src/components/ui/button.tsx`. New `shape` prop: `pill` (default; circle at
  icon sizes) or `square` (rounded rectangle). Pressed / toggled-on buttons sink in.
- **Fonts:** Sora (headings), Plus Jakarta Sans (body), Caveat (accent word), JetBrains Mono.
- **Images:** all hero, phone, dashboard, shop cover, avatar and feature artwork is new and original
  (`apps/web/public`). The old GarageBox stock assets are gone.
- **Help agent:** `components/help/help-agent.tsx` (mounted in the root layout) answers only from
  `features/help/knowledge.ts` and declines anything unrelated to BayFlow.
