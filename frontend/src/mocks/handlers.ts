import { http, HttpResponse } from "msw";
import type { ManufacturingOrderDto, TransitionRequest } from "../api/orders";
import { API_BASE } from "../api/client";
import { getAvailableTransitions } from "../features/orders/orderStatus";
import { SEED_ORDERS } from "./orders.fixtures";
import { SEED_WIP_POSITIONS } from "./wip.fixtures";

// In-memory order store backing the mock orders API. It persists for the
// lifetime of a browser session (so a transition survives a refetch in dev/E2E)
// and is reset between unit tests via `resetOrdersStore()`.
let store = new Map<string, ManufacturingOrderDto>();

export function resetOrdersStore(): void {
  store = new Map(SEED_ORDERS.map((order) => [order.id, { ...order }]));
}

resetOrdersStore();

function problem(
  status: number,
  slug: string,
  title: string,
  detail: string,
  instance: string,
) {
  return HttpResponse.json(
    {
      type: `https://nsg.mx/problems/orders/${slug}`,
      title,
      status,
      detail,
      instance,
    },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

export const handlers = [
  http.get(`${API_BASE}/orders/:orderId/`, ({ params }) => {
    const orderId = String(params.orderId);
    const order = store.get(orderId);
    if (order === undefined) {
      return problem(
        404,
        "order-not-found",
        "Order does not exist",
        `order '${orderId}' does not exist`,
        `${API_BASE}/orders/${orderId}/`,
      );
    }
    return HttpResponse.json(order);
  }),

  http.post(`${API_BASE}/orders/:orderId/transition/`, async ({ params, request }) => {
    const orderId = String(params.orderId);
    const order = store.get(orderId);
    const instance = `${API_BASE}/orders/${orderId}/transition/`;

    if (order === undefined) {
      return problem(
        404,
        "order-not-found",
        "Order does not exist",
        `order '${orderId}' does not exist`,
        instance,
      );
    }

    const body = (await request.json()) as TransitionRequest;
    const allowed = getAvailableTransitions(order.status);
    if (!allowed.includes(body.target_state)) {
      return problem(
        409,
        "invalid-transition",
        "Invalid order transition",
        `cannot transition from ${order.status} to ${body.target_state}`,
        instance,
      );
    }

    const updated: ManufacturingOrderDto = { ...order, status: body.target_state };
    store.set(orderId, updated);
    return HttpResponse.json(updated);
  }),

  // WIP read projection (ADR 0004 / NSG-37). The `wip` context owns this URL and
  // filters by `order_id`. It never queries `orders` synchronously, so an order
  // with no positions (or an unknown order) returns 200 with `[]`, never 404.
  http.get(`${API_BASE}/wip/positions/`, ({ request }) => {
    const url = new URL(request.url);
    const orderId = url.searchParams.get("order_id");
    const positions =
      orderId === null ? [] : (SEED_WIP_POSITIONS[orderId] ?? []);
    return HttpResponse.json(positions);
  }),
];
