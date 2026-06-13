import { useMutation, useQueryClient } from "@tanstack/react-query";
import { transitionOrder } from "../../api/orders";
import type { ManufacturingOrderDto } from "../../api/orders";
import type { OrderStatusValue } from "./orderStatus";
import { orderKeys } from "./queryKeys";

/**
 * Mutation that asks the backend to transition an order to `targetState`.
 *
 * On success we both prime the cache with the returned order and invalidate the
 * detail query (per the NSG-41 pattern), so the screen reflects the new state
 * and the freshly-available transitions without a manual reload (AC-4).
 *
 * On error nothing is written to the cache, so the order keeps its previous
 * state (AC-5); the caller renders the error message.
 */
export function useTransitionOrder(orderId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (targetState: OrderStatusValue) =>
      transitionOrder(orderId, targetState),
    onSuccess: (updated: ManufacturingOrderDto) => {
      queryClient.setQueryData(orderKeys.detail(orderId), updated);
      void queryClient.invalidateQueries({
        queryKey: orderKeys.detail(orderId),
      });
    },
  });
}
