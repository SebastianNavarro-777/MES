import type { WipPositionDto } from "../api/wip";

/**
 * Seed WIP balances used by the MSW mock backend (dev + E2E + as test defaults).
 * Keyed by order id; an order absent from this map yields an empty list `[]`
 * (never 404), matching NSG-37 AC-3.
 *
 * OF-2002 is "in_progress" and therefore has live balances across its route.
 * OF-1001 (draft) and OF-3003 (closed) are intentionally omitted so the empty
 * state is exercisable.
 */
export const SEED_WIP_POSITIONS: Readonly<
  Record<string, readonly WipPositionDto[]>
> = {
  "OF-2002": [
    { order_id: "OF-2002", route_step: 1, qty_in: 250, qty_out: 250, qty_scrap: 0, balance: 0 },
    { order_id: "OF-2002", route_step: 2, qty_in: 250, qty_out: 200, qty_scrap: 5, balance: 45 },
    { order_id: "OF-2002", route_step: 3, qty_in: 200, qty_out: 0, qty_scrap: 0, balance: 200 },
  ],
};
