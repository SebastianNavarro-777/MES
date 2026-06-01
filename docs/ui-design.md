---
title: UI design — conventions for MES screens
status: skeleton
audience: Workers and Spec Writers touching `frontend/` or `apps/*/interface/`; Architect for new UI Stories.
last_updated: 2026-06-01
---

# UI design

Conventions for the **operator-facing** and **supervisor-facing** screens of the MES. Complements [FRONTEND.md](FRONTEND.md) (stack/folder layout) and [vision/core-beliefs.md](vision/core-beliefs.md) (the "operadores primero" rule).

**Skeleton.** The first Worker that ships a UI Story (NSG-7 in the seed) is expected to flesh out the tokens with the actual values they chose, and subsequent Workers reuse them.

## Why this doc exists

MES screens are unusual — they're consumed on the shop floor (tablet, kiosk, mobile), often by operators wearing gloves, in poor lighting, under time pressure. The default "modern web app" sensibility (low contrast, decorative animations, tiny touch targets, hover states) actively *hurts* in this context.

Workers that ignore the rules here will produce UIs that fail user testing. The Reviewer rejects PRs that violate the **hard rules** at the bottom of this file.

---

## Design tokens

_(The first frontend Worker codifies these. Until then, treat the placeholder values as guidance; pick concrete hex codes that satisfy the constraints below.)_

### Color — status

Status uses a 4-tier palette that always pairs **colour + icon + text**. Never colour-only.

| Tier | Token name | Hex (placeholder) | Used for |
|---|---|---|---|
| Critical | `status-critical` | `#C0392B` (red) | Stopped equipment, NCR open, missed deadline. |
| Warning | `status-warning` | `#E67E22` (orange) | Approaching threshold, retry pending, slow integration. |
| Healthy | `status-healthy` | `#27AE60` (green) | Running, on-target, completed. |
| Neutral | `status-neutral` | `#7F8C8D` (grey) | Idle, draft, scheduled. |

All four tokens MUST satisfy WCAG 2.1 AA contrast (≥4.5:1) against the surface colour they sit on.

### Color — surfaces

| Token | Purpose |
|---|---|
| `surface-page` | Page background. Light grey, NOT white — pure white is harsh under shop-floor lighting. |
| `surface-card` | Cards and panels. |
| `surface-elevated` | Modals and overlays. |

### Spacing scale

Base unit: 4 px. Scale: `4, 8, 12, 16, 24, 32, 48, 64`. Touch targets are **never smaller than 44×44 px** (gloved hands, WCAG 2.5.5). Tap-able elements always have ≥8 px gap between them.

### Type scale

Operator screens use larger type than typical web apps because they're read from 1–1.5 m away:

| Token | Px | Use |
|---|---|---|
| `text-display` | 32 | Andon equipment name, dashboard headline. |
| `text-title` | 24 | Section headers. |
| `text-body-lg` | 18 | Operator-facing primary body. **Default for floor screens.** |
| `text-body` | 16 | Supervisor / admin screens body. |
| `text-caption` | 14 | Metadata, timestamps. |

Line-height ≥1.5× font-size for body. Never use `font-weight: 300` or lighter on floor screens — readability suffers.

---

## Component patterns

These are the recurring UI shapes the MES needs. Workers compose them rather than inventing new ones.

### Status pill

`<status-color> + <icon> + <text>`. Examples: "🛑 Detenido", "⚠ Lento", "✅ Corriendo", "⏸ Inactivo". Always all three. Never just the colored dot.

### Andon card

Equipment-level card showing: equipment name (`text-display`), current state (status pill), OEE percentage with sparkline, time-in-state. Updates from the OEE event stream. Card itself is a touch target — tap opens detail drawer.

### Confirmation modal

State transitions (release order, close order, open NCR) require a confirmation modal. Modal has:
- Title: action verb in past tense ("Confirmar liberación").
- Body: 1-line summary of consequence ("Esta orden saldrá a piso y los operarios podrán arrancarla.").
- Primary action button: action verb (`Liberar`). Secondary: `Cancelar`.
- ESC and overlay click cancel; only the primary button confirms.

