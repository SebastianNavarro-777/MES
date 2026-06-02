// GP-010: enumerated states are modelled as a typed enum, never bare string
// literals scattered through conditionals. This object + union type is the
// single source of truth for order statuses on the frontend.

export const OrderStatus = {
  Draft: "draft",
  Released: "released",
  InProgress: "in_progress",
  Completed: "completed",
  Closed: "closed",
} as const;

export type OrderStatusValue = (typeof OrderStatus)[keyof typeof OrderStatus];

/**
 * Canonical forward lifecycle: draft → released → in_progress → completed → closed.
 *
 * This sequence only drives *which actions to render*. The backend
 * (`transition_state`) remains the source of truth and validates every
 * transition server-side; an action shown here can still be rejected (AC-5).
 */
export const ORDER_STATUS_SEQUENCE: readonly OrderStatusValue[] = [
  OrderStatus.Draft,
  OrderStatus.Released,
  OrderStatus.InProgress,
  OrderStatus.Completed,
  OrderStatus.Closed,
];

/** Type guard: is the given value a known order status? */
export function isOrderStatus(value: unknown): value is OrderStatusValue {
  return (
    typeof value === "string" &&
    (ORDER_STATUS_SEQUENCE as readonly string[]).includes(value)
  );
}

/**
 * Valid transitions offered from `current`. The lifecycle is strictly linear,
 * so each status offers at most one forward transition (the terminal `closed`
 * state offers none).
 */
export function getAvailableTransitions(
  current: OrderStatusValue,
): readonly OrderStatusValue[] {
  const index = ORDER_STATUS_SEQUENCE.indexOf(current);
  if (index === -1) {
    return [];
  }
  const next = ORDER_STATUS_SEQUENCE[index + 1];
  return next === undefined ? [] : [next];
}
