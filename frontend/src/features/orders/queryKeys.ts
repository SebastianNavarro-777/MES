// Centralised TanStack Query keys for the orders feature so the detail query
// can be invalidated consistently after a successful transition (see NSG-41,
// which reuses this key to keep its WIP panel in sync).

export const orderKeys = {
  all: ["orders"] as const,
  detail: (orderId: string) => [...orderKeys.all, "detail", orderId] as const,
};