For irreversible operations (close order, cancel NCR), require typed confirmation (e.g., type the order ID).

### Form

- Label always above input. Never placeholder-only.
- Required fields marked with `*` next to label, not red border (red = error, not requirement).
- Inline validation only on `blur`, never on `keydown`.
- Errors below the field, prefixed with `⚠` and the field name (so screen readers announce context).
- Submit button disabled only while submitting (not while invalid — let the user click and see all errors at once).

### List + filter

- Filter chips horizontal across the top, never a sidebar (sidebars eat screen on tablets).
- List rows minimum 56 px tall. Identifier left, status pill right.
- Empty state: 1 line + 1 suggested action (e.g., "No hay órdenes liberadas. ¿Crear una?").
- Cursor pagination — load more button at bottom; no infinite scroll on operator screens (lose scroll position when they tap back).

### Scan input

Barcode/QR scan inputs:
- Field auto-focuses on mount.
- Field captures full code on `Enter` (most USB scanners append CR).
- Visual + audible feedback on successful read (green flash + short beep).
- Visual + audible feedback on rejected read (red flash + dissonant beep + reason in text).

---

## Role-specific UX

| Role | Device | Density | Confirmation level |
|---|---|---|---|
| **operator** | Tablet, kiosk, sometimes mobile | Low (large targets, big type) | Heavy — every irreversible action needs explicit confirm. |
| **supervisor** | Laptop, tablet | Medium | Standard — irreversible actions only. |
| **admin** | Laptop | High — Django admin idioms OK | None beyond Django defaults. |

Operator screens NEVER show: stack traces, raw IDs, technical labels (`enabled`, `is_active`), debug toggles. Use human language. Admin and supervisor screens may show technical detail.

---

## Accessibility — shop floor specific

Beyond WCAG 2.1 AA, the MES has factory-floor extras:

- **Contrast under poor lighting.** Assume 200–400 lux ambient (typical shop floor). Test on a tablet at maximum brightness; if any status is hard to discern, fail.
- **Colorblind operators.** Status MUST be perceivable without colour. Validate with a deuteranopia simulator before merging UI tickets.
- **Gloved hands.** Touch targets ≥44 px. No drag-to-reorder, no long-press, no swipe gestures for primary actions (operators wear nitrile or thick leather gloves — capacitive sensitivity varies).
- **Audible feedback** for scan inputs and status transitions, with a per-session mute. Operators rely on audio when their eyes are on the part being worked.
- **No animations on critical paths** longer than 150 ms. A 300 ms slide-in modal feels lethargic when an operator is bottlenecking the line.

---

## Don't do

The Reviewer agent rejects PRs that include any of these:

- **Color-only status indicators.** Always pair colour with icon and text.
- **Placeholder-only form labels.** Placeholders disappear on focus; gloved operators can't recover the label.
- **Touch targets <44 px** on operator screens.
- **`font-weight: 300` (or lighter)** for body text on operator screens.
- **Decorative animations** longer than 150 ms on operator paths.
- **Hover-only affordances** for primary actions (operators are on touch devices).
- **Infinite scroll** on operator lists (back-button loses position).
- **Toasts as the primary success/error indicator** for shop-floor actions — operator might not see it. Use inline confirmation in the form / list itself.
- **Decimals in operator counts.** Show `1234` not `1,234.00`; humans on a shop floor are not accountants.
- **Western Electric chart rules visualised as ASCII** — use the chart library; SPC patterns must be visually unambiguous.

---

## Open questions

- TODO: ¿Qué chart library para Gantt? (Fase 5) — Spec Writer del primer Story de scheduling decide y abre ADR si la decisión cuesta licencia.
- TODO: ¿i18n para operadores extranjeros? (es-MX baseline, pero algunos clientes tienen operarios trilingües). Esperar hasta Fase 2.
- TODO: ¿Dark mode? Probablemente no para operador (lighting es claro), sí para supervisor (oficina). Decidir cuando llegue el primer ticket de supervisor screen.
