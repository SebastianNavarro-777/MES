import { getJson, postJson } from "./client";
import type { OrderStatusValue } from "../features/orders/orderStatus";

// --- API contract (consumed) -------------------------------------------------
// Owned by the orders backend Story in Epic NSG-14; mocked with MSW until it
// ships. Confirmed shape:
//
//   GET  /api/v1/orders/{id}/        -> 200 ManufacturingOrderDto | 404 problem+json
//   POST /api/v1/orders/{id}/transition/
//        body: { "target_state": OrderStatusValue }
//        -> 200 ManufacturingOrderDto (new state)
//        -> 409 problem+json (invalid transition / state conflict)
// -----------------------------------------------------------------------------

/** Manufacturing order as returned by the orders API. */
export interface ManufacturingOrderDto {
  readonly id: string;
  readonly product_id: string;
  readonly product_name: string;
  readonly qty: number;
  readonly route: string;
  /** ISO-8601 date (commitment / due date). */
  readonly due_date: string;
  readonly status: OrderStatusValue;
}

export interface TransitionRequest {
  readonly target_state: OrderStatusValue;
}

export function fetchOrder(orderId: string): Promise<ManufacturingOrderDto> {
  return getJson<ManufacturingOrderDto>(
    `/orders/${encodeURIComponent(orderId)}/`,
  );
}

export function transitionOrder(
  orderId: string,
  targetState: OrderStatusValue,
): Promise<ManufacturingOrderDto> {
  const payload: TransitionRequest = { target_state: targetState };
  return postJson<ManufacturingOrderDto>(
    `/orders/${encodeURIComponent(orderId)}/transition/`,
    payload,
  );
}
