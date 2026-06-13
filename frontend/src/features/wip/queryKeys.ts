// Centralised TanStack Query keys for the wip feature. Keyed by order so the
// order-detail screen can invalidate a single order's WIP balances after a
// state transition without touching unrelated cache entries.

export const wipKeys = {
  all: ["wip"] as const,
  byOrder: (orderId: string) =>
    [...wipKeys.all, "positions", orderId] as const,
};
