import { describe, expect, it } from "vitest";
import {
  OrderStatus,
  getAvailableTransitions,
  isOrderStatus,
} from "../orderStatus";

describe("getAvailableTransitions", () => {
  // AC-2: La pantalla ofrece únicamente las transiciones de estado válidas
  // desde el estado actual según la máquina de estados
  // (draft → released → in_progress → completed → closed).
  it("offers only the single valid forward transition for each state", () => {
    expect(getAvailableTransitions(OrderStatus.Draft)).toEqual([
      OrderStatus.Released,
    ]);
    expect(getAvailableTransitions(OrderStatus.Released)).toEqual([
      OrderStatus.InProgress,
    ]);
    expect(getAvailableTransitions(OrderStatus.InProgress)).toEqual([
      OrderStatus.Completed,
    ]);
    expect(getAvailableTransitions(OrderStatus.Completed)).toEqual([
      OrderStatus.Closed,
    ]);
  });

  // AC-2: las transiciones no permitidas no se muestran como acción disponible
  // (el estado terminal `closed` no ofrece ninguna).
  it("offers no transitions from the terminal closed state", () => {
    expect(getAvailableTransitions(OrderStatus.Closed)).toEqual([]);
  });
});

describe("isOrderStatus", () => {
  it("accepts known statuses and rejects everything else", () => {
    expect(isOrderStatus("draft")).toBe(true);
    expect(isOrderStatus("released")).toBe(true);
    expect(isOrderStatus("paused")).toBe(false);
    expect(isOrderStatus(42)).toBe(false);
    expect(isOrderStatus(null)).toBe(false);
  });
});
