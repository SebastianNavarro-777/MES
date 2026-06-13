import { OrderStatus } from "../features/orders/orderStatus";
import type { OrderStatusValue } from "../features/orders/orderStatus";

// es-MX is the baseline (and currently only) locale. Strings are externalised
// from day one per docs/FRONTEND.md, even with a single locale.

export type StatusTier = "critical" | "warning" | "healthy" | "neutral";

interface StatusPresentation {
  readonly label: string;
  readonly icon: string;
  readonly tier: StatusTier;
}

/** Human label, icon and colour tier for each order status (colour + icon + text). */
export const ORDER_STATUS_PRESENTATION: Readonly<
  Record<OrderStatusValue, StatusPresentation>
> = {
  [OrderStatus.Draft]: { label: "Borrador", icon: "📝", tier: "neutral" },
  [OrderStatus.Released]: { label: "Liberada", icon: "📋", tier: "neutral" },
  [OrderStatus.InProgress]: { label: "En proceso", icon: "▶", tier: "healthy" },
  [OrderStatus.Completed]: { label: "Completada", icon: "✅", tier: "healthy" },
  [OrderStatus.Closed]: { label: "Cerrada", icon: "🔒", tier: "neutral" },
};

/** Action verb shown on the button/modal for a transition *into* a status. */
export const ORDER_TRANSITION_ACTION: Readonly<
  Record<OrderStatusValue, string>
> = {
  [OrderStatus.Draft]: "Regresar a borrador",
  [OrderStatus.Released]: "Liberar",
  [OrderStatus.InProgress]: "Iniciar",
  [OrderStatus.Completed]: "Completar",
  [OrderStatus.Closed]: "Cerrar",
};

export const messages = {
  appTitle: "NSG MES",
  order: {
    detailHeading: "Orden de fabricación",
    fields: {
      id: "Identificador",
      product: "Producto",
      qty: "Cantidad",
      route: "Ruta",
      dueDate: "Fecha compromiso",
      status: "Estado actual",
    },
    transitions: {
      heading: "Cambios de estado",
      none: "No hay cambios de estado disponibles desde el estado actual.",
    },
    loading: "Cargando orden…",
    notFound: {
      title: "Orden no encontrada",
      body: "No existe una orden con ese identificador. Verifica el código e inténtalo de nuevo.",
    },
    error: {
      title: "No se pudo cargar la orden",
      body: "Ocurrió un error al consultar la orden. Reintenta en unos segundos.",
      retry: "Reintentar",
    },
    transitionError: {
      // Operator-readable; never a stack trace or raw status code.
      generic: "No se pudo cambiar el estado de la orden. La orden conserva su estado anterior.",
    },
  },
  modal: {
    titlePrefix: "Confirmar",
    from: "Estado actual",
    to: "Nuevo estado",
    confirmSuffix: "",
    cancel: "Cancelar",
  },
  wip: {
    heading: "Balances de WIP",
    subheading: "Inventario en proceso por paso de ruta",
    /** Prefix for a route step label, e.g. "Paso 2". */
    routeStepPrefix: "Paso",
    columns: {
      routeStep: "Paso de ruta",
      qtyIn: "Entradas",
      qtyOut: "Salidas",
      qtyScrap: "Merma",
      balance: "Balance",
    },
    loading: "Cargando balances de WIP…",
    empty: "Esta orden todavía no tiene balances de WIP registrados.",
    error: {
      title: "No se pudieron cargar los balances de WIP",
      body: "Ocurrió un error al consultar el inventario en proceso. Reintenta en unos segundos.",
      retry: "Reintentar",
    },
  },
} as const;
