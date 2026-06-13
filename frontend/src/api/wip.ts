import { getJson } from "./client";

// --- API contract (consumed) -------------------------------------------------
// Owned by the `wip` context (Story NSG-37, Epic NSG-32); mocked with MSW until
// it ships. The read URL is fixed by ADR docs/decisions/0004-wip-read-api-url.md
// (NSG-42, Option A): the `wip` context owns and exposes its read projection and
// the frontend filters by `order_id` — NOT the stale `GET /api/v1/orders/{id}/wip/`
// that older Story text mentioned. Keeping the read under `wip/` preserves the
// bounded-context boundary (orders never proxies wip data).
//
//   GET /api/v1/wip/positions/?order_id={id}
//        -> 200 WipPositionDto[]  (empty list [] when the order has no positions;
//                                   never 404 — wip cannot validate the order
//                                   synchronously, see NSG-37 AC-3)
// -----------------------------------------------------------------------------

/**
 * WIP balance for one route step of one order, as returned by the wip API.
 *
 * `balance` is the net balance computed by the wip domain (NSG-37 AC-1). The
 * frontend renders it verbatim and never recomputes the formula client-side.
 */
export interface WipPositionDto {
  readonly order_id: string;
  /** Ordinal position of the step within the order's route (1-based). */
  readonly route_step: number;
  readonly qty_in: number;
  readonly qty_out: number;
  readonly qty_scrap: number;
  /** Net balance computed by the wip domain; the UI does not recalculate it. */
  readonly balance: number;
}

export function fetchWipPositions(
  orderId: string,
): Promise<readonly WipPositionDto[]> {
  return getJson<WipPositionDto[]>(
    `/wip/positions/?order_id=${encodeURIComponent(orderId)}`,
  );
}
