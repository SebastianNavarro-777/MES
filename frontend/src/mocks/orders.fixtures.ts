import type { ManufacturingOrderDto } from "../api/orders";
import { OrderStatus } from "../features/orders/orderStatus";

/** Seed orders used by the MSW mock backend (dev + E2E + as test defaults). */
export const SEED_ORDERS: readonly ManufacturingOrderDto[] = [
  {
    id: "OF-1001",
    product_id: "PROD-A",
    product_name: "Soporte de aluminio A",
    qty: 100,
    route: "RUTA-ESTÁNDAR",
    due_date: "2026-06-15",
    status: OrderStatus.Draft,
  },
  {
    id: "OF-2002",
    product_id: "PROD-B",
    product_name: "Cubierta de acero B",
    qty: 250,
    route: "RUTA-CNC",
    due_date: "2026-06-20",
    status: OrderStatus.InProgress,
  },
  {
    id: "OF-3003",
    product_id: "PROD-C",
    product_name: "Ensamble final C",
    qty: 40,
    route: "RUTA-ENSAMBLE",
    due_date: "2026-05-30",
    status: OrderStatus.Closed,
  },
];
